"""Olise's engine code against OUR schema. These guard the seams between the lanes."""
import os

import psycopg
import pytest
from sqlalchemy import text

from core import alerts
from core.contracts import PlanParams, QualityFlag
from core.migrate import ensure_columns
from core.replan import replan
from core.scheduler import build_plan, plan_units_from_rows
from engine.pg_store import PgStore
from tests.conftest import predict


@pytest.fixture
def store():
    st = PgStore(os.environ["DATABASE_URL"])
    yield st
    st.conn.close()


def engine_replan(st, day=10):
    """What engine/worker.py does each tick."""
    rows = [dict(r) for r in st.conn.execute(
        "SELECT DISTINCT ON (unit_id) unit_id, p_fail_h, status, rul_low FROM predictions "
        "WHERE sim_day <= %s ORDER BY unit_id, sim_day DESC", (day,)).fetchall()]
    units = plan_units_from_rows(rows, set())
    return st.replan(lambda prev: build_plan(units, st.get_capacity(), st.get_constraints(day), PlanParams(),
                                             day, prev, 14), day)


def plan_rows(db):
    return db.execute(text("SELECT unit_id, planned_day, technician_id, crew, state FROM plan_items "
                           "ORDER BY unit_id")).all()


def test_engine_can_write_a_quality_flag(db, store):
    flag = QualityFlag(unit_id="EDS-01", sensor="s8", flag_type="sensor_offline", sim_day=10)
    created, resolved = store.upsert_quality_flags([flag])
    assert len(created) == 1 and resolved == []
    created, _ = store.upsert_quality_flags([flag])  # same flag again: nothing new
    assert created == [] and db.execute(text("SELECT count(*) FROM quality_flags")).scalar() == 1
    _, resolved = store.upsert_quality_flags([flag.model_copy(update={"resolved_day": 16})])
    assert len(resolved) == 1
    assert db.execute(text("SELECT detail, resolved_day FROM quality_flags")).one() == ("", 16)


def test_engine_plan_write_works_and_skips_unchanged_plans(db, store):
    predict(db, "EDS-01", 0.95)
    predict(db, "EDS-02", 0.90)
    assert engine_replan(store).changed
    assert plan_rows(db) == [("EDS-01", 10, 1, 0, "planned"), ("EDS-02", 10, 2, 0, "planned")]
    assert not engine_replan(store).changed


def test_voice_replan_agrees_with_the_engine_so_the_plan_never_flips(db, store):
    for u, p in (("EDS-01", .95), ("EDS-02", .90), ("EDS-03", .85)):
        predict(db, u, p)
    engine_replan(store)
    before = plan_rows(db)
    events_before = db.execute(text("SELECT count(*) FROM events")).scalar()
    result = replan(db, emit=True)
    assert not result.changed and plan_rows(db) == before
    assert db.execute(text("SELECT count(*) FROM events")).scalar() == events_before  # no spurious plan_changed
    # a constraint through the voice path, then the engine's next tick must keep it
    db.execute(text("INSERT INTO constraints (technician_id, unit_id, earliest_day, source) "
                    "VALUES (1, 'EDS-01', 11, 'voice')"))
    replan(db, reason="technician unavailable before Friday")
    moved = dict((r[0], r[1]) for r in plan_rows(db))
    assert moved["EDS-01"] == 11
    assert not engine_replan(store).changed and dict((r[0], r[1]) for r in plan_rows(db)) == moved
    detail = db.execute(text("SELECT detail FROM events WHERE type = 'plan_changed' ORDER BY id DESC")).scalar()
    assert "technician unavailable before Friday" in detail


def test_engines_after_tick_hook_rings_the_technicians(db, store):
    predict(db, "EDS-01", 0.95)
    store.after_tick(10)  # this is the call the engine makes after every tick
    row = db.execute(text("SELECT unit_id, technician_id, state FROM call_requests")).one()
    assert tuple(row) == ("EDS-01", 1, "ringing")


