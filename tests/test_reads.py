import json
import os

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from api.routers import clock, events, field, fleet, health, plan
from core import reads
from tests.conftest import predict

app = FastAPI()
for r in (health.router, fleet.router, plan.router, events.router, clock.router):
    app.include_router(r)
client = TestClient(app)

FLEET_KEYS = {"unit_id", "station_code", "station", "risk_status", "sensor_issue", "display_status", "rul", "p_fail",
              "confidence", "reason", "top_sensors", "next_service_day", "needs_manager_decision", "failed",
              "data_source", "model_version"}
EVENT_KEYS = {"event_id", "type", "sim_day", "unit_id", "title", "detail", "severity", "payload"}
PLAN_KEYS = {"id", "unit_id", "station_code", "planned_day", "planned_date", "technician_id", "technician_name",
             "expected_saving", "reason", "state"}


def run(db, sql, **p):
    db.execute(text(sql), p)
    db.commit()


@pytest.fixture
def world(db):
    """Day 10 (a Thursday). EDS-01 red with an open sensor flag, EDS-02 watch with one, EDS-03 failed,
    EDS-04 red and planned, EDS-05 red with NO plan row (no crew slot), HIN-01 never predicted."""
    predict(db, "EDS-01", 0.95)
    predict(db, "EDS-02", 0.40, status="watch")
    predict(db, "EDS-03", 0.90)
    predict(db, "EDS-04", 0.85)
    predict(db, "EDS-05", 0.80)
    run(db, "UPDATE predictions SET top_sensors = CAST('[\"s8\", \"s13\"]' AS jsonb) WHERE unit_id = 'EDS-01'")
    run(db, "UPDATE units SET status = 'failed' WHERE id = 'EDS-03'")
    run(db, "INSERT INTO quality_flags (unit_id, sim_day, sensor, flag_type) VALUES "
            "('EDS-01', 8, 's8', 'sensor_offline'), ('EDS-02', 9, 's13', 'sensor_stuck')")
    run(db, "INSERT INTO plan_items (unit_id, planned_day, technician_id, crew, expected_saving, reason, state) VALUES "
            "('EDS-01', 10, 1, 0, 170000, 'At risk: 95%', 'planned'), ('EDS-04', 12, 2, 0, 150000, 'At risk: 85%', 'planned'), "
            "('EDS-02', 11, NULL, 0, 20000, 'Crew free late', 'needs_manager_decision')")
    return db


def by_id(units):
    return {u["unit_id"]: u for u in units}


# ---------------------------------------------------------------- fleet
def test_fleet_has_exactly_the_shape_the_dashboard_expects(world):
    body = client.get("/api/fleet").json()
    assert set(body) == {"sim_day", "clock", "units"} and body["sim_day"] == 10
    assert {"status", "speed_seconds_per_day", "sim_day"} <= set(body["clock"])
    assert len(body["units"]) == 6 and all(set(u) == FLEET_KEYS for u in body["units"])
    assert [u["unit_id"] for u in body["units"]] == sorted(u["unit_id"] for u in body["units"])


def test_fleet_values(world):
    u = by_id(client.get("/api/fleet").json()["units"])
    a = u["EDS-01"]
    assert (a["station_code"], a["station"], a["risk_status"], a["p_fail"]) == ("EDS", "Edson", "at_risk", 0.95)
    assert a["rul"] == {"low": 6.0, "likely": 10.0, "high": 14.0} and a["top_sensors"] == ["s8", "s13"]
    assert a["next_service_day"] == 10 and a["reason"] == "Fan speed drifting" and a["data_source"] == "live"
    assert a["needs_manager_decision"] is False and a["failed"] is False


