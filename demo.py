"""Local, synthetic-only KYRO academic demonstration. Not clinical software."""
from __future__ import annotations
import math
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from flask import Flask, jsonify, request, render_template
from werkzeug.exceptions import HTTPException

ROOT = Path(__file__).resolve().parent
LABELS = ["Low", "Medium", "High", "Critical"]
SPECIALTIES = ("general", "cardiology", "respiratory", "trauma")
VITALS = {"heart_rate": (20, 250), "systolic_bp": (40, 300),
          "diastolic_bp": (20, 200), "respiratory_rate": (5, 80),
          "pain_scale": (0, 10), "oxygen_saturation": (1, 100)}
STATES = ("review", "waiting", "assigned", "in_treatment", "completed")

class Invalid(ValueError):
    pass

class Conflict(Invalid):
    pass

def number(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise Invalid(name + " must be numeric")
    if not math.isfinite(value) or not low <= value <= high:
        raise Invalid(name + " outside demo input bounds")
    return value

def normalize(data):
    if not isinstance(data, dict):
        raise Invalid("Expected a JSON object")
    label = data.get("name")
    if not isinstance(label, str) or not label.strip() or len(label) > 80:
        raise Invalid("Enter a fictional case label (1-80 characters)")
    age = number(data.get("age"), "age", 18, 90)
    if int(age) != age:
        raise Invalid("Age must be an integer")
    gender = data.get("gender")
    if gender not in ("male", "female", "other"):
        raise Invalid("Invalid gender")
    specialty = data.get("specialty")
    if specialty not in SPECIALTIES:
        raise Invalid("Select a specialty for this simulated case")
    vitals = data.get("vitals")
    if not isinstance(vitals, dict):
        raise Invalid("Vitals must be an object")
    clean = {k: number(vitals.get(k), k, *bounds) for k, bounds in VITALS.items()}
    unit = data.get("temperature_unit")
    if unit == "C":
        clean["temperature"] = number(vitals.get("temperature"), "temperature C", 30, 45) * 9 / 5 + 32
    elif unit == "F":
        clean["temperature"] = number(vitals.get("temperature"), "temperature F", 86, 113)
    else:
        raise Invalid("Specify temperature_unit C or F")
    if clean["diastolic_bp"] >= clean["systolic_bp"]:
        raise Invalid("Diastolic BP must be less than systolic BP")
    conditions = data.get("chronic_conditions")
    allowed = {"asthma","cancer","ckd","copd","chf","cad","diabetes_type1","diabetes_type2","esrd","htn","obesity","osa"}
    if not isinstance(conditions, list) or any(not isinstance(c, str) or c not in allowed for c in conditions):
        raise Invalid("Select valid chronic conditions (empty list if none)")
    flags = {}
    for key in ("immediate_triage", "arrival_by_ems"):
        val = data.get(key)
        if type(val) is not int or val not in (0, 1):
            raise Invalid(key + " must be 0 or 1")
        flags[key] = val
    return {"name": label.strip(), "age": int(age), "gender": gender,
            "specialty": specialty, "vitals": clean, "history": {"chronic_conditions": conditions}, **flags}

def model_predict(data):
    from app.ai.inference import predict_severity
    severity, probability, _ = predict_severity(data)
    return int(severity), float(probability)

@contextmanager
def transaction(path):
    db = sqlite3.connect(path, timeout=10, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    try:
        db.execute("BEGIN IMMEDIATE")
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()

def initialize(path):
    with transaction(path) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS doctors (
          id TEXT PRIMARY KEY, name TEXT NOT NULL, specialty TEXT NOT NULL,
          capacity INTEGER NOT NULL CHECK(capacity>0))""")
        db.execute("""CREATE TABLE IF NOT EXISTS cases (
          seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
          request_id TEXT UNIQUE NOT NULL, fingerprint TEXT NOT NULL,
          name TEXT NOT NULL, specialty TEXT NOT NULL, predicted INTEGER NOT NULL CHECK(predicted BETWEEN 0 AND 3),
          confidence REAL NOT NULL CHECK(confidence BETWEEN 0 AND 1),
          reviewed INTEGER CHECK(reviewed BETWEEN 0 AND 3), oxygen REAL NOT NULL,
          state TEXT NOT NULL CHECK(state IN ('review','waiting','assigned','in_treatment','completed')),
          doctor_id TEXT REFERENCES doctors(id), created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        db.execute("""CREATE TABLE IF NOT EXISTS events (
          seq INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT NOT NULL REFERENCES cases(id),
          action TEXT NOT NULL, created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        db.executemany("INSERT OR IGNORE INTO doctors VALUES (?,?,?,?)",
                       [(f"d{i}", name, spec, 2) for i, (name,spec) in enumerate([
                           ("Demo doctor A","general"),("Demo doctor B","cardiology"),
                           ("Demo doctor C","respiratory"),("Demo doctor D","trauma"),
                           ("Demo doctor E","general")], 1)])

def event(db, case_id, action):
    db.execute("INSERT INTO events(case_id,action) VALUES (?,?)", (case_id,action))

def dispatch(db):
    """Assign reviewed waiting cases by severity/FIFO; never cross specialties."""
    waiting = db.execute("SELECT * FROM cases WHERE state='waiting' ORDER BY reviewed DESC,seq").fetchall()
    for case in waiting:
        doctor = db.execute("""SELECT d.id, COUNT(c.id) AS load FROM doctors d
            LEFT JOIN cases c ON c.doctor_id=d.id AND c.state IN ('assigned','in_treatment')
            WHERE d.specialty=? GROUP BY d.id HAVING COUNT(c.id)<d.capacity
            ORDER BY CAST(COUNT(c.id) AS REAL)/d.capacity,d.id LIMIT 1""", (case["specialty"],)).fetchone()
        if doctor:
            db.execute("UPDATE cases SET state='assigned', doctor_id=? WHERE id=?", (doctor["id"],case["id"]))
            event(db,case["id"],"assigned")

def create_demo_app(db_path=None, predictor=None):
    import hashlib
    import json
    app = Flask(__name__, template_folder=str(ROOT / "demo_templates"))
    app.config.update(MAX_CONTENT_LENGTH=32*1024, JSON_SORT_KEYS=False)
    path = str(db_path or os.getenv("KYRO_DEMO_DB", str(ROOT / "demo_data" / "kyro.sqlite3")))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    initialize(path)
    predict = predictor or model_predict

    @app.errorhandler(Invalid)
    def invalid(exc):
        return jsonify(error=str(exc)), 409 if isinstance(exc, Conflict) else 400

    @app.errorhandler(HTTPException)
    def http_error(exc):
        return jsonify(error=exc.name), exc.code

    @app.errorhandler(Exception)
    def unexpected(exc):
        app.logger.error("Demo operation failed: %s", type(exc).__name__)
        return jsonify(error="Demo operation failed; no incomplete transaction was committed."), 500

    @app.after_request
    def headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'"
        return response

    def body():
        if not request.is_json:
            raise Invalid("Content-Type must be application/json")
        data = request.get_json()
        if not isinstance(data, dict):
            raise Invalid("Expected a JSON object")
        return data

    @app.get("/")
    def home():
        return render_template("dashboard.html")

    @app.get("/api/demo/state")
    def state():
        with transaction(path) as db:
            cases = [dict(r) for r in db.execute("""SELECT c.id,c.name,c.specialty,c.predicted,c.confidence,c.reviewed,c.oxygen,c.state,c.created,d.name AS doctor
              FROM cases c LEFT JOIN doctors d ON c.doctor_id=d.id
              ORDER BY CASE WHEN c.state='completed' THEN 1 ELSE 0 END,COALESCE(c.reviewed,c.predicted) DESC,c.seq""")]
            doctors = [dict(r) for r in db.execute("""SELECT d.*,COUNT(c.id) AS load FROM doctors d
              LEFT JOIN cases c ON c.doctor_id=d.id AND c.state IN ('assigned','in_treatment')
              GROUP BY d.id ORDER BY d.id""")]
            events = [dict(r) for r in db.execute("SELECT action,case_id,created FROM events ORDER BY seq DESC LIMIT 20")]
        return jsonify(cases=cases, doctors=doctors, events=events)

    @app.post("/api/demo/intake")
    def intake():
        data = body()
        if data.get("synthetic_only") is not True:
            raise Invalid("Confirm fictional data only")
        token = data.get("request_id")
        if not isinstance(token,str) or not 1 <= len(token) <= 100:
            raise Invalid("request_id required")
        normalized = normalize(data)
        fingerprint = hashlib.sha256(json.dumps(normalized,sort_keys=True).encode()).hexdigest()
        with transaction(path) as db:
            existing = db.execute("SELECT id,fingerprint FROM cases WHERE request_id=?", (token,)).fetchone()
            if existing:
                if existing["fingerprint"] != fingerprint:
                    raise Conflict("request_id already used with different data")
                return jsonify(id=existing["id"], duplicate=True)
        try:
            predicted, confidence = predict(normalized)
            if type(predicted) is not int or predicted not in range(4) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
                raise ValueError("Invalid model output")
        except Exception as exc:
            app.logger.error("Model unavailable: %s",type(exc).__name__)
            return jsonify(error="Model unavailable; no case was created."), 503
        with transaction(path) as db:
            existing = db.execute("SELECT id,fingerprint FROM cases WHERE request_id=?", (token,)).fetchone()
            if existing:
                if existing["fingerprint"] != fingerprint:
                    raise Conflict("request_id already used with different data")
                return jsonify(id=existing["id"], duplicate=True)
            case_id = str(uuid4())
            db.execute("""INSERT INTO cases(id,request_id,fingerprint,name,specialty,predicted,confidence,oxygen,state)
              VALUES (?,?,?,?,?,?,?,?,'review')""",(case_id,token,fingerprint,normalized["name"],normalized["specialty"],predicted,confidence,normalized["vitals"]["oxygen_saturation"]))
            event(db,case_id,"intake_pending_human_review")
        return jsonify(id=case_id,predicted=predicted,confidence=confidence), 201

    @app.post("/api/demo/cases/<case_id>/action")
    def action(case_id):
        data = body()
        op = data.get("action")
        with transaction(path) as db:
            case = db.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
            if not case:
                return jsonify(error="Case not found"),404
            if op == "review" and case["state"] == "review":
                severity = data.get("severity")
                if type(severity) is not int or severity not in range(4):
                    raise Invalid("Choose a simulated reviewed severity")
                db.execute("UPDATE cases SET reviewed=?,state='waiting' WHERE id=?",(severity,case_id))
            elif op == "start" and case["state"] == "assigned":
                db.execute("UPDATE cases SET state='in_treatment' WHERE id=?",(case_id,))
            elif op == "complete" and case["state"] == "in_treatment":
                db.execute("UPDATE cases SET state='completed' WHERE id=?",(case_id,))
            else:
                raise Conflict("Action not allowed in current state")
            event(db,case_id,op)
            dispatch(db)
        return jsonify(ok=True)

    return app

if __name__ == "__main__":
    create_demo_app().run(host="127.0.0.1",port=5000,debug=False)
