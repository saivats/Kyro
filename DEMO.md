# KYRO — local academic demonstration

This branch adds a separate, local-first simulation. It does not replace or claim to harden the legacy Supabase API. **Never enter real patient data or use these results for medical decisions.** The committed XGBoost model is a research prototype evaluated on mixed synthetic and real data; its scores are not clinically calibrated. Symptoms and oxygen saturation are not model features. Every case must receive an explicit simulated human review before assignment; specialty is selected manually rather than inferred medically.

## Windows quick start

From the repository root (Python 3.11):

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe demo.py
```

Open http://127.0.0.1:5000. No Supabase account is required; the shipped model is used without retraining. Keep the terminal open. Stop with Ctrl+C. The demo binds to loopback with debug disabled. Do not expose it on a network.

1. Load a fictional example, confirm fictional data, run AI triage.
2. Choose a simulated reviewed severity. The case enters the specialty-specific queue, and is assigned if capacity exists.
3. Start treatment, then complete. Capacity is released and the next waiting case is dispatched by reviewed severity then arrival order.
4. Repeat intake to show capacity limits, waiting cases and event history. Dashboard polls every five seconds; this is not WebSocket streaming.

Demo state is stored in demo_data/kyro.sqlite3 (ignored by Git). To reset, stop the server and remove the demo database. Only the case label, specialty, oxygen value, model output, workflow state and event history are retained; no real identifiers should be used.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pip install pytest
.\.venv\Scripts\python.exe -m pytest -q
```

The suite includes Celsius/Fahrenheit normalization, invalid inputs, explicit review, specialty routing, capacity, simultaneous review requests, lifecycle, idempotency, model failure, dashboard HTTP smoke and a real committed-model prediction. A passing suite does not establish clinical validity or production security.

## Remaining scope

The existing run.py and server.py remain legacy research interfaces, not deployment-ready. Supabase transaction/RLS/RBAC migrations, authentication, clinical validation, independent real-only holdout, retraining, SHAP UI, multi-tenancy, WebSockets and production deployment require separate verification and implementation. The local demo deliberately does not implement these as simulated or misleading production features.