def test_a_real_risk_is_never_hidden_behind_a_sensor_fault(world):
    u = by_id(client.get("/api/fleet").json()["units"])
    assert u["EDS-01"]["sensor_issue"] is True and u["EDS-01"]["display_status"] == "at_risk"  # D1
    assert u["EDS-02"]["sensor_issue"] is True and u["EDS-02"]["display_status"] == "sensor_issue"
    assert u["EDS-04"]["sensor_issue"] is False and u["EDS-04"]["display_status"] == "at_risk"
    run(world, "UPDATE quality_flags SET resolved_day = 12 WHERE unit_id = 'EDS-02'")  # resolved flags stop counting
    assert by_id(client.get("/api/fleet").json()["units"])["EDS-02"]["display_status"] == "watch"


def test_manager_decision_flag_covers_both_kinds(world):
    u = by_id(client.get("/api/fleet").json()["units"])
    assert u["EDS-02"]["needs_manager_decision"] is True   # a row marked needs_manager_decision
    assert u["EDS-05"]["needs_manager_decision"] is True   # red, and no crew slot ever got it
    assert u["EDS-04"]["needs_manager_decision"] is False and u["EDS-03"]["needs_manager_decision"] is False  # failed: no


def test_failed_unit_and_unit_without_a_prediction(world):
    u = by_id(client.get("/api/fleet").json()["units"])
    assert u["EDS-03"]["failed"] is True
    h = u["HIN-01"]
    assert (h["risk_status"], h["confidence"], h["p_fail"], h["rul"]) == ("healthy", "low", 0.0, {"low": 0, "likely": 0, "high": 0})
    assert "first prediction" in h["reason"] and h["next_service_day"] is None


def test_fleet_uses_the_newest_prediction_not_a_future_or_older_one(db):
    predict(db, "EDS-01", 0.30, status="watch", day=8)
    predict(db, "EDS-01", 0.95, status="at_risk", day=10)
    predict(db, "EDS-01", 0.10, status="healthy", day=15)  # ahead of the clock: ignored
    assert by_id(client.get("/api/fleet").json()["units"])["EDS-01"]["risk_status"] == "at_risk"


def test_fleet_survives_an_unseeded_database(db):
    run(db, "TRUNCATE sim_state, units, stations CASCADE")
    body = client.get("/api/fleet").json()
    assert body["units"] == [] and body["clock"]["sim_day"] == 0


# ---------------------------------------------------------------- unit detail
def test_unit_detail_has_history_sensors_events_calls_and_flags(world):
    predict(world, "EDS-01", 0.60, status="watch", day=9)
    run(world, "INSERT INTO readings (unit_id, sim_day, s8, s13) VALUES ('EDS-01', 9, 2388.1, NULL), ('EDS-01', 10, 2388.4, 2388.5)")
    run(world, "INSERT INTO events (sim_day, type, unit_id, title, detail, severity, payload) VALUES "
               "(10, 'status_change', 'EDS-01', 'At risk', 'x', 'warning', '{\"a\": 1}'), (10, 'status_change', 'EDS-02', 'Watch', 'y', 'info', '{}')")
    d = client.get("/api/units/EDS-01").json()
    assert FLEET_KEYS <= set(d) and set(d) - FLEET_KEYS == {"history", "sensors", "events", "calls", "quality_flags"}
    assert [h["sim_day"] for h in d["history"]] == [9, 10] and set(d["history"][0]) == {"sim_day", "rul_low", "rul_likely", "rul_high", "p_fail"}
    sensors = {s["sensor"]: s for s in d["sensors"]}
    assert len(sensors) == 14 and sensors["s8"]["label"] == "Fan speed"
    assert [p["sim_day"] for p in sensors["s8"]["points"]] == [9, 10]
    assert [p["sim_day"] for p in sensors["s13"]["points"]] == [10]  # a missing value is skipped, not zero
    assert [e["unit_id"] for e in d["events"]] == ["EDS-01"] and d["events"][0]["payload"] == {"a": 1}
    assert d["quality_flags"] == [{"id": 1, "unit_id": "EDS-01", "sim_day": 8, "sensor": "s8",
                                   "flag_type": "sensor_offline", "resolved_day": None}]
    assert d["calls"] == []


def test_unknown_unit_is_404(world):
    assert client.get("/api/units/XXX-99").status_code == 404


