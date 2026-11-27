import concurrent.futures
import pytest
from demo import create_demo_app, normalize, Invalid

def payload(token="one", **overrides):
    d=dict(name="Fictional case",age=42,gender="male",specialty="cardiology",
           temperature_unit="C",vitals=dict(heart_rate=80,systolic_bp=120,diastolic_bp=80,
           respiratory_rate=16,temperature=37,pain_scale=2,oxygen_saturation=98),
           chronic_conditions=[],immediate_triage=0,arrival_by_ems=0,
           synthetic_only=True,request_id=token)
    d.update(overrides)
    return d

@pytest.fixture
def app(tmp_path):
    return create_demo_app(tmp_path/"demo.db", predictor=lambda data:(2,.75))

def intake(c,token):
    r=c.post("/api/demo/intake",json=payload(token))
    assert r.status_code==201
    return r.json["id"]

def action(c,id,op,**kwargs):
    return c.post(f"/api/demo/cases/{id}/action",json=dict(action=op,**kwargs))

def state(c):
    return c.get("/api/demo/state").json

def test_temperature():
    assert normalize(payload())["vitals"]["temperature"] == pytest.approx(98.6)
    d=payload(temperature_unit="F");d["vitals"]["temperature"]=98.6
    assert normalize(d)["vitals"]["temperature"] == pytest.approx(98.6)

@pytest.mark.parametrize("key,value",[("age",-1),("age",True),("gender","bad"),("temperature_unit","X"),("vitals",{}),("chronic_conditions",None)])
def test_validation(key,value):
    with pytest.raises(Invalid): normalize(payload(**{key:value}))

def test_lifecycle_and_capacity(app):
    with app.test_client() as c:
        ids=[intake(c,str(i)) for i in range(4)]
        assert all(x["state"]=="review" for x in state(c)["cases"])
        for id,severity in zip(ids,[0,1,1,3]):
            assert action(c,id,"review",severity=severity).status_code==200
        s=state(c); by_id={x["id"]:x for x in s["cases"]}
        assert by_id[ids[2]]["state"]=="waiting"
        assert by_id[ids[3]]["state"]=="waiting"
        assert action(c,ids[0],"complete").status_code==409
        assert action(c,ids[0],"start").status_code==200
        assert action(c,ids[0],"complete").status_code==200
        by_id={x["id"]:x for x in state(c)["cases"]}
        assert by_id[ids[3]]["state"]=="assigned"
        assert by_id[ids[2]]["state"]=="waiting"
        assert by_id[ids[0]]["state"]=="completed"
        assert by_id[ids[3]]["doctor"]=="Demo doctor B"

def test_idempotent_and_conflict(app):
    with app.test_client() as c:
        id=intake(c,"same")
        r=c.post("/api/demo/intake",json=payload("same"))
        assert r.status_code==200 and r.json["id"]==id
        assert c.post("/api/demo/intake",json=payload("same",age=43)).status_code==409
        assert len(state(c)["cases"])==1

def test_concurrent_review(app):
    with app.test_client() as c: ids=[intake(c,str(i)) for i in range(8)]
    def review(id):
        with app.test_client() as c: return action(c,id,"review",severity=3).status_code
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        assert list(pool.map(review,ids))==[200]*8
    with app.test_client() as c:
        s=state(c)
        assert sum(x["state"]=="assigned" for x in s["cases"])==2
        assert sum(x["state"]=="waiting" for x in s["cases"])==6
        assert all(x["load"]<=x["capacity"] for x in s["doctors"])

def test_fictional_confirmation_and_dashboard(app):
    with app.test_client() as c:
        assert c.get("/").status_code==200
        assert c.post("/api/demo/intake",json=payload(synthetic_only=False)).status_code==400

def test_model_failure_no_case(tmp_path):
    def fail(data): raise RuntimeError("model failure")
    app=create_demo_app(tmp_path/"failure.db",predictor=fail)
    with app.test_client() as c:
        assert c.post("/api/demo/intake",json=payload()).status_code==503
        assert state(c)["cases"]==[]

def test_committed_model_smoke(tmp_path):
    app=create_demo_app(tmp_path/"actual.db")
    with app.test_client() as c:
        r=c.post("/api/demo/intake",json=payload())
        assert r.status_code==201
        assert 0<=r.json["predicted"]<=3
        assert 0<=r.json["confidence"]<=1
