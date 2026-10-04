import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from api.routers import voice
from core import alerts
from core.replan import replan
from tests.conftest import predict

app = FastAPI()
app.include_router(voice.router)
client = TestClient(app)
URL = "/api/voice/tools"


def count(db, sql):
    return db.execute(text(sql)).scalar()


def run(db, sql, **p):
    db.execute(text(sql), p)
    db.commit()


def planned(db, unit):
    return db.execute(text("SELECT planned_day FROM plan_items WHERE unit_id = :u"), {"u": unit}).scalar()


@pytest.fixture
def plan(db):
    """Three at-risk units at EDS (two crews a day) and a baseline plan. Today is day 10, a Thursday."""
    predict(db, "EDS-01", 0.95)
    predict(db, "EDS-02", 0.90)
    predict(db, "EDS-03", 0.85)
    replan(db, emit=False)
    # Calls the technicians have answered: the plan only changes during one of these.
    run(db, "INSERT INTO call_requests (unit_id, technician_id, sim_day, state, attempt) VALUES "
            "('EDS-01', 1, 10, 'answered', 1), ('EDS-01', 2, 10, 'answered', 1), ('EDS-04', 1, 10, 'answered', 1)")
    return db


def avail(text_, unit="EDS-01", tech=1, **extra):
    return client.post(f"{URL}/submit-availability",
                       json={"unit_id": unit, "technician_id": tech, "earliest_day_text": text_, **extra})


# ---------------------------------------------------------------- replan
def test_replan_writes_plan_with_technicians_and_keeps_done_history(db):
    predict(db, "EDS-01", 0.95)
    predict(db, "EDS-02", 0.90)
    db.execute(text("INSERT INTO plan_items (unit_id, planned_day, crew, expected_saving, reason, state) "
                    "VALUES ('EDS-05', 8, 0, 0, '', 'done')"))
    db.commit()
    result = replan(db)
    db.commit()
    rows = db.execute(text("SELECT unit_id, planned_day, technician_id, state FROM plan_items "
                           "ORDER BY unit_id")).all()
    assert rows == [("EDS-01", 10, 1, "planned"), ("EDS-02", 10, 2, "planned"), ("EDS-05", 8, None, "done")]
    assert result.changed and count(db, "SELECT count(*) FROM events WHERE type = 'plan_changed'") == 1
    replan(db)  # nothing new: same plan, no second event
    assert count(db, "SELECT count(*) FROM events WHERE type = 'plan_changed'") == 1


# ---------------------------------------------------------------- submit-availability
def test_not_before_friday_moves_unit_and_shifts_the_next_one(plan):
    r = avail("Friday", note="crew busy until then")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["say"] == "Got it. EDS-01 moves to Friday. EDS-03 also moves to Thursday."
    assert planned(plan, "EDS-01") == 11 and planned(plan, "EDS-03") == 10
    row = plan.execute(text("SELECT unit_id, technician_id, earliest_day, source FROM constraints")).one()
    assert tuple(row) == ("EDS-01", 1, 11, "voice")
    ev = plan.execute(text("SELECT type FROM events WHERE type IN ('constraint_added', 'plan_changed') "
                           "ORDER BY id")).scalars().all()
    assert ev == ["constraint_added", "plan_changed"]


def test_same_call_twice_changes_nothing_twice(plan):
    avail("Friday")
    r = avail("Friday")
    assert r.json() == {"ok": True, "say": "Got it. EDS-01 is already planned for Friday, so nothing changes.",
                        "earliest_day": 11}
    assert count(plan, "SELECT count(*) FROM constraints") == 1
    assert count(plan, "SELECT count(*) FROM events WHERE type = 'constraint_added'") == 1
    assert count(plan, "SELECT count(*) FROM events WHERE type = 'plan_changed'") == 1


def test_constraint_is_linked_to_the_answered_call(plan):
    cid = count(plan, "SELECT id FROM call_requests WHERE unit_id = 'EDS-01' AND technician_id = 1")
    avail("Friday")
    assert count(plan, "SELECT call_request_id FROM constraints") == cid


def test_french_technician_is_answered_in_french(plan):
    r = avail("vendredi", tech=2)  # Marc speaks French
    assert r.json()["say"].startswith("C'est noté. EDS-01 est décalé à vendredi.")