def seed_call(db, transcript, summary="Short.", dc=None, conv="conv_1", evaluation=None, unit="EDS-01"):
    run(db, "INSERT INTO call_requests (unit_id, technician_id, sim_day, state, attempt) VALUES (:u, 1, 10, 'done', 1)", u=unit)
    run(db, "INSERT INTO calls (call_request_id, conversation_id, language, transcript, summary, data_collection, "
            "evaluation, duration_secs, received_via) VALUES (1, :c, 'en', CAST(:t AS jsonb), :s, CAST(:d AS jsonb), "
            "CAST(:e AS jsonb), 24, 'webhook')",
        c=conv, t=json.dumps(transcript) if transcript is not None else None, s=summary,
        d=json.dumps(dc) if dc else None, e=json.dumps(evaluation) if evaluation else None)


TURNS = [{"role": "agent", "message": "Hi", "time_in_call_secs": 0,
          "tool_calls": [{"request_id": "r1", "tool_name": "submit_availability", "params_as_json": "{}"}],
          "tool_results": [{"request_id": "r1", "tool_name": "submit_availability", "result_value": "{}", "is_error": False}]}]


def test_call_record_passes_the_transcript_through_untouched(world):
    seed_call(world, TURNS, dc={"available_day": "Friday", "english_summary": "In English."},
              evaluation=[{"criteria_id": "greeted", "result": "success", "rationale": "yes"}])
    c = client.get("/api/calls/1").json()
    assert c["transcript"] == TURNS and c["summary"] == "Short." and c["summary_en"] == "In English."
    assert c["technician_name"] == "Anna Primary" and c["unit_id"] == "EDS-01" and c["duration_secs"] == 24
    assert c["evaluation"] == [{"criteria_id": "greeted", "result": "success", "rationale": "yes"}]
    assert client.get("/api/units/EDS-01").json()["calls"] == [c]


def test_call_without_report_card_omits_it_and_unfinished_calls_are_hidden(world):
    seed_call(world, TURNS)
    assert "evaluation" not in client.get("/api/calls/1").json()
    assert client.get("/api/calls/1").json()["summary_en"] == "Short."  # no english summary: plain one
    run(world, "INSERT INTO calls (call_request_id, conversation_id, language) VALUES (1, 'conv_pending', 'en')")  # phone linked, no webhook yet
    assert len(client.get("/api/units/EDS-01").json()["calls"]) == 1
    assert client.get("/api/calls/99").status_code == 404


# ---------------------------------------------------------------- plan and work orders
def test_plan_items(world):
    items = client.get("/api/plan").json()
    assert all(set(i) == PLAN_KEYS for i in items)
    assert [(i["unit_id"], i["planned_day"]) for i in items] == [("EDS-01", 10), ("EDS-02", 11), ("EDS-04", 12)]
    first, middle = items[0], items[1]
    assert (first["planned_date"], first["technician_name"], first["station_code"]) == ("2026-10-15", "Anna Primary", "EDS")
    assert middle["technician_id"] == 0 and middle["technician_name"] == "Unassigned" and middle["state"] == "needs_manager_decision"


def test_old_finished_work_drops_out_of_the_plan(world):
    run(world, "INSERT INTO plan_items (unit_id, planned_day, crew, expected_saving, reason, state) VALUES "
               "('EDS-05', 2, 0, 0, '', 'done'), ('EDS-05', 9, 0, 0, '', 'done')")
    days = [(i["unit_id"], i["planned_day"]) for i in client.get("/api/plan").json() if i["state"] == "done"]
    assert days == [("EDS-05", 9)]  # finished more than a week ago: gone; recent: kept


