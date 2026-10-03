"""Crew-limited weekly plan. Must return a diff (added/moved/removed) for the voice reply.

Owner: Olise. Spec: Olise guide section 8, techstack section 7.4.

Greedy v1:
  value       expected_saving = p_fail * urgency * C_breakdown - C_service; non-positive -> skipped
  order       expected saving (rounded to $1,000 so tiny p_fail wobbles do not reshuffle), then unit_id
  assignment  earliest day in [max(today, earliest_day), today + window - 1] with a free crew slot at the
              unit's station (crews_per_station slots per station per day)
  constraints "not before Friday" binds the UNIT (earliest_day); several for one unit -> the latest wins
  no slot     an at_risk unit with no feasible slot -> needs_manager_decision (never fails silently);
              a watch unit with no slot is listed in `deferred`
  too late    an at_risk unit whose earliest_day is after today + rul_low is scheduled if possible but
              marked needs_manager_decision: the crew is only free after it may already have failed
  booking     at_risk units are booked. Watch units with a positive saving are returned in `deferred`
              (next in line) unless params.book_watch is set. Reason: with the contract costs the saving is
              positive for every p_fail > 0.10, i.e. every watch unit, so booking them would service units
              as soon as they leave healthy and make the alert threshold irrelevant (techstack section 19).
  excluded    failed and done units; healthy units

The plan is rebuilt from scratch every call with a stable order, so the same input always gives the same
plan (idempotent) and a small change gives a small diff. `greedy_assign` is the kernel; the simulation
(core/simulate.py) calls the same kernel, so there is one scheduler, not two.

Callers (engine tick and API re-plan) must hold one advisory lock around "read state, build plan,
write plan" so they do not interleave. That lock lives in Ebube's core/db.py.
"""
from __future__ import annotations

from collections import defaultdict

from core.contracts import (Capacity, Constraint, ManagerDecision, PlanChange, PlanItem, PlanParams, PlanResult,
                            PlanUnit)

SAVING_ROUND: float = 1000.0


def expected_saving(p_fail: float, cost_breakdown: float, cost_service: float, urgency: float = 1.0) -> float:
    return float(p_fail) * float(urgency) * float(cost_breakdown) - float(cost_service)


def priority_key(saving: float, unit_id: str) -> tuple[float, str]:
    return (-round(saving / SAVING_ROUND), unit_id)


def greedy_assign(stations: list[str], earliest: list[int], today: int, window: int,
                  crews: dict[str, int] | int, blocked: dict[str, set[int]] | None = None,
                  used: dict[tuple[str, int], int] | None = None) -> list[tuple[int, int] | None]:
    """Assign each candidate (already in priority order) the earliest free (day, crew) slot, or None.

    stations[i], earliest[i]: the candidate's station and earliest allowed day. `crews`: slots per station
    per day (an int for every station, or a dict). `used` is updated in place when given.
    """
    used = used if used is not None else defaultdict(int)
    blocked = blocked or {}
    last_day = today + window - 1
    out: list[tuple[int, int] | None] = []
    for st, ear in zip(stations, earliest):
        cap = crews if isinstance(crews, int) else crews.get(st, 0)
        slot = None
        if cap > 0:
            for d in range(max(today, ear), last_day + 1):
                if d in blocked.get(st, ()):
                    continue
                if used[(st, d)] < cap:
                    slot = (d, used[(st, d)])
                    used[(st, d)] += 1
                    break
        out.append(slot)
    return out


def latest_constraints(constraints: list[Constraint]) -> dict[str, Constraint]:
    out: dict[str, Constraint] = {}
    for c in constraints:
        if c.unit_id not in out or c.earliest_day > out[c.unit_id].earliest_day:
            out[c.unit_id] = c
    return out


def diff_plans(previous: list[PlanItem] | None, items: list[PlanItem]) -> list[PlanChange]:
    old = {p.unit_id: p.planned_day for p in (previous or [])}
    new = {p.unit_id: p.planned_day for p in items}
    changes: list[PlanChange] = []
    for it in items:  # priority order
        if it.unit_id not in old:
            changes.append(PlanChange(kind="added", unit_id=it.unit_id, new_day=it.planned_day))
        elif old[it.unit_id] != it.planned_day:
            changes.append(PlanChange(kind="moved", unit_id=it.unit_id, old_day=old[it.unit_id], new_day=it.planned_day))
    for uid in sorted(old):
        if uid not in new:
            changes.append(PlanChange(kind="removed", unit_id=uid, old_day=old[uid]))
    for it in items:
        if it.unit_id in old and old[it.unit_id] == it.planned_day:
            changes.append(PlanChange(kind="unchanged", unit_id=it.unit_id, old_day=it.planned_day, new_day=it.planned_day))
    return changes


