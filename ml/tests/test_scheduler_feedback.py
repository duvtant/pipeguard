"""Scheduler (determinism, capacity, constraints, diff, manager decisions) and feedback rules."""
from core.contracts import Capacity, Constraint, PlanItem, PlanParams, PlanUnit, VerdictRecord
from core.feedback import adjust_threshold, process_feedback, urgency_multipliers
from core.scheduler import build_plan

P = PlanParams()


def U(uid, p, status="at_risk", low=30.0, **kw):
    return PlanUnit(unit_id=uid, station_code=uid.split("-")[0], p_fail=p, risk_status=status, rul_low=low, **kw)


FLEET = [U("EDS-01", 0.9), U("EDS-02", 0.7), U("EDS-03", 0.6), U("HIN-01", 0.8), U("HIN-02", 0.3, "watch"),
         U("EDS-04", 0.05, "healthy"), U("EDS-05", 0.95, failed=True)]


def test_deterministic_and_idempotent():
    a = build_plan(FLEET, Capacity(crews_per_station=1), [], P, today=10)
    b = build_plan(list(reversed(FLEET)), Capacity(crews_per_station=1), [], P, today=10)
    assert a.items == b.items
    c = build_plan(FLEET, Capacity(crews_per_station=1), [], P, today=10, previous=a.items)
    assert all(ch.kind == "unchanged" for ch in c.changes) and not c.changed


def test_capacity_one_orders_by_saving():
    r = build_plan(FLEET, Capacity(crews_per_station=1), [], P, today=10)
    eds = [(i.unit_id, i.planned_day) for i in r.items if i.station_code == "EDS"]
    assert eds == [("EDS-01", 10), ("EDS-02", 11), ("EDS-03", 12)]
    assert all(i.unit_id not in ("EDS-04", "EDS-05") for i in r.items)   # healthy and failed excluded
    assert "HIN-02" not in [i.unit_id for i in r.items] and r.deferred == ["HIN-02"]  # watch: next in line
    booked = build_plan(FLEET, Capacity(crews_per_station=1), [], P.model_copy(update={"book_watch": True}), today=10)
    assert ("HIN-02", 11) in [(i.unit_id, i.planned_day) for i in booked.items]       # literal rule on request


def test_crews_zero_everything_needs_a_decision():
    r = build_plan(FLEET, Capacity(crews_per_station=0), [], P, today=10)
    assert r.items == []
    assert set(r.needs_manager_decision) == {"EDS-01", "EDS-02", "EDS-03", "HIN-01"}
    assert r.deferred == ["HIN-02"]
    assert all("No crew" in d.reason for d in r.decisions)


def test_crews_huge_everything_today():
    r = build_plan(FLEET, Capacity(crews_per_station=99), [], P, today=10)
    assert {i.planned_day for i in r.items} == {10} and len(r.items) == 4 and r.needs_manager_decision == []


def test_constraint_moves_unit_and_diff_reports_it():
    before = build_plan(FLEET, Capacity(crews_per_station=1), [], P, today=10)
    cons = [Constraint(unit_id="EDS-01", earliest_day=12), Constraint(unit_id="EDS-01", earliest_day=11)]
    after = build_plan(FLEET, Capacity(crews_per_station=1), cons, P, today=10, previous=before.items)
    days = {i.unit_id: i.planned_day for i in after.items}
    assert days["EDS-01"] == 12                   # the latest earliest_day wins
    assert days["EDS-02"] == 10 and days["EDS-03"] == 11
    moved = {c.unit_id: (c.old_day, c.new_day) for c in after.changes if c.kind == "moved"}
    assert moved == {"EDS-01": (10, 12), "EDS-02": (11, 10), "EDS-03": (12, 11)}