def test_work_orders_csv(world):
    r = client.get("/api/work-orders.csv")
    assert r.headers["content-type"].startswith("text/csv")
    assert r.headers["content-disposition"] == 'attachment; filename="work_orders_day_10.csv"'
    assert r.content.startswith(b"\xef\xbb\xbf")  # BOM so Excel reads UTF-8
    lines = r.content.decode("utf-8-sig").splitlines()
    assert lines[0] == "date,station,unit,technician,expected_saving,reason"
    assert len(lines) == 3 and lines[1].startswith("2026-10-15,EDS,EDS-01,Anna Primary,170000.0,")  # decisions excluded
    run(world, "UPDATE plan_items SET reason = 'say \"hi\", ok' WHERE unit_id = 'EDS-01'")
    assert '"say ""hi"", ok"' in client.get("/api/work-orders.csv").content.decode("utf-8-sig")  # real CSV quoting


# ---------------------------------------------------------------- events and stream
def test_events_log_and_after_id(world):
    for i in range(1, 6):
        run(world, "INSERT INTO events (sim_day, type, unit_id, title, detail, severity, payload) "
                   "VALUES (10, 'status_change', 'EDS-01', :t, '', 'info', '{}')", t=f"e{i}")
    allev = client.get("/api/events").json()
    assert [e["title"] for e in allev] == ["e1", "e2", "e3", "e4", "e5"] and all(set(e) == EVENT_KEYS for e in allev)
    assert [e["event_id"] for e in client.get("/api/events?after_id=3").json()] == [4, 5]
    assert client.get("/api/events?after_id=5").json() == []


def test_events_tail_is_capped_but_after_id_is_complete(world):
    run(world, "INSERT INTO events (sim_day, type, title, detail, severity, payload) "
               "SELECT 10, 'status_change', 'x', '', 'info', '{}' FROM generate_series(1, 320)")
    assert len(client.get("/api/events").json()) == reads.EVENT_TAIL
    assert client.get("/api/events").json()[-1]["event_id"] == 320  # the tail is the newest, oldest first
    assert len(client.get("/api/events?after_id=1").json()) == 319


def test_stream_resumes_and_never_floods(world):
    run(world, "INSERT INTO events (sim_day, type, title, detail, severity, payload) "
               "SELECT 10, 'status_change', 'x', '', 'info', '{}' FROM generate_series(1, 50)")
    assert events.start_cursor(None) == 30           # a new tab replays only the last 20
    assert events.start_cursor("40") == 20           # a reconnect resumes just before what it saw
    assert events.start_cursor("garbage") == 30 and events.start_cursor("5") == 0
    got = events.fetch_after(47)
    assert [e["event_id"] for e in got] == [48, 49, 50]
    assert events.frame(got[0]).startswith("id: 48\ndata: {") and events.frame(got[0]).endswith("\n\n")
    assert '"event:' not in events.frame(got[0])      # unnamed event: one onmessage handler gets everything


# ---------------------------------------------------------------- technicians, clock, health, extras
def test_technicians_show_who_is_online(db, monkeypatch):
    monkeypatch.setitem(field.CONNECTED, 2, 1)
    techs = client.get("/api/technicians").json()
    assert [t["name"] for t in techs] == ["Anna Primary", "Marc Tremblay", "Bo Backup", "Hana Solo"]
    assert set(techs[0]) == {"id", "name", "station_code", "shift", "language", "is_backup", "online", "field_page_id"}
    assert [t["online"] for t in techs] == [False, True, False, False]
    assert techs[2]["is_backup"] is True and techs[1]["language"] == "fr" and techs[3]["station_code"] == "HIN"


