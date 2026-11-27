"""Prediction and exact TreeSHAP contributions from the committed multiclass booster."""
from __future__ import annotations

from pathlib import Path
from threading import RLock

import numpy as np
import xgboost as xgb

from app.ai.features import ALL_FEATURES, build_feature_vector
from app.core.config import settings
from app.core.errors import AIModelError

_lock = RLock()
_model = None


def _read_model():
    candidate = xgb.Booster(params={"nthread": 1})
    candidate.load_model(Path(settings.ai.MODEL_PATH))
    candidate.set_param({"nthread": 1})
    if candidate.feature_names != ALL_FEATURES:
        raise AIModelError("Model feature contract mismatch")
    return candidate


def reload_model():
    global _model
    with _lock:
        _model = _read_model()


def get_model():
    global _model
    with _lock:
        if _model is None:
            _model = _read_model()
        return _model


def infer(patient_data, *, explain=True):
    model = get_model()
    row = xgb.DMatrix(build_feature_vector(patient_data), nthread=1)
    probabilities = model.predict(row, strict_shape=True)[0]
    if (probabilities.shape != (4,) or not np.isfinite(probabilities).all()
            or np.any(probabilities < 0) or np.any(probabilities > 1)
            or not np.isclose(probabilities.sum(), 1.0, atol=1e-6)):
        raise AIModelError("Invalid probability vector")
    severity = int(probabilities.argmax())
    result = {
        "predicted_class": severity,
        "predicted_label": settings.ai.SEVERITY_CLASSES[severity],
        "confidence": float(probabilities[severity]),
        "probabilities": probabilities.tolist(),
    }
    if explain:
        values = model.predict(row, pred_contribs=True, strict_shape=True)[0]
        if values.shape != (4, len(ALL_FEATURES) + 1) or not np.isfinite(values).all():
            raise AIModelError("Invalid contribution matrix")
        weights = values[severity, :-1]
        result["base_margin"] = float(values[severity, -1])
        result["feature_importance"] = [
            {"feature": ALL_FEATURES[i], "shap_value": float(weights[i])}
            for i in np.argsort(-np.abs(weights), kind="stable")
        ]
    return result


def predict_severity(patient_data):
    result = infer(patient_data, explain=False)
    return result["predicted_class"], result["confidence"], np.array(result["probabilities"])


def explain_prediction(patient_data):
    result = infer(patient_data)
    # Preserve the legacy response field. Its values describe class direction.
    result["risk_factors"] = [
        {**item, "direction": "toward" if item["shap_value"] > 0 else
         "away" if item["shap_value"] < 0 else "neutral"}
        for item in result["feature_importance"][:10]
    ]
    return result