def test_constraint_beyond_window_and_too_late():
    cons = [Constraint(unit_id="EDS-01", earliest_day=30)]
    r = build_plan(FLEET, Capacity(crews_per_station=1), cons, P, today=10)
    assert "EDS-01" in r.needs_manager_decision and "EDS-01" not in [i.unit_id for i in r.items]
    reason = next(d.reason for d in r.decisions if d.unit_id == "EDS-01")
    assert "beyond this week's plan" in reason
    # Free only on day 14 but may fail within 3 days: scheduled, flagged for the manager.
    units = [U("EDS-01", 0.9, low=3.0)]
    r = build_plan(units, Capacity(crews_per_station=1), [Constraint(unit_id="EDS-01", earliest_day=14)], P, today=10)
    assert r.items[0].planned_day == 14 and r.items[0].state == "needs_manager_decision"
    assert r.needs_manager_decision == ["EDS-01"]


def test_two_units_one_station_one_crew_and_removed():
    units = [U("EDS-01", 0.9), U("EDS-02", 0.85)]
    r = build_plan(units, Capacity(crews_per_station=1), [], P, today=0)
    assert [(i.unit_id, i.planned_day) for i in r.items] == [("EDS-01", 0), ("EDS-02", 1)]
    prev = r.items + [PlanItem(unit_id="WHT-09", station_code="WHT", planned_day=3, crew=0, expected_saving=1, reason="x")]
    r2 = build_plan(units, Capacity(crews_per_station=1), [], P, today=0, previous=prev)
    assert [c.unit_id for c in r2.changes if c.kind == "removed"] == ["WHT-09"]


def test_urgency_lowers_priority():
    units = [U("EDS-01", 0.9, urgency=0.5), U("EDS-02", 0.8)]
    r = build_plan(units, Capacity(crews_per_station=1), [], P, today=0)
    assert r.items[0].unit_id == "EDS-02"


# ---- feedback --------------------------------------------------------------------------------
def V(uid, verdict, day=0):
    return VerdictRecord(unit_id=uid, verdict=verdict, sim_day=day)


def test_feedback_raises_on_false_alarms_and_respects_bounds():
    vs = [V("A", "looks_fine"), V("B", "looks_fine"), V("C", "confirmed_wear")]
    new, msg = adjust_threshold(vs, 0.5)
    assert new == 0.55 and msg.startswith("Feedback received, threshold adjusted from 0.50 to 0.55")
    assert adjust_threshold(vs, 0.9) == (0.9, None)
    hits = [V(c, "confirmed_wear") for c in "ABCDE"]
    assert adjust_threshold(hits, 0.5)[0] == 0.45
    assert adjust_threshold(hits, 0.2) == (0.2, None)


def test_feedback_small_window_and_middle_band():
    assert adjust_threshold([V("A", "looks_fine"), V("B", "looks_fine")], 0.5) == (0.5, None)
    mixed = [V(c, "confirmed_wear") for c in "ABC"] + [V("D", "looks_fine")]  # 75%: no change
    assert adjust_threshold(mixed, 0.5) == (0.5, None)


def test_feedback_burst_from_one_unit_moves_once():
    vs = [V("A", "looks_fine"), V("B", "looks_fine"), V("C", "confirmed_wear")]
    th, _ = adjust_threshold(vs, 0.5)
    for _ in range(5):
        vs.append(V("B", "looks_fine"))
        th2, msg = adjust_threshold(vs, th)
        assert th2 == th and msg is None


def test_feedback_window_is_last_ten_units():
    vs = [V(f"U{i}", "looks_fine") for i in range(10)] + [V(f"W{i}", "confirmed_wear") for i in range(10)]
    assert adjust_threshold(vs, 0.5)[0] == 0.45   # only the last 10 count: all hits


def test_urgency_and_reset():
    vs = [V("A", "looks_fine", day=10), V("B", "looks_fine", day=1), V("C", "part_replaced", day=11)]
    assert urgency_multipliers(vs, today=12) == {"A": 0.5}
    res = process_feedback(vs, 0.5, today=12)
    assert res.reset_units == ["C"] and 0.2 <= res.threshold <= 0.9
