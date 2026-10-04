import json

import numpy as np
import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from api.routers import admin, simulate, testmode
from core import alerts, demo_call, impact
from core.replan import replan
from tests.conftest import predict

app = FastAPI()
for r in (testmode.router, admin.router, simulate.router):
    app.include_router(r)
client = TestClient(app)


def count(db, sql):
    return db.execute(text(sql)).scalar()


def run(db, sql, **p):
    db.execute(text(sql), p)
    db.commit()


# ---------------------------------------------------------------- auth
def test_admin_token_is_enforced_only_when_configured(db, monkeypatch):
    from api import deps
    assert client.get("/api/testmode/faults").status_code == 200  # dev: no token configured
    monkeypatch.setattr(deps.settings, "admin_token", "s3cret")
    assert client.get("/api/testmode/faults").status_code == 401
    assert client.get("/api/testmode/faults", headers={"X-Admin-Token": "nope"}).status_code == 401
    assert client.get("/api/testmode/faults", headers={"X-Admin-Token": "s3cret"}).status_code == 200
    assert client.post("/api/admin/reset").status_code == 401   # the reset is protected too
    assert client.post("/api/admin/simulate-call").status_code == 401


# ---------------------------------------------------------------- test mode faults
FAULT = {"unit_id": "EDS-01", "sensor": "s8", "type": "dead"}
FAULT_KEYS = {"id", "unit_id", "sensor", "type", "start_day", "end_day", "source"}


def test_fault_toggle_lifecycle(db):
    f = client.post("/api/testmode/faults", json=FAULT).json()
    assert set(f) == FAULT_KEYS and (f["start_day"], f["end_day"], f["source"]) == (10, None, "toggle")
    assert client.post("/api/testmode/faults", json=FAULT).json()["id"] == f["id"]   # second click: still one fault
    assert client.post("/api/testmode/faults", json={**FAULT, "type": "stuck"}).json()["id"] == f["id"]
    assert count(db, "SELECT count(*) FROM faults") == 1
    assert [x["id"] for x in client.get("/api/testmode/faults").json()] == [f["id"]]
    run(db, "UPDATE sim_state SET sim_day = 12")
    ended = client.delete(f"/api/testmode/faults/{f['id']}").json()
    assert ended["end_day"] == 12
    assert client.delete(f"/api/testmode/faults/{f['id']}").json()["end_day"] == 12   # ending twice is fine
    assert client.get("/api/testmode/faults").json() == []
    assert client.post("/api/testmode/faults", json=FAULT).json()["id"] != f["id"]   # can be toggled on again


def test_fault_validation(db):
    assert client.post("/api/testmode/faults", json={**FAULT, "unit_id": "XXX-99"}).status_code == 422
    assert client.post("/api/testmode/faults", json={**FAULT, "sensor": "s1"}).status_code == 422   # flat sensor, not modelled
    assert client.post("/api/testmode/faults", json={**FAULT, "type": "melted"}).status_code == 422
    assert client.delete("/api/testmode/faults/999").status_code == 404
    run(db, "UPDATE units SET status = 'failed' WHERE id = 'EDS-01'")
    assert client.post("/api/testmode/faults", json=FAULT).json() == {"ok": True, "ignored": "unit already failed"}
    assert count(db, "SELECT count(*) FROM faults") == 0


# ---------------------------------------------------------------- reset
def test_reset_runs_the_seed_and_reports_failures(db, monkeypatch):
    calls = []
    monkeypatch.setattr(admin, "reset_demo", lambda: calls.append(1) or {"units": 100})
    assert client.post("/api/admin/reset").json() == {"ok": True} and calls == [1]

    def broken():
        raise RuntimeError("NASA data not found")
    monkeypatch.setattr(admin, "reset_demo", broken)
    r = client.post("/api/admin/reset")
    assert r.status_code == 500 and "NASA data not found" in r.json()["detail"]


# ---------------------------------------------------------------- Impact simulation (synthetic cross-fitted predictions)
@pytest.fixture
def oof(tmp_path, monkeypatch):
    """100 engines of the same shape as ml/artifacts/oof_predictions.parquet, so the real simulator runs."""
    rng = np.random.default_rng(7)
    rows = []
    for e in range(1, 101):
        life = int(rng.integers(130, 330))
        for c in range(1, life + 1):
            rul = life - c
            capped = min(125, rul)
            likely = max(0.0, capped + rng.normal(0, 6))
            rows.append((e, "", c, life, rul, capped, e % 5, max(0.0, likely - 12), likely, likely + 12))
    pd.DataFrame(rows, columns=["source_engine", "unit_id", "cycle", "max_cycle", "rul_true", "rul_capped", "fold",
                                "rul_low", "rul_likely", "rul_high"]).to_parquet(tmp_path / "oof_predictions.parquet")
    monkeypatch.setattr(impact.settings, "model_dir", str(tmp_path))
    monkeypatch.setattr(impact, "_oof", None)
    impact._impact_cached.cache_clear()
    yield
    monkeypatch.setattr(impact, "_oof", None)


