import threading

from sqlalchemy import text
from sqlmodel import Session

from core import alerts
from core.db import engine
from tests.conftest import predict


def states(s):
    return [tuple(r) for r in s.execute(text("SELECT id, unit_id, technician_id, attempt, state "
                                             "FROM call_requests ORDER BY id"))]


def event_types(s):
    return [r[0] for r in s.execute(text("SELECT type FROM events ORDER BY id"))]


def expire(s, cid):
    s.execute(text("UPDATE call_requests SET ring_expires_at = now() - interval '1 second' WHERE id = :i"), {"i": cid})
    s.commit()


# ---------------------------------------------------------------- guardrails
def test_only_top_band_of_at_risk_units_get_calls(db):
    predict(db, "EDS-01", 0.95)
    predict(db, "EDS-02", 0.90)
    predict(db, "EDS-03", 0.85)
    predict(db, "EDS-04", 0.70)                 # fourth: outside the top 3
    predict(db, "EDS-05", 0.99, status="watch")  # not at risk
    res = alerts.create_call_requests(db)
    db.commit()
    assert [s[1] for s in states(db)] == ["EDS-01", "EDS-02", "EDS-03"]
    assert len(res["created"]) == 3


def test_failed_units_and_units_with_open_request_are_skipped(db):
    predict(db, "EDS-01", 0.95)
    predict(db, "EDS-02", 0.90)
    db.execute(text("UPDATE units SET status = 'failed' WHERE id = 'EDS-01'"))
    db.commit()
    alerts.create_call_requests(db)
    db.commit()
    alerts.create_call_requests(db)  # second pass: EDS-02 already ringing
    db.commit()
    assert [s[1] for s in states(db)] == ["EDS-02"]


def test_daily_cap_moves_to_next_technician_then_suppresses(db):
    for i in range(1, 4):  # Anna already has 3 calls today
        db.execute(text("INSERT INTO call_requests (unit_id, technician_id, sim_day, state, attempt) "
                        "VALUES (:u, 1, 10, 'done', 1)"), {"u": f"EDS-0{i}"})
    db.commit()
    predict(db, "EDS-04", 0.9)
    alerts.create_call_requests(db)
    db.commit()
    assert states(db)[-1][2] == 2  # Marc takes it
    for t in (2, 3):  # now cap Marc and Bo too
        for _ in range(3):
            db.execute(text("INSERT INTO call_requests (unit_id, technician_id, sim_day, state, attempt) "
                            "VALUES ('HIN-01', :t, 10, 'done', 1)"), {"t": t})
    db.commit()
    predict(db, "EDS-05", 0.95)
    res = alerts.create_call_requests(db)
    assert res["created"] == [] and "cap" in res["suppressed"][0][1]


def test_no_duplicate_within_3_days_unless_worsened(db):
    predict(db, "EDS-01", 0.70, day=10)
    alerts.create_call_requests(db)
    db.commit()
    alerts.miss_call(db, states(db)[0][0])
    alerts.miss_call(db, states(db)[-1][0])  # backup misses too: chain over
    db.commit()
    predict(db, "EDS-01", 0.72, day=11)
    res = alerts.create_call_requests(db, sim_day=11)
    assert res["created"] == [] and "not worsened" in res["suppressed"][0][1]
    predict(db, "EDS-01", 0.86, day=11)   # +0.16 since the last call
    assert len(alerts.create_call_requests(db, sim_day=11)["created"]) == 1


def test_repeat_call_allowed_after_3_days(db):
    predict(db, "EDS-01", 0.70, day=10)
    alerts.create_call_requests(db)
    db.execute(text("UPDATE call_requests SET state = 'done'"))
    db.commit()
    predict(db, "EDS-01", 0.70, day=13)
    assert len(alerts.create_call_requests(db, sim_day=13)["created"]) == 1


# ---------------------------------------------------------------- state machine
def ring_one(db, unit="EDS-01"):
    predict(db, unit, 0.9)
    alerts.create_call_requests(db)
    db.commit()
    return states(db)[-1][0]


def test_answer_then_done(db):
    cid = ring_one(db)
    assert alerts.answer_call(db, cid) is True
    assert alerts.answer_call(db, cid) is False  # second tap does nothing
    assert alerts.finish_call(db, cid) is True
    db.commit()
    assert states(db)[0][4] == "done"
    assert event_types(db) == ["call_requested", "call_answered"]


def test_late_answer_after_expiry_fails_cleanly(db):
    cid = ring_one(db)
    expire(db, cid)
    assert alerts.answer_call(db, cid) is False
    assert states(db)[0][4] == "ringing"  # sweeper still owns it


def test_decline_rings_backup_then_escalates(db):
    cid = ring_one(db)
    assert alerts.miss_call(db, cid, "declined")
    db.commit()
    rows = states(db)
    assert rows[0][4] == "missed" and rows[1][3:] == (2, "ringing") and rows[1][2] == 3  # Bo, the backup
    assert alerts.miss_call(db, rows[1][0])
    db.commit()
    assert states(db)[1][4] == "escalated"
    assert event_types(db)[-1] == "manager_alert"
    assert alerts.miss_call(db, rows[1][0]) is False  # already handled


def test_no_backup_at_station_escalates_directly(db):
    cid = ring_one(db, "HIN-01")
    alerts.miss_call(db, cid)
    db.commit()
    assert states(db) == [(cid, "HIN-01", 4, 1, "escalated")]
    assert event_types(db)[-1] == "manager_alert"


# ---------------------------------------------------------------- sweeper
def test_sweeper_only_touches_expired_rings_and_is_idempotent(db):
    a = ring_one(db, "EDS-01")
    ring_one(db, "EDS-02")
    expire(db, a)
    assert alerts.sweep_expired(db) == 1
    db.commit()
    assert alerts.sweep_expired(db) == 0  # the backup ring is fresh, nothing else expired
    assert [r[4] for r in states(db)] == ["missed", "ringing", "ringing"]


def test_two_sweepers_do_not_double_fire(db):
    cid = ring_one(db)
    expire(db, cid)
    results = []

    def run():
        with Session(engine) as s:
            results.append(alerts.sweep_expired(s))
            s.commit()

    threads = [threading.Thread(target=run) for _ in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sum(results) == 1
    assert len(states(db)) == 2  # original plus exactly one backup ring