def test_unit_and_technician_ids_from_the_llm_are_cleaned_up(plan):
    r = avail("tomorrow", unit="eds 1", tech="1")
    assert r.json()["ok"] is True and planned(plan, "EDS-01") == 11


def test_unclear_day_asks_again_and_saves_nothing(plan):
    r = avail("whenever").json()
    assert r["ok"] is False and "Which day" in r["say"]
    assert avail("peut-être", tech=2).json()["say"].startswith("Désolé")
    assert count(plan, "SELECT count(*) FROM constraints") == 0


def test_too_late_for_the_unit_goes_to_a_manager(plan):
    r = avail("in 9 days").json()  # past this week's plan window
    assert r["ok"] is True and "flagged it for a manager" in r["say"]
    assert planned(plan, "EDS-01") is None
    alert = plan.execute(text("SELECT severity, title, payload FROM events WHERE type = 'manager_alert'")).one()
    assert alert[0] == "critical" and alert[1] == "Manager decision needed" and alert[2]["reason"] == "needs_manager_decision"
    avail("in 9 days")  # the agent repeats itself: still one alert for the manager
    assert count(plan, "SELECT count(*) FROM events WHERE type = 'manager_alert'") == 1


def test_unit_not_in_the_plan_is_just_noted(plan):
    r = avail("Friday", unit="EDS-04").json()  # healthy, never planned
    assert r["ok"] is True and r["say"] == "Noted. EDS-04 won't be scheduled before Friday."


def test_if_replan_breaks_the_constraint_is_still_saved(plan, monkeypatch):
    import core.replan

    def boom(*a, **k):
        raise RuntimeError("scheduler unavailable")
    monkeypatch.setattr(core.replan, "replan", boom)
    r = avail("Friday").json()
    assert r["ok"] is True and "plan will update shortly" in r["say"]
    assert count(plan, "SELECT count(*) FROM constraints") == 1


# ---------------------------------------------------------------- never a 4xx or 5xx for a person on the line
@pytest.mark.parametrize("path", ["unit-status", "submit-availability", "field-report", "feedback"])
@pytest.mark.parametrize("body", [{}, {"unit_id": None}, {"unit_id": "XXX-99"}, [1, 2], "text", 5])
def test_garbage_input_still_gets_200_and_a_sentence(db, path, body):
    r = client.post(f"{URL}/{path}", json=body)
    assert r.status_code == 200
    assert r.json()["ok"] is False and r.json()["say"]


def test_not_json_at_all_is_still_200(db):
    r = client.post(f"{URL}/submit-availability", content=b"not json", headers={"content-type": "text/plain"})
    assert r.status_code == 200 and r.json()["ok"] is False


# ---------------------------------------------------------------- other tools
def test_unit_status_reads_plan_and_risk_in_the_technicians_language(plan):
    r = client.post(f"{URL}/unit-status", json={"unit_id": "EDS-01", "technician_id": 1}).json()
    assert r["say"] == "EDS-01 is at risk. About 6 to 14 days left. It is planned for Thursday."
    r = client.post(f"{URL}/unit-status", json={"unit_id": "EDS-01", "technician_id": 2}).json()
    assert r["say"] == "EDS-01 est à risque. Environ 6 à 14 jours restants. Il est prévu pour jeudi."
    assert "no prediction" in client.post(f"{URL}/unit-status", json={"unit_id": "EDS-05"}).json()["say"]


def test_feedback_tool_validates_and_is_idempotent(plan):
    ok = {"unit_id": "EDS-01", "technician_id": 1, "verdict": "part_replaced", "note": "new bearing"}
    assert client.post(f"{URL}/feedback", json=ok).json() == {"ok": True, "say": "Thanks, I've recorded that."}
    client.post(f"{URL}/feedback", json=ok)
    assert count(plan, "SELECT count(*) FROM feedback") == 1
    assert plan.execute(text("SELECT life_start_day FROM units WHERE id = 'EDS-01'")).scalar() == 11
    bad = client.post(f"{URL}/feedback", json={**ok, "verdict": "maybe"}).json()
    assert bad["ok"] is False and "Is the wear confirmed" in bad["say"]