def test_simulate_returns_the_three_policies(db, oof):
    body = {"crews_per_station": 2, "cost_breakdown": 200000, "cost_service": 20000, "threshold": None, "horizon_days": None}
    r = client.post("/api/simulate", json=body)
    assert r.status_code == 200
    out = r.json()
    assert {"policies", "default", "tuned", "headline", "computed_ms"} <= set(out)
    assert [p["policy"] for p in out["policies"]] == ["run_to_failure", "fixed_schedule", "pipeguard"]
    assert {"breakdowns", "planned_services", "wasted_services", "crew_days", "total_cost"} <= set(out["policies"][0])
    assert {"detected", "actioned", "total", "lead_days", "text"} <= set(out["headline"]) and out["headline"]["total"] == 100
    assert {"threshold", "horizon_days", "total_cost"} <= set(out["tuned"])


def test_simulate_costs_react_to_the_sliders(db, oof):
    base = {"crews_per_station": 2, "cost_service": 20000, "threshold": None, "horizon_days": None}
    cheap = client.post("/api/simulate", json={**base, "cost_breakdown": 50000}).json()
    dear = client.post("/api/simulate", json={**base, "cost_breakdown": 500000}).json()
    rtf = lambda o: next(p for p in o["policies"] if p["policy"] == "run_to_failure")["total_cost"]  # noqa: E731
    assert rtf(dear) > rtf(cheap) * 2          # breakdowns cost more, so running to failure costs much more


def test_simulate_rejects_bad_input_and_says_503_without_data(db, monkeypatch, tmp_path):
    assert client.post("/api/simulate", json={"crews_per_station": "many"}).status_code == 422
    monkeypatch.setattr(impact.settings, "model_dir", str(tmp_path))   # empty directory
    monkeypatch.setattr(impact, "_oof_paths", lambda: [tmp_path / "nope.parquet"])
    monkeypatch.setattr(impact, "_oof", None)
    r = client.post("/api/simulate", json={"crews_per_station": 2, "cost_breakdown": 200000, "cost_service": 20000})
    assert r.status_code == 503 and "not available" in r.json()["detail"]
    assert client.get("/api/impact").status_code == 503
    assert client.post("/api/admin/tune").status_code == 503


def test_impact_is_cached_until_the_tuned_setting_changes(db, oof):
    run(db, "INSERT INTO engine_params (id, threshold, horizon_days) VALUES (1, 0.3, 21)")
    first = client.get("/api/impact").json()
    assert client.get("/api/impact").json() == first                       # cached: identical, computed_ms included
    assert impact._impact_cached.cache_info().hits >= 1
    run(db, "UPDATE engine_params SET threshold = 0.6")
    assert client.get("/api/impact").json()["policies"]                    # a new tuned setting recomputes


def test_tune_stores_the_winner_in_engine_params(db, oof):
    run(db, "INSERT INTO engine_params (id, threshold, horizon_days) VALUES (1, 0.5, 14)")
    out = client.post("/api/admin/tune").json()
    assert out["threshold"] in (0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8) and out["horizon_days"] in (7, 14, 21)
    row = db.execute(text("SELECT threshold, horizon_days, tuned_at IS NOT NULL FROM engine_params")).one()
    assert (row[0], row[1], row[2]) == (out["threshold"], out["horizon_days"], True)


# ---------------------------------------------------------------- simulate-call
@pytest.fixture
def fast(monkeypatch):
    monkeypatch.setattr(demo_call, "STEP_SECS", 0)
    monkeypatch.setattr(demo_call, "RECORDED", demo_call.RECORDED.with_name("no_such_recording.json"))


@pytest.fixture
def planned(db):
    for u, p in (("EDS-01", .95), ("EDS-02", .90), ("EDS-03", .85)):
        predict(db, u, p)
    replan(db, emit=False)
    db.commit()
    return db


def event_types(db):
    return db.execute(text("SELECT type FROM events ORDER BY id")).scalars().all()


