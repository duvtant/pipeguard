import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from api.routers import fleet, plan
from core import approvals, voice_tools
from core.replan import replan
from tests.conftest import predict
from tests.test_engine_store import engine_replan
from engine.pg_store import PgStore
import os

app = FastAPI()
app.include_router(plan.router)
app.include_router(fleet.router)
client = TestClient(app)


def run(db, sql, **p):
    db.execute(text(sql), p)
    db.commit()


def count(db, sql):
    return db.execute(text(sql)).scalar()


def items(by="unit_id"):
    return {i[by]: i for i in client.get("/api/plan").json()}


def csv_units():
    lines = client.get("/api/work-orders.csv").content.decode("utf-8-sig").splitlines()[1:]
    return sorted(l.split(",")[2] for l in lines)


@pytest.fixture
def world(db):
    """Day 10 (Thursday). EDS-01..03 red with a baseline plan (two crews a day), and answered calls for two of them."""
    for u, p in (("EDS-01", .95), ("EDS-02", .90), ("EDS-03", .85)):
        predict(db, u, p)
    replan(db, emit=False)
    run(db, "INSERT INTO call_requests (unit_id, technician_id, sim_day, state, attempt) VALUES "
            "('EDS-01', 1, 10, 'answered', 1), ('EDS-02', 1, 10, 'answered', 1)")
    return db


def move(db, unit="EDS-01", day="Friday"):
    r = voice_tools.submit_availability(db, {"unit_id": unit, "technician_id": 1, "earliest_day_text": day})
    db.commit()
    assert r["ok"] is True
    return r


# ---------------------------------------------------------------- approval
def test_everything_starts_approved(world):
    assert {i["approval"] for i in items().values()} == {"approved"}
    assert csv_units() == ["EDS-01", "EDS-02", "EDS-03"]


def test_a_voice_move_becomes_a_proposal_until_a_manager_approves(world):
    move(world)
    got = items()
    assert got["EDS-01"]["planned_day"] == 11 and got["EDS-01"]["approval"] == "proposed"
    assert got["EDS-03"]["planned_day"] == 10 and got["EDS-03"]["approval"] == "proposed"   # shifted by the same call
    assert got["EDS-02"]["approval"] == "approved"                                          # untouched: still approved
    assert csv_units() == ["EDS-02"]                                                        # proposals are not work orders


def test_repeating_the_call_never_unapproves_anything(world):
    move(world)
    client.post("/api/plan/approve-all")
    move(world)  # the agent repeats itself: same day, nothing changes
    assert {i["approval"] for i in items().values()} == {"approved"}
    assert count(world, "SELECT count(*) FROM events WHERE type = 'plan_changed'") == 1   # only the move: the baseline wrote none


def test_approve_one_item(world):
    move(world)
    iid = items()["EDS-01"]["id"]
    r = client.post(f"/api/plan/{iid}/approve").json()
    assert r["approval"] == "approved" and r["unit_id"] == "EDS-01" and r["planned_day"] == 11
    ev = world.execute(text("SELECT title, detail, unit_id, payload FROM events WHERE type = 'plan_approved'")).one()
    assert ev[0] == "Plan approved" and ev[1] == "A manager approved EDS-01 for Fri, Oct 16. It is now a work order."
    assert ev[2] == "EDS-01" and ev[3] == {"planned_day": 11}
    assert items()["EDS-03"]["approval"] == "proposed" and csv_units() == ["EDS-01", "EDS-02"]
    client.post(f"/api/plan/{iid}/approve")  # approving twice: no second event
    assert count(world, "SELECT count(*) FROM events WHERE type = 'plan_approved'") == 1


def test_approve_all_and_unknown_item(world):
    move(world)
    assert client.post("/api/plan/approve-all").json() == {"approved": 2}
    assert client.post("/api/plan/approve-all").json() == {"approved": 0}
    assert csv_units() == ["EDS-01", "EDS-02", "EDS-03"]
    assert client.post("/api/plan/99999/approve").status_code == 404


def test_a_later_move_to_a_new_day_needs_approval_again(world):
    move(world)
    client.post("/api/plan/approve-all")
    move(world, day="Saturday")   # moves EDS-01 again, to day 12
    assert items()["EDS-01"]["planned_day"] == 12 and items()["EDS-01"]["approval"] == "proposed"


def test_approvals_survive_the_engine_rewriting_the_plan(world):
    move(world)
    client.post(f"/api/plan/{items()['EDS-01']['id']}/approve")
    st = PgStore(os.environ["DATABASE_URL"])
    try:
        predict(world, "EDS-02", 0.91)   # a new prediction: the engine's next tick replans
        engine_replan(st)
    finally:
        st.conn.close()
    got = items()
    assert got["EDS-01"]["approval"] == "approved" and got["EDS-03"]["approval"] == "proposed"