def test_field_report_is_stored_once(plan):
    body = {"unit_id": "EDS-02", "technician_id": 1, "note": "bearing noise on the left side"}
    assert client.post(f"{URL}/field-report", json=body).json()["ok"] is True
    client.post(f"{URL}/field-report", json=body)
    assert count(plan, "SELECT count(*) FROM events WHERE title = 'Field report'") == 1
    assert client.post(f"{URL}/field-report", json={**body, "note": ""}).json()["ok"] is False


# ---------------------------------------------------------------- auth
def test_tool_secret_is_enforced_only_when_configured(plan, monkeypatch):
    monkeypatch.setattr(voice.settings, "voice_tool_secret", "s3cret")
    body = {"unit_id": "EDS-01", "technician_id": 1}
    assert client.post(f"{URL}/unit-status", json=body).status_code == 401
    assert client.post(f"{URL}/unit-status", json=body, headers={"Authorization": "Bearer nope"}).status_code == 401
    assert client.post(f"{URL}/unit-status", json=body, headers={"Authorization": "Bearer s3cret"}).status_code == 200


# ---------------------------------------------------------------- the rules from guide 8.5
def test_no_plan_change_without_an_answered_call_about_that_unit(plan):
    for unit, tech in (("EDS-02", 1), ("EDS-01", 3), ("EDS-01", None)):   # no call / someone else's call / no technician
        r = avail("Friday", unit=unit, tech=tech).json()
        assert r["ok"] is False and "no active call" in r["say"], (unit, tech)
    assert avail("vendredi", unit="EDS-02", tech=2).json()["say"].startswith("Désolé, je ne peux pas modifier le plan")
    assert count(plan, "SELECT count(*) FROM constraints") == 0 and planned(plan, "EDS-01") == 10


def test_a_call_the_phone_already_hung_up_on_still_counts(plan):
    run(plan, "UPDATE call_requests SET state = 'done' WHERE unit_id = 'EDS-01' AND technician_id = 1")
    assert avail("Friday").json()["ok"] is True


def test_a_ringing_call_that_nobody_answered_does_not_count(plan):
    run(plan, "UPDATE call_requests SET state = 'ringing' WHERE unit_id = 'EDS-01' AND technician_id = 1")
    assert avail("Friday").json()["ok"] is False


def test_the_day_rules(plan):
    assert avail("Thursday").json()["earliest_day"] == 10          # today's weekday means today
    assert avail("2026-10-16").json()["earliest_day"] == 11        # ISO date, Friday
    assert avail("2026-10-01").json()["earliest_day"] == 10        # a day already gone means today
    assert count(plan, "SELECT count(*) FROM constraints") == 2  # "Thursday" and the past date are the same day: stored once


def test_feedback_moves_the_threshold_through_olises_rule(plan):
    run(plan, "INSERT INTO engine_params (id, threshold, horizon_days) VALUES (1, 0.5, 14)")
    for unit in ("EDS-01", "EDS-02"):
        body = {"unit_id": unit, "technician_id": 1, "verdict": "looks_fine"}
        assert client.post(f"{URL}/feedback", json=body).json()["ok"] is True
    assert count(plan, "SELECT threshold FROM engine_params") == 0.5          # two verdicts: not enough data yet
    client.post(f"{URL}/feedback", json={"unit_id": "EDS-04", "technician_id": 1, "verdict": "looks_fine"})
    assert count(plan, "SELECT threshold FROM engine_params") == 0.55          # three false alarms: threshold goes up
    ev = plan.execute(text("SELECT title, detail, payload FROM events WHERE type = 'threshold_adjusted'")).one()
    assert ev[0] == "Alert threshold adjusted" and "0.50 to 0.55" in ev[1] and ev[2] == {"old": 0.5, "new": 0.55}
    client.post(f"{URL}/feedback", json={"unit_id": "EDS-04", "technician_id": 1, "verdict": "looks_fine"})  # a repeat
    assert count(plan, "SELECT threshold FROM engine_params") == 0.55
    assert count(plan, "SELECT count(*) FROM events WHERE type = 'threshold_adjusted'") == 1
