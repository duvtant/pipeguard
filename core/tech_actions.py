"""What a technician does, shared by the phone page and the voice tools (techstack 11.3, 11.4)."""
from sqlalchemy import text
from sqlmodel import Session

from core.alerts import add_event, sim_today

VERDICTS = ("confirmed_wear", "looks_fine", "part_replaced")


def record_feedback(s: Session, unit_id: str, technician_id: int, verdict: str, note: str | None = None) -> dict:
    """Store a verdict. Raises ValueError on a bad unit or verdict. Idempotent per unit, technician and day.

    TODO(Olise): threshold and urgency learning (core/feedback.py) is not wired in yet.
    """
    if verdict not in VERDICTS:
        raise ValueError("bad verdict")
    if not s.execute(text("SELECT 1 FROM units WHERE id = :u"), {"u": unit_id}).first():
        raise ValueError("unknown unit")
    day = sim_today(s)
    threshold = s.execute(text("SELECT threshold FROM engine_params WHERE id = 1")).scalar()
    out = {"threshold": float(threshold) if threshold is not None else 0.5}
    if s.execute(text("SELECT 1 FROM feedback WHERE unit_id = :u AND technician_id = :t AND verdict = :v "
                      "AND sim_day = :d"), {"u": unit_id, "t": technician_id, "v": verdict, "d": day}).first():
        return out  # same verdict twice (LLM retry or double tap): one row, one event
    s.execute(text("INSERT INTO feedback (unit_id, technician_id, verdict, note, sim_day) "
                   "VALUES (:u, :t, :v, :n, :d)"),
              {"u": unit_id, "t": technician_id, "v": verdict, "n": note, "d": day})
    if verdict == "part_replaced":  # new life starts tomorrow; the engine restarts its status memory
        s.execute(text("UPDATE units SET life_start_day = :d + 1, status = 'healthy', above_count = 0, "
                       "below_count = 0, serviced_count = serviced_count + 1 WHERE id = :u"),
                  {"d": day, "u": unit_id})
        s.execute(text("UPDATE plan_items SET state = 'done' WHERE unit_id = :u AND state <> 'done'"), {"u": unit_id})
    add_event(s, day, "feedback_received", unit_id, "Feedback received",
              f"Technician verdict: {verdict.replace('_', ' ')}.", payload={"verdict": verdict})
    return out