def test_a_demo_reset_puts_everything_back_to_approved(world):
    move(world)
    assert items()["EDS-01"]["approval"] == "proposed"
    run(world, "TRUNCATE events")   # what the seed's reset does to every table
    assert {i["approval"] for i in items().values()} == {"approved"}


# ---------------------------------------------------------------- manager decisions
@pytest.fixture
def stuck(world):
    """EDS-04 is red but no crew slot could take it (no plan row)."""
    predict(world, "EDS-04", 0.80)
    return world


def test_a_unit_no_crew_could_take_gets_a_manager_card(stuck):
    card = items()["EDS-04"]
    assert card["state"] == "needs_manager_decision" and card["id"] >= 1_000_000 and card["approval"] == "proposed"
    assert "decision" not in card and card["technician_name"] == "Unassigned" and card["expected_saving"] > 100000
    assert approvals.unit_for_synth(card["id"]) == "EDS-04"
    fleet_unit = {u["unit_id"]: u for u in client.get("/api/fleet").json()["units"]}["EDS-04"]
    assert fleet_unit["needs_manager_decision"] is True and fleet_unit["next_service_day"] is None


def test_overtime_schedules_an_extra_crew_tomorrow(stuck):
    iid = items()["EDS-04"]["id"]
    r = client.post(f"/api/plan/{iid}/decide", json={"choice": "overtime"}).json()
    assert (r["state"], r["planned_day"], r["approval"], r["decision"]) == ("planned", 11, "approved", "overtime")
    assert r["technician_name"] == "Anna Primary" and r["id"] == iid
    ev = stuck.execute(text("SELECT title, detail, payload FROM events WHERE type = 'manager_decision'")).one()
    assert ev[0] == "Overtime crew approved" and "overtime crew for EDS-04 on Fri, Oct 16" in ev[1] and ev[2] == {"choice": "overtime", "day": 11}
    u = {u["unit_id"]: u for u in client.get("/api/fleet").json()["units"]}["EDS-04"]
    assert u["needs_manager_decision"] is False and u["next_service_day"] == 11
    assert "EDS-04" in csv_units()


def test_deferring_accepts_the_risk_and_stays_off_the_schedule(stuck):
    iid = items()["EDS-04"]["id"]
    r = client.post(f"/api/plan/{iid}/decide", json={"choice": "defer"}).json()
    assert (r["state"], r["decision"]) == ("needs_manager_decision", "deferred")
    assert stuck.execute(text("SELECT title FROM events WHERE type = 'manager_decision'")).scalar() == "Risk accepted for now"
    u = {u["unit_id"]: u for u in client.get("/api/fleet").json()["units"]}["EDS-04"]
    assert u["needs_manager_decision"] is False
    assert "EDS-04" not in csv_units()
    r = client.post(f"/api/plan/{iid}/decide", json={"choice": "overtime"}).json()   # a deferred item can still be upgraded
    assert r["decision"] == "overtime" and "EDS-04" in csv_units()


def test_deciding_twice_changes_nothing_and_bad_requests_are_clear(stuck):
    iid = items()["EDS-04"]["id"]
    client.post(f"/api/plan/{iid}/decide", json={"choice": "overtime"})
    client.post(f"/api/plan/{iid}/decide", json={"choice": "overtime"})
    assert count(stuck, "SELECT count(*) FROM events WHERE type = 'manager_decision'") == 1
    assert client.post(f"/api/plan/{iid}/decide", json={"choice": "pray"}).status_code == 422
    assert client.post("/api/plan/99999/decide", json={"choice": "defer"}).status_code == 404
    ok_item = items()["EDS-02"]["id"]   # a normal planned item does not need a decision
    assert client.post(f"/api/plan/{ok_item}/decide", json={"choice": "defer"}).status_code == 409


def test_a_voice_call_that_comes_too_late_can_also_get_an_overtime_decision(world):
    """The scheduler keeps the unit with a late crew day and marks it needs_manager_decision (a real row)."""
    predict(world, "EDS-01", 0.95, rul_low=2.0)   # may fail within 2 days, so a crew free only on day 14 is too late
    r = voice_tools.submit_availability(world, {"unit_id": "EDS-01", "technician_id": 1, "earliest_day_text": "in 4 days"})
    world.commit()
    assert r["ok"] is True and "flagged it for a manager" in r["say"]
    card = items()["EDS-01"]
    assert card["state"] == "needs_manager_decision" and card["planned_day"] == 14 and card["id"] < 1_000_000   # a real row
    r = client.post(f"/api/plan/{card['id']}/decide", json={"choice": "overtime"}).json()
    assert (r["state"], r["planned_day"], r["id"]) == ("planned", 11, card["id"])
    assert count(world, "SELECT count(*) FROM plan_items WHERE unit_id = 'EDS-01'") == 1
    assert len([i for i in client.get("/api/plan").json() if i["unit_id"] == "EDS-01"]) == 1   # one card, not two
