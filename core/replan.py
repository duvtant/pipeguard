"""Rebuild the weekly plan from the database and save it. The ONLY writer of plan_items.

The engine (after each tick) and the voice tools (after a new constraint) both call replan(), so the
dashboard, the phone page and the agent all see the same plan. Caller commits.

Olise's scheduler is imported inside the function: if his files are not on this branch yet, the API still
starts and only the re-plan fails (voice_tools degrades gracefully).
"""
from __future__ import annotations

from sqlalchemy import text
from sqlmodel import Session

from core.alerts import _rows, add_event, sim_today
from core.config import get_settings
from core.simcal import weekday

settings = get_settings()

CREWS_PER_STATION = 2  # same default as the dashboard slider


def _describe(c) -> str | None:
    if c.kind == "moved":
        return f"{c.unit_id} moved to day {c.new_day} ({weekday(c.new_day)})"
    if c.kind == "added":
        return f"{c.unit_id} added on day {c.new_day} ({weekday(c.new_day)})"
    if c.kind == "removed":
        return f"{c.unit_id} removed from the plan"
    return None


def replan(s: Session, reason: str | None = None, emit: bool = True):
    """Returns Olise's PlanResult. Writes plan_items and, if anything changed, one plan_changed event."""
    from core.contracts import Capacity, Constraint, PlanItem, PlanParams
    from core.scheduler import build_plan, plan_units_from_rows

    today = sim_today(s)
    horizon = s.execute(text("SELECT horizon_days FROM engine_params WHERE id = 1")).scalar() or settings.horizon_days

    latest = [dict(r) for r in _rows(
        s, "SELECT DISTINCT ON (unit_id) unit_id, p_fail_h, status, rul_low FROM predictions "
           "WHERE sim_day <= :d ORDER BY unit_id, sim_day DESC", d=today)]
    failed = {r["id"] for r in _rows(s, "SELECT id FROM units WHERE status = 'failed'")}
    # TODO(Olise): pass feedback urgency (looks_fine lowers it for 7 days) once core/feedback.py is wired in.
    units = plan_units_from_rows(latest, failed)

    constraints = [Constraint(unit_id=r["unit_id"], earliest_day=r["earliest_day"],
                              technician_id=r["technician_id"], note=r["note"] or "")
                   for r in _rows(s, "SELECT unit_id, earliest_day, technician_id, note FROM constraints ORDER BY id")]

    previous = [PlanItem(unit_id=r["unit_id"], station_code=r["code"], planned_day=r["planned_day"], crew=r["crew"],
                         expected_saving=r["expected_saving"], reason=r["reason"], state=r["state"])
                for r in _rows(s, "SELECT p.unit_id, st.code, p.planned_day, p.crew, p.expected_saving, p.reason, "
                                  "p.state FROM plan_items p JOIN units u ON u.id = p.unit_id "
                                  "JOIN stations st ON st.id = u.station_id WHERE p.state <> 'done'")]

    params = PlanParams(cost_breakdown=settings.cost_breakdown, cost_service=settings.cost_service)
    result = build_plan(units, Capacity(crews_per_station=CREWS_PER_STATION), constraints, params, today,
                        previous, horizon)

    # crew slot -> technician: the station's technicians, primaries first (wraps if there are fewer techs)
    roster: dict[str, list[int]] = {}
    for r in _rows(s, "SELECT st.code, t.id FROM technicians t JOIN stations st ON st.id = t.station_id "
                      "ORDER BY t.is_backup, t.id"):
        roster.setdefault(r["code"], []).append(r["id"])

    s.execute(text("DELETE FROM plan_items WHERE state <> 'done'"))  # finished work stays as history
    for it in result.items:
        techs = roster.get(it.station_code)
        s.execute(text(
            "INSERT INTO plan_items (unit_id, planned_day, technician_id, crew, expected_saving, reason, state) "
            "VALUES (:u, :d, :t, :c, :e, :r, :st)"),
            {"u": it.unit_id, "d": it.planned_day, "t": techs[it.crew % len(techs)] if techs else None,
             "c": it.crew, "e": it.expected_saving, "r": it.reason, "st": it.state})

    if emit and result.changed:
        changes = [c for c in result.changes if c.kind != "unchanged"]
        detail = "; ".join(d for d in map(_describe, changes) if d) + (f" ({reason})" if reason else "") + "."
        add_event(s, today, "plan_changed", changes[0].unit_id, "Plan changed", detail,
                  payload={"changes": [c.model_dump() for c in changes]})
    return result
