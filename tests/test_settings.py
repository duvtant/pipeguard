"""The manager's runtime settings: one shared row that the API writes and the engine, alerts and voice re-plan read."""
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from api.routers import settings as settings_router
from core import alerts, app_settings
from core.replan import replan
from engine.pg_store import PgStore
from tests.conftest import predict
from tests.test_alerts import ring_one, states, event_types

app = FastAPI()
app.include_router(settings_router.router)
client = TestClient(app)

DEFAULTS = {"crews_per_station": 2, "cost_breakdown": 200000.0, "cost_service": 20000.0, "ring_timeout_secs": 30,
            "call_backup_when_missed": True, "require_manager_for_conflicts": True}


@pytest.fixture(autouse=True)
def clean_settings(db):
    """Settings are not part of the per-test table wipe in conftest: clear the row before and after."""
    db.execute(text("DELETE FROM app_settings")); db.commit()
    yield
    db.execute(text("DELETE FROM app_settings")); db.commit()


def test_with_no_saved_row_the_defaults_are_served(db):
    r = client.get("/api/settings")
    assert r.status_code == 200 and r.json() == DEFAULTS


def test_a_put_changes_only_the_fields_it_sends_and_is_saved(db):
    r = client.put("/api/settings", json={"crews_per_station": 1})
    assert r.status_code == 200 and r.json() == {**DEFAULTS, "crews_per_station": 1}
    r = client.put("/api/settings", json={"ring_timeout_secs": 45, "call_backup_when_missed": False, "something_else": 9})  # unknown field ignored
    assert r.json() == {**DEFAULTS, "crews_per_station": 1, "ring_timeout_secs": 45, "call_backup_when_missed": False}
    assert client.get("/api/settings").json() == r.json()
    assert db.execute(text("SELECT count(*) FROM app_settings")).scalar() == 1  # still a single row


@pytest.mark.parametrize("bad", [{"crews_per_station": 6}, {"crews_per_station": -1}, {"ring_timeout_secs": 1}, {"ring_timeout_secs": 500},
                                 {"cost_breakdown": -5}, {"cost_service": 99_000_000}, {"crews_per_station": "many"}])
def test_out_of_range_values_are_rejected_and_nothing_is_saved(db, bad):
    assert client.put("/api/settings", json=bad).status_code == 422
    assert client.get("/api/settings").json() == DEFAULTS


def test_the_engine_sees_a_change_made_through_the_api(db):
    st = PgStore(os.environ["DATABASE_URL"])
    try:
        assert st.get_capacity().crews_per_station == 2 and st.get_costs() == {"cost_breakdown": 200000.0, "cost_service": 20000.0}
        client.put("/api/settings", json={"crews_per_station": 0, "cost_breakdown": 150000, "cost_service": 25000})
        assert st.get_capacity().crews_per_station == 0
        assert st.get_costs() == {"cost_breakdown": 150000.0, "cost_service": 25000.0}
    finally:
        st.conn.close()


def test_costs_decide_whether_a_service_is_worth_booking(db):
    predict(db, "EDS-01", 0.95)
    client.put("/api/settings", json={"cost_service": 1_000_000})  # a service now costs more than the breakdown it prevents
    replan(db)
    assert db.execute(text("SELECT count(*) FROM plan_items")).scalar() == 0
    client.put("/api/settings", json={"cost_service": 20_000})
    replan(db)
    assert db.execute(text("SELECT count(*) FROM plan_items")).scalar() == 1


def test_the_ring_time_comes_from_the_settings(db):
    client.put("/api/settings", json={"ring_timeout_secs": 10})
    cid = ring_one(db)
    secs = db.execute(text("SELECT extract(epoch FROM ring_expires_at - now()) FROM call_requests WHERE id = :i"), {"i": cid}).scalar()
    assert 5 < secs <= 10


def test_with_the_backup_switched_off_a_missed_call_goes_straight_to_the_manager(db):
    client.put("/api/settings", json={"call_backup_when_missed": False})
    cid = ring_one(db)
    assert alerts.miss_call(db, cid)
    db.commit()
    assert [r[4] for r in states(db)] == ["escalated"]  # no second (backup) request
    assert event_types(db)[-1] == "manager_alert"


def test_a_demo_reset_puts_the_settings_back_to_the_defaults(db):
    client.put("/api/settings", json={"crews_per_station": 4})
    db.execute(text("TRUNCATE app_settings")); db.commit()  # what the seed does to every table
    assert app_settings.read(db) == DEFAULTS


def test_the_table_is_added_to_a_database_that_predates_it(db):
    from core.migrate import ensure_columns
    db.execute(text("DROP TABLE app_settings")); db.commit()
    assert app_settings.read(db) == DEFAULTS  # a missing table is not an error: defaults
    ensure_columns()
    db.rollback()  # end this session's open transaction: it would keep showing the catalogue as it was before the table was created
    assert db.execute(text("SELECT to_regclass('app_settings') IS NOT NULL")).scalar()
    assert client.put("/api/settings", json={"crews_per_station": 3}).json()["crews_per_station"] == 3
