# KYRO

**AI-based medical triage and dynamic doctor assignment · academic simulation**

KYRO demonstrates how an uncalibrated severity prediction can support a human review before a fictional case enters a capacity-limited specialty queue. The default application runs offline after setup and stores fictional cases on the local computer. It has no clinical validation. Use fabricated inputs only.

## Run on Windows 10 or 11

Install 64-bit Python 3.11 and Git. In PowerShell:

```powershell
git clone https://github.com/saivats/Kyro.git
cd Kyro
.\setup.bat
.\start.bat
```

Open **http://127.0.0.1:5000**. Initial setup downloads dependencies and checks the committed model. On subsequent runs use `start.bat`. Stop with Ctrl+C. No Supabase account or training step is required. For the presentation sequence and guarded reset, see [DEMO_GUIDE.md](DEMO_GUIDE.md).

On Linux or macOS use Python 3.11, a virtual environment, `python -m pip install -r requirements-demo.txt` and `python demo.py`. Docker Compose offers an optional local launch with `docker compose up --build`; it publishes only to loopback and persists SQLite in a named volume.

## Application structure

| Location | Responsibility |
| --- | --- |
| `demo.py` | Flask entry point, normalized intake, SQLite migration, transactions, roster and workflow |
| `demo_templates/`, `static/` | Offline dashboard, triage inspector, queue, doctor workspace, analytics and activity |
| `app/ai/features.py` | Ordered feature contract and transformations |
| `app/ai/inference.py` | Cached XGBoost booster, probability vector and exact TreeSHAP contributions |
| `app/ai/artifacts/` | Committed booster, metadata, historical evaluation |
| `app/ai/train.py`, `app/ai/nhamcs_loader.py` | Legacy hybrid training and data ingestion |
| `app/services/`, `supabase_schema.sql` | Earlier Supabase prototype |
| `tests/` | Validation, actual-model regression, lifecycle, concurrency and browser workflow |

## Prediction and human review

The model consumes 29 numeric inputs in the order saved with the booster. Inputs include age, encoded gender, six vitals (temperature in Fahrenheit), prior triage, EMS arrival, twelve chronic flags and seven derived features. The local API requires explicit vital values, temperature unit, history and flags. Celsius is converted once. The legacy model codes male as 1 and female/other as 0 at inference. This encoding loses information. SpO₂ and free-text symptoms appear beside the AI output for review and do not affect model scores.

The inspector shows four uncalibrated scores and the five largest absolute TreeSHAP contributions to the predicted class. The signed contributions plus a base value reconstruct its raw margin before the multiclass probability transformation. A contribution measures model behavior, not causation or medical risk. The application reuses one feature vector for prediction and explanation. If the model fails, intake returns 503 and writes no case.

A reviewer confirms or changes severity and routing specialty. Reviewed cases wait for matching available doctors. Dispatch orders patients by confirmed severity, then intake sequence. Eligible doctors are ordered by workload divided by capacity, then doctor ID. A doctor's open cases count toward capacity until completion. Closing availability stops new assignments and preserves existing work. Completion and subsequent dispatch share one transaction.

`review → waiting → assigned → in_treatment → completed`. An available slot can make the waiting state transient. A unique request ID makes intake retries safe. SQLite foreign keys, an immediate write transaction and indexed assignment lookups keep capacity consistent. Earlier demo records migrate in place; previously unrecorded clinical detail and SHAP values appear as unavailable. The queue displays active cases and up to 50 recent completions. Overview totals use the entire database.

## Local API

| Method | Path | Operation |
| --- | --- | --- |
| GET | `/health/live`, `/health/ready` | Process liveness and database/model readiness |
| POST | `/api/demo/intake` | Validate a fictional case, predict and save for review |
| GET | `/api/demo/cases/<id>` | Retrieve normalized input and persisted explanation |
| POST | `/api/demo/cases/<id>/action` | Review (severity 0–3 and specialty), start or complete |
| POST | `/api/demo/doctors`, `/api/demo/doctors/<id>` | Register or update fictional roster and dispatch eligible cases |
| GET | `/api/demo/state` | Workflow, capacity, duration aggregates and audit activity |
| GET | `/api/demo/model` | Model contract and committed historical evaluation |

See `tests/test_demo.py::payload` for a complete JSON intake example. Include `synthetic_only: true` and a unique `request_id`. Reusing a key for changed input returns 409. The default database is `demo_data/kyro.sqlite3`. Set `KYRO_DEMO_DB` to select an isolated simulation.

## Historical model evaluation

Version 1.0.0 was evaluated on 3,543 mixed real/synthetic rows. The committed report records **85.55% accuracy, 85.11% macro F1, 95.42% macro ROC AUC, 69.35% High recall and 100% Critical recall**. Of 535 High reference cases, 125 were predicted Low and 35 Medium. These are historical results. Regression and browser tests verify software behavior only.

Legacy preparation paths use different rule-derived labels and sex/chronic-field encodings. Some missing fields are filled with zero, medians can be computed before splitting, and synthetic and real cases are combined before evaluation. Prior immediate triage also overlaps the target definition. The evaluation does not establish performance on an independent real-only cohort. The released model is preserved. Replacing it requires reconciled preprocessing, provenance, a training-only fit and independent evaluation.

## Verify

```powershell
.\.venv\Scripts\python.exe -m pip install pytest
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip install playwright
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe tests/browser_workflow.py
```

Browser verification launches the real app on a temporary database and drives intake, signed explanations, review, queueing, treatment, automatic dispatch, refresh and a narrow viewport. The browser tooling is optional for ordinary demonstrations.

## Legacy research interfaces

`run.py` uses the legacy Supabase API, and `server.py` is the older standalone prediction API. Their contracts and assignment behavior differ from the local demo. For isolated Supabase development, install `requirements.txt`, copy `.env.example` to `.env`, configure a separate test project, review `supabase_schema.sql` before applying it, and run `python run.py`. Keep keys server-side. The earlier schema and services lack a verified authorization/RLS boundary and transactional patient lifecycle. This release provides no hosted deployment with real patient access. The local simulation is single-user and has no authenticated clinician identity.

## Troubleshooting

- **Python launcher missing** — setup also accepts a 64-bit Python 3.11 available as `python`. A pre-existing virtual environment must use that version.
- **Model unavailable** — run `setup.bat` in the release checkout and check that `app/ai/artifacts/xgb_severity_model.json` exists. Clear any stale `MODEL_PATH` override.
- **Port 5000 in use** — stop the previous KYRO terminal or the process already using the port before starting.
- **Database identity/version error** — use a dedicated demo path or restore a compatible backup. Existing unrelated tables are left intact.

The original architecture and contributor plan are preserved in [WorkPlan.md](WorkPlan.md). Its roadmap describes proposed work.