def test_simulated_call_runs_the_same_steps_as_a_real_one(planned, fast):
    before = dict(planned.execute(text("SELECT unit_id, planned_day FROM plan_items")).all())
    r = client.post("/api/admin/simulate-call")
    assert r.status_code == 200 and r.json()["unit_id"] == "EDS-01" and r.json()["staged"] is True
    assert event_types(planned)[-5:] == ["call_requested", "call_answered", "constraint_added", "plan_changed", "call_summary"]
    after = dict(planned.execute(text("SELECT unit_id, planned_day FROM plan_items")).all())
    assert after["EDS-01"] == before["EDS-01"] + 1                       # moved one day, visibly
    cr = planned.execute(text("SELECT id, state, technician_id FROM call_requests")).one()
    assert cr[1] == "done"                                               # finished through the state machine
    con = planned.execute(text("SELECT call_request_id, source, technician_id FROM constraints")).one()
    assert tuple(con) == (cr[0], "voice", cr[2])                         # the real voice tool saved it, linked to the call
    call = planned.execute(text("SELECT received_via, conversation_id, duration_secs FROM calls")).one()
    assert tuple(call) == ("simulated", f"conv_sim_{cr[0]}", 24)
    rec = client.get  # the dashboard reads it back through the normal call record
    from api.routers import fleet
    app2 = FastAPI()
    app2.include_router(fleet.router)
    c = TestClient(app2).get("/api/calls/1").json()
    assert c["received_via"] == "simulated" and c["unit_id"] == "EDS-01"
    assert c["transcript"][2]["tool_calls"][0]["tool_name"] == "submit_availability"
    assert json.loads(c["transcript"][2]["tool_results"][0]["result_value"])["ok"] is True   # the tool's real answer
    assert "cannot service EDS-01" in c["summary_en"] and rec


def test_simulated_call_twice_is_safe(planned, fast):
    client.post("/api/admin/simulate-call")
    client.post("/api/admin/simulate-call")
    assert count(planned, "SELECT count(*) FROM calls") == 2
    assert count(planned, "SELECT count(*) FROM call_requests WHERE state = 'done'") == 2


def test_simulated_call_for_a_chosen_unit_and_technician(planned, fast):
    r = client.post("/api/admin/simulate-call", json={"unit_id": "eds 2", "technician_id": 2})
    assert r.json()["unit_id"] == "EDS-02"
    assert count(planned, "SELECT technician_id FROM call_requests") == 2


def test_nothing_to_simulate_is_a_clear_422(db, fast):
    r = client.post("/api/admin/simulate-call")
    assert r.status_code == 422 and "no planned service" in r.json()["detail"]
    run(db, "INSERT INTO plan_items (unit_id, planned_day, crew, expected_saving, reason, state) VALUES ('EDS-01', 11, 0, 0, '', 'planned')")
    assert client.post("/api/admin/simulate-call", json={"unit_id": "EDS-02"}).status_code == 422
    assert client.post("/api/admin/simulate-call", json={"unit_id": "banana"}).status_code == 422


def test_ring_mode_only_rings_the_phone_page(planned, fast):
    r = client.post("/api/admin/simulate-call", json={"ring": True}).json()
    assert r["field_page"] == "/field/slug-anna" and "staged" not in r
    assert event_types(planned)[-1] == "call_requested"
    assert count(planned, "SELECT state FROM call_requests") == "ringing"   # a human answers it
    assert count(planned, "SELECT count(*) FROM constraints") == 0


def test_a_recorded_call_is_replayed_through_the_same_code(planned, fast, tmp_path, monkeypatch):
    rec = {"type": "post_call_transcription", "data": {
        "conversation_id": "conv_real_recording", "transcript": [
            {"role": "agent", "message": "Hello Sam", "time_in_call_secs": 0},
            {"role": "agent", "message": "", "time_in_call_secs": 8, "tool_calls": [
                {"request_id": "x", "tool_name": "submit_availability", "tool_has_been_called": True,
                 "params_as_json": json.dumps({"unit_id": "EDS-01", "technician_id": 1, "earliest_day_text": "Monday"})}],
             "tool_results": [{"request_id": "x", "tool_name": "submit_availability", "is_error": False,
                               "result_value": json.dumps({"ok": True, "say": "Got it."})}]}],
        "metadata": {"call_duration_secs": 31},
        "analysis": {"transcript_summary": "Recorded call.", "evaluation_criteria_results_list": [
            {"criteria_id": "greeted", "result": "success", "rationale": "yes"}]}}}
    path = tmp_path / "recorded_call.json"
    path.write_text(json.dumps(rec))
    monkeypatch.setattr(demo_call, "RECORDED", path)
    client.post("/api/admin/simulate-call")
    row = planned.execute(text("SELECT conversation_id, transcript, evaluation, duration_secs, received_via FROM calls")).one()
    assert row[0].startswith("conv_sim_") and row[0] != "conv_real_recording"      # cannot collide on a repeat
    assert row[1] == rec["data"]["transcript"]                                      # stored exactly as recorded
    assert row[2] == [{"criteria_id": "greeted", "result": "success", "rationale": "yes"}] and row[3:] == (31, "simulated")
    assert planned.execute(text("SELECT earliest_day FROM constraints")).scalar() == 14  # "Monday" from the recording, day 14