def plan_units_from_rows(rows: list[dict], failed: set[str] | None = None,
                         urgency: dict[str, float] | None = None) -> list[PlanUnit]:
    """Scheduler input from the latest stored prediction per unit (dicts with unit_id, p_fail_h, status,
    rul_low). The engine and the API (re-plan after a voice constraint) both use this, so they agree."""
    failed, urgency = failed or set(), urgency or {}
    out = [PlanUnit(unit_id=r["unit_id"], station_code=r["unit_id"].split("-")[0], p_fail=float(r["p_fail_h"]),
                    risk_status=r["status"], rul_low=float(r["rul_low"]), failed=r["unit_id"] in failed,
                    urgency=float(urgency.get(r["unit_id"], 1.0))) for r in rows]
    seen = {u.unit_id for u in out}
    out += [PlanUnit(unit_id=uid, station_code=uid.split("-")[0], p_fail=0.0, risk_status="healthy", rul_low=0.0,
                     failed=True) for uid in sorted(failed - seen)]
    return out


def _money(x: float) -> str:
    return f"${x:,.0f}"


def build_plan(units: list[PlanUnit], capacity: Capacity, constraints: list[Constraint], params: PlanParams,
               today: int, previous: list[PlanItem] | None = None, horizon_days: int = 14) -> PlanResult:
    """The weekly plan for days today .. today + window - 1, plus the diff against `previous`."""
    cons = latest_constraints(constraints)
    cands: list[tuple[PlanUnit, float]] = []
    next_in_line: list[tuple[PlanUnit, float]] = []
    for u in units:
        if u.failed or u.done or u.risk_status not in ("at_risk", "watch"):
            continue
        s = expected_saving(u.p_fail, params.cost_breakdown, params.cost_service, u.urgency)
        if s <= 0:
            continue
        if u.risk_status == "at_risk" or params.book_watch:
            cands.append((u, s))
        else:
            next_in_line.append((u, s))
    cands.sort(key=lambda us: priority_key(us[1], us[0].unit_id))
    next_in_line.sort(key=lambda us: priority_key(us[1], us[0].unit_id))

    earliest = [cons[u.unit_id].earliest_day if u.unit_id in cons else today for u, _ in cands]
    stations = [u.station_code for u, _ in cands]
    crews = {st: capacity.crews(st) for st in set(stations)}
    blocked = {st: set(days) for st, days in capacity.blocked_days.items()}
    slots = greedy_assign(stations, earliest, today, params.window_days, crews, blocked)

    items: list[PlanItem] = []
    decisions: list[ManagerDecision] = []
    deferred: list[str] = [u.unit_id for u, _ in next_in_line]
    last_day = today + params.window_days - 1
    for (u, s), ear, slot in zip(cands, earliest, slots):
        risk_txt = f"{u.p_fail:.0%} chance of failure within {horizon_days} days; expected saving {_money(s)}"
        too_late = u.risk_status == "at_risk" and ear > today + u.rul_low
        if slot is None:
            if u.risk_status != "at_risk":
                deferred.append(u.unit_id)
                continue
            if crews.get(u.station_code, 0) <= 0:
                why = f"No crew available at {u.station_code} this week."
            elif ear > last_day:
                why = f"Earliest allowed day ({ear}) is beyond this week's plan (ends day {last_day})."
            else:
                why = f"No free crew slot at {u.station_code} before the end of the week."
            if too_late:
                why += f" The unit may fail before day {ear} (lowest estimate {u.rul_low:.0f} days)."
            decisions.append(ManagerDecision(unit_id=u.unit_id, station_code=u.station_code, reason=why))
            continue
        day, crew = slot
        state = "planned"
        reason = ("At risk: " if u.risk_status == "at_risk" else "Watch: ") + risk_txt
        if too_late:
            state = "needs_manager_decision"
            why = (f"Crew is free only from day {ear}, but the unit may fail within {u.rul_low:.0f} days "
                   f"(by day {today + int(u.rul_low)}).")
            decisions.append(ManagerDecision(unit_id=u.unit_id, station_code=u.station_code, reason=why))
            reason += ". " + why
        items.append(PlanItem(unit_id=u.unit_id, station_code=u.station_code, planned_day=day, crew=crew,
                              expected_saving=round(s, 2), reason=reason, state=state))

    return PlanResult(
        items=items,
        needs_manager_decision=[d.unit_id for d in decisions],
        decisions=decisions,
        deferred=deferred,
        changes=diff_plans(previous, items),
    )