def listen_for(channel):
    conn = psycopg.connect(os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://"), autocommit=True)
    conn.execute(f"LISTEN {channel}")
    return conn


def test_clock_controls(db):
    assert client.post("/api/clock", json={"action": "play"}).json()["status"] == "running"
    assert client.post("/api/clock", json={"action": "pause"}).json()["status"] == "paused"
    assert client.post("/api/clock", json={"action": "speed", "speed_seconds_per_day": 2}).json()["speed_seconds_per_day"] == 2.0
    assert client.post("/api/clock", json={"action": "speed", "speed_seconds_per_day": 99}).json()["speed_seconds_per_day"] == 5.0
    assert client.post("/api/clock", json={"action": "speed", "speed_seconds_per_day": 0}).json()["speed_seconds_per_day"] == 0.25
    c = client.get("/api/clock").json()
    assert c["sim_day"] == 10 and c["weekday"] == "Thursday" and c["calendar_date"] == "2026-10-15"
    assert client.post("/api/clock", json={"action": "speed"}).status_code == 422
    assert client.post("/api/clock", json={"action": "teleport"}).status_code == 422


def test_clock_advance_tells_the_simulator(db):
    conn = listen_for("clock_cmd")
    try:
        client.post("/api/clock", json={"action": "advance", "days": 5})
        client.post("/api/clock", json={"action": "advance"})
        client.post("/api/clock", json={"action": "advance", "days": 99999})
        got = [n.payload for n in conn.notifies(timeout=2, stop_after=3)]
    finally:
        conn.close()
    assert got == ["advance:5", "advance:1", "advance:1000"]


def test_clock_reset_runs_the_seed(db, monkeypatch):
    calls = []
    monkeypatch.setattr(clock, "reset_demo", lambda: calls.append(1) or {"units": 100})
    assert client.post("/api/clock", json={"action": "reset"}).status_code == 200 and calls == [1]

    def broken():
        raise RuntimeError("NASA data not found")
    monkeypatch.setattr(clock, "reset_demo", broken)
    r = client.post("/api/clock", json={"action": "reset"})
    assert r.status_code == 500 and "NASA data not found" in r.json()["detail"]


def test_the_seed_script_can_be_loaded_by_the_reset_helper():
    import importlib.util
    from core.admin_ops import SEED_PATH
    spec = importlib.util.spec_from_file_location("pipeguard_seed_check", SEED_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # imports cleanly; reseed() itself needs the NASA data files
    assert callable(mod.reseed) and callable(mod.tuned_defaults)
    assert mod.tuned_defaults() == (0.3, 21)  # David's item 6: the tuned values, not the 0.5 / 14 placeholders


def test_health_reports_what_the_preflight_needs(world):
    h = client.get("/api/health").json()
    assert h["status"] == "ok" and h["ok"] is True and h["database"] is True and h["mock_api"] is False
    assert h["sim_day"] == 10 and h["engine_lag_days"] == 0 and h["data_source"] == {"live": 5, "fallback": 0}
    assert {"elevenlabs_configured", "webhook_secret_set", "voice_tool_secret_set", "admin_token_set",
            "simulator_tick_age_secs", "model_version"} <= set(h)
    run(world, "UPDATE sim_state SET sim_day = 14")
    assert client.get("/api/health").json()["engine_lag_days"] == 4  # the engine is four days behind the simulator


def test_health_says_degraded_with_503_when_the_database_fails(monkeypatch):
    def boom(s):
        raise RuntimeError("db down")
    monkeypatch.setattr(reads, "health", boom)
    r = client.get("/api/health")
    assert r.status_code == 503 and r.json()["ok"] is False and r.json()["database"] is False


def test_trend_feedback_stats_and_model(world):
    predict(world, "EDS-01", 0.9, day=9)
    t = client.get("/api/fleet/trend").json()
    assert t == [{"sim_day": 9, "needing_attention": 1}, {"sim_day": 10, "needing_attention": 4}]  # EDS-01, 03, 04, 05 red on day 10
    assert client.get("/api/feedback/stats").json() == {"total": 0, "confirmed": 0}
    run(world, "INSERT INTO feedback (unit_id, technician_id, verdict, sim_day) VALUES "
               "('EDS-01', 1, 'confirmed_wear', 10), ('EDS-02', 1, 'looks_fine', 10), ('EDS-04', 1, 'part_replaced', 10)")
    assert client.get("/api/feedback/stats").json() == {"total": 3, "confirmed": 2}
    m = client.get("/api/model").json()
    assert m == {"rmse": 14.3, "baseline_rmse": 34.9, "model_version": "v1"}
