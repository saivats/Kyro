import concurrent.futures
import json
import sqlite3

import numpy as np
import pytest
import xgboost as xgb

from app.ai.features import ALL_FEATURES, build_feature_vector
from app.ai.inference import get_model
from demo import ROOT, create_demo_app, initialize, normalize
from test_demo import action, intake, payload, state


def test_real_model_explanation_persists(tmp_path):
    path = tmp_path / "cases.db"
    client = create_demo_app(path).test_client()
    assert client.get("/health/ready").status_code == 200
    data = payload(symptoms="Fictional shortness of breath", chronic_conditions=["asthma"])
    response = client.post("/api/demo/intake", json=data)
    assert response.status_code == 201
    client = create_demo_app(path).test_client()
    detail = client.get("/api/demo/cases/" + response.json["id"]).json
    assert detail["intake"]["symptoms"] == data["symptoms"]
    result = detail["result"]
    vector = build_feature_vector(normalize(data))
    names = json.loads((ROOT / "app/ai/artifacts/model_meta.json").read_text())["features"]
    assert names == ALL_FEATURES == list(vector.columns) == get_model().feature_names
    assert vector.loc[0, "temperature"] == pytest.approx(98.6)
    assert vector.loc[0, "asthma"] == vector.loc[0, "gender"] == 1
    assert "oxygen_saturation" not in names and "symptoms" not in names
    matrix = xgb.DMatrix(vector, nthread=1)
    expected = get_model().predict(matrix)[0]
    assert result["probabilities"] == pytest.approx(expected)
    predicted = result["predicted_class"]
    assert predicted == int(np.argmax(expected))
    assert result["confidence"] == pytest.approx(expected[predicted])
    weights = result["feature_importance"]
    assert {x["feature"] for x in weights} == set(names)
    total = result["base_margin"] + sum(x["shap_value"] for x in weights)
    assert total == pytest.approx(get_model().predict(matrix, output_margin=True)[0, predicted], abs=0.0001)


def test_simultaneous_retries_and_completion(tmp_path):
    app = create_demo_app(tmp_path / "demo.db", predictor=lambda d: (1, .7))
    def submit(_):
        with app.test_client() as client:
            return client.post("/api/demo/intake", json=payload()).status_code
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        codes = list(pool.map(submit, range(6)))
    assert sorted(codes) == [200]*5 + [201]
    client = app.test_client()
    case = state(client)["cases"][0]["id"]
    action(client, case, "review", severity=1)
    action(client, case, "start")
    def finish(_):
        with app.test_client() as c:
            return action(c, case, "complete").status_code
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(finish, range(2))) == [200, 409]
    assert state(client)["counts"] == {"completed": 1}


def test_roster_priority_fifo_and_review_specialty(tmp_path):
    client = create_demo_app(tmp_path / "db", predictor=lambda d: (0, .5)).test_client()
    roster = dict(name="Doctor B", specialty="cardiology", capacity=1, available=False)
    url = "/api/demo/doctors/d2"
    assert client.post(url,json=roster).status_code == 200
    ids = [intake(client, str(i)) for i in range(3)]
    for case, severity in zip(ids, [1,3,3]):
        assert action(client, case, "review", severity=severity, specialty="cardiology").status_code == 200
    assert state(client)["counts"] == {"waiting":3}
    roster["available"] = True
    assert client.post(url,json=roster).status_code == 200
    assert client.post(url,json={**roster,"specialty":"general"}).status_code == 409
    assert action(client,ids[1],"start").status_code == 200
    assert action(client,ids[1],"complete").status_code == 200
    assert action(client,ids[2],"start").status_code == 200
    assert client.post("/api/demo/doctors", json={**roster,"name":"Relief"}).status_code == 201
    assert state(client)["counts"] == {"assigned":1,"completed":1,"in_treatment":1}


def test_unrelated_database_preserved(tmp_path):
    path = tmp_path / "other.db"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE personal(value TEXT)")
    with pytest.raises(RuntimeError):
        initialize(path)
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT name FROM sqlite_master").fetchall() == [("personal",)]


def test_request_errors_and_rollback(tmp_path):
    path = tmp_path / "demo.db"
    client = create_demo_app(path,predictor=lambda d:(2,.7)).test_client()
    assert client.post("/api/demo/intake",data="x",content_type="application/json").status_code == 400
    assert client.post("/api/demo/intake",data="x"*40000,content_type="application/json").status_code == 413
    case = intake(client,"case")
    with sqlite3.connect(path) as db:
        db.execute("CREATE TRIGGER fail_event BEFORE INSERT ON events BEGIN SELECT RAISE(ABORT,'fail'); END")
    response = action(client,case,"review",severity=3)
    assert response.status_code == 500
    assert state(client)["cases"][0]["state"] == "review"
    assert all(d["load"] == 0 for d in state(client)["doctors"])

def test_previous_demo_database_migrates_without_fabricating_details(tmp_path):
    path = tmp_path / "older.db"
    with sqlite3.connect(path) as db:
        db.executescript("""
          CREATE TABLE doctors(id TEXT PRIMARY KEY,name TEXT,specialty TEXT,capacity INTEGER);
          CREATE TABLE cases(seq INTEGER PRIMARY KEY,id TEXT UNIQUE,request_id TEXT UNIQUE,fingerprint TEXT,
            name TEXT,specialty TEXT,predicted INTEGER,confidence REAL,reviewed INTEGER,oxygen REAL,state TEXT,
            doctor_id TEXT REFERENCES doctors(id),created TEXT);
          CREATE TABLE events(seq INTEGER PRIMARY KEY,case_id TEXT,action TEXT,created TEXT);
          INSERT INTO cases VALUES(1,'old','old-request','hash','Earlier case','general',1,.6,NULL,99,'review',NULL,'2026-01-01 00:00:00');
        """)
    client = create_demo_app(path, predictor=lambda d:(1,.6)).test_client()
    assert client.get("/api/demo/cases/old").json == {"intake":None,"result":None}
    assert action(client,"old","review",severity=1).status_code == 200
    assert state(client)["cases"][0]["state"] == "assigned"
