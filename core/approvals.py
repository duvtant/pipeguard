"""Manager approval of plan changes and manager decisions (David's MESSAGE_TO_EBUBE.md items 1 and 2).

State is DERIVED from the event log, not stored on plan rows: Olise's engine deletes and rewrites plan_items
whenever the plan changes, so anything stored on a row would be lost. Events survive that, and a demo reset
(which truncates events) puts everything back to approved with no extra code.

  proposed   a plan_changed event tagged source=voice moved or added (unit, day), and no later plan_approved
             event covers that (unit, day). Everything else is approved.
  decision   the newest manager_decision event for a unit: overtime (an extra crew tomorrow) or deferred.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlmodel import Session

from core.alerts import add_event, sim_today
from core.contracts import STATION_ORDER
from core.simcal import format_sim_date

SYNTH_BASE = 1_000_000  # ids for plan items that have no database row (a unit no crew could take)

_PROPOSED_SQL = """
SELECT m.unit_id, m.day FROM (
  SELECT e.id AS eid, c->>'unit_id' AS unit_id, (c->>'new_day')::int AS day
  FROM events e,
       jsonb_array_elements(CASE WHEN jsonb_typeof(e.payload->'changes') = 'array'
                                 THEN e.payload->'changes' ELSE '[]'::jsonb END) c
  WHERE e.type = 'plan_changed' AND e.payload->>'source' = 'voice' AND c->>'kind' IN ('moved', 'added')
) m
WHERE NOT EXISTS (SELECT 1 FROM events a WHERE a.type = 'plan_approved' AND a.id > m.eid
                  AND a.unit_id = m.unit_id AND (a.payload->>'planned_day')::int = m.day)
"""


def synth_id(unit_id: str) -> int:
    code, num = unit_id.split("-")
    return SYNTH_BASE + STATION_ORDER.index(code) * 100 + int(num)


def unit_for_synth(item_id: int) -> str | None:
    if item_id < SYNTH_BASE:
        return None
    idx, num = divmod(item_id - SYNTH_BASE, 100)
    return f"{STATION_ORDER[idx]}-{num:02d}" if idx < len(STATION_ORDER) and num else None


def proposed(s: Session) -> set[tuple[str, int]]:
    return {(r[0], r[1]) for r in s.execute(text(_PROPOSED_SQL))}


def decisions(s: Session) -> dict[str, dict]:
    """unit_id -> {"choice": "overtime" | "deferred", "day": int | None}, newest decision per unit."""
    rows = s.execute(text(
        "SELECT DISTINCT ON (unit_id) unit_id, payload->>'choice', (payload->>'day')::int FROM events "
        "WHERE type = 'manager_decision' AND unit_id IS NOT NULL ORDER BY unit_id, id DESC"))
    return {r[0]: {"choice": r[1], "day": r[2]} for r in rows}


def approve(s: Session, unit_id: str, planned_day: int) -> bool:
    """Release one plan item as a work order. False if it was already approved (no second event)."""
    if (unit_id, planned_day) not in proposed(s):
        return False
    add_event(s, sim_today(s), "plan_approved", unit_id, "Plan approved",
              f"A manager approved {unit_id} for {format_sim_date(planned_day)}. It is now a work order.",
              payload={"planned_day": planned_day})
    return True


def decide(s: Session, unit_id: str, choice: str) -> bool:
    """choice: 'overtime' or 'defer'. False if the unit already has that decision (no second event)."""
    stored = "deferred" if choice == "defer" else "overtime"
    current = decisions(s).get(unit_id)
    if current and current["choice"] == stored:
        return False
    today = sim_today(s)
    if stored == "overtime":
        day = today + 1  # an extra crew tomorrow: it does not take a normal slot
        add_event(s, today, "manager_decision", unit_id, "Overtime crew approved",
                  f"A manager approved an overtime crew for {unit_id} on {format_sim_date(day)}. It is now a work order.",
                  payload={"choice": "overtime", "day": day})
    else:
        add_event(s, today, "manager_decision", unit_id, "Risk accepted for now",
                  f"A manager accepted the risk on {unit_id} for now. No crew is scheduled.",
                  payload={"choice": "deferred"})
    return True