def test_the_hook_never_raises_into_the_engine(db, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("policy bug")
    monkeypatch.setattr(alerts, "create_call_requests", boom)
    alerts.on_engine_tick(10)  # must swallow it: a call-policy bug cannot stop the fleet


def test_defaults_are_added_to_a_database_that_predates_them(db):
    with psycopg.connect(os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://"),
                         autocommit=True) as c:
        c.execute("ALTER TABLE plan_items ALTER COLUMN crew DROP DEFAULT")
        c.execute("ALTER TABLE quality_flags ALTER COLUMN detail DROP DEFAULT")
    ensure_columns()
    db.execute(text("INSERT INTO plan_items (unit_id, planned_day, expected_saving, reason, state) "
                    "VALUES ('EDS-01', 10, 0, '', 'planned')"))
    db.execute(text("INSERT INTO quality_flags (unit_id, sim_day, sensor, flag_type) VALUES ('EDS-01', 10, 's8', 'x')"))
    db.commit()


# ---- the plan must not pile up as simulated days pass (found on the deployed server, Oct 4) -------------------------------------
# A booking nobody services goes overdue. The engine used to hide overdue rows from the diff (so the same unit looked brand new every
# day: a "Plan changed" event per day) and never delete them (one extra row per day).

def open_rows(db):
    return db.execute(text("SELECT unit_id, planned_day, state FROM plan_items WHERE state IN ('planned', 'needs_manager_decision') "
                           "ORDER BY unit_id, planned_day")).all()


def test_days_passing_without_a_service_keep_one_row_and_write_no_event(db, store):
    predict(db, "EDS-01", 0.95)
    assert engine_replan(store, day=10).changed
    assert open_rows(db) == [("EDS-01", 10, "planned")]
    for day in (11, 12, 13, 20):
        result = engine_replan(store, day=day)
        assert not result.changed, f"day {day}: an overdue booking rolled forward is not a change"
        assert open_rows(db) == [("EDS-01", day, "planned")]  # still ONE row, now booked for today


def test_a_stale_overdue_row_is_replaced_not_duplicated_when_the_plan_really_changes(db, store):
    predict(db, "EDS-01", 0.95)
    engine_replan(store, day=10)
    predict(db, "EDS-02", 0.90, day=12)  # a second unit turns red on day 12
    result = engine_replan(store, day=12)
    assert result.changed and [c.unit_id for c in result.changes if c.kind == "added"] == ["EDS-02"]  # only the NEW unit is news
    assert open_rows(db) == [("EDS-01", 12, "planned"), ("EDS-02", 12, "planned")]


def test_a_voice_constraint_still_moves_the_booking_after_days_have_passed(db, store):
    predict(db, "EDS-01", 0.95)
    engine_replan(store, day=10)
    db.execute(text("UPDATE sim_state SET sim_day = 13 WHERE id = 1"))
    db.execute(text("INSERT INTO constraints (technician_id, unit_id, earliest_day, source) VALUES (1, 'EDS-01', 16, 'voice')"))
    result = replan(db, emit=True, source="voice")
    assert any(c.kind == "moved" and c.unit_id == "EDS-01" and c.new_day == 16 for c in result.changes)
    assert open_rows(db) == [("EDS-01", 16, "planned")]
    assert not engine_replan(store, day=13).changed  # and the engine's next tick keeps it


def test_finished_services_are_never_touched_by_a_replan(db, store):
    predict(db, "EDS-01", 0.95)
    engine_replan(store, day=10)
    db.execute(text("UPDATE plan_items SET state = 'done' WHERE unit_id = 'EDS-01'"))
    db.commit()  # the engine uses its own connection: an uncommitted change would block its DELETE
    engine_replan(store, day=15)
    assert db.execute(text("SELECT count(*) FROM plan_items WHERE state = 'done'")).scalar() == 1
