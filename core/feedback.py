"""Threshold adjustment from technician verdicts.

Owner: Olise. Spec: Olise guide section 11, techstack section 7.7.

adjust_threshold(verdicts, current) -> (new_threshold, message | None)
  window      the last 10 verdicts, at most one per unit (the newest), so a burst of verdicts from one
              unit cannot swing the global threshold
  hit rate    hits / window, where confirmed_wear and part_replaced are hits (the wear was real) and
              looks_fine is a false alarm
  rule        hit rate < 60% -> threshold + 0.05 (max 0.9); > 85% -> threshold - 0.05 (min 0.2)
  pacing      it moves at most one step per call, and only when the newest verdict is new information:
              a repeat of the same verdict from a unit already in the window changes nothing
  small data  fewer than MIN_VERDICTS distinct units in the window -> no change

Call it once per new verdict, with all verdicts so far (chronological). Pure function.
"""
from __future__ import annotations

from core.contracts import FeedbackResult, VerdictRecord

WINDOW: int = 10
MIN_VERDICTS: int = 3
STEP: float = 0.05
LOW_HIT_RATE: float = 0.60
HIGH_HIT_RATE: float = 0.85
MIN_THRESHOLD: float = 0.2
MAX_THRESHOLD: float = 0.9
LOOKS_FINE_DAYS: int = 7
LOOKS_FINE_URGENCY: float = 0.5
HITS = ("confirmed_wear", "part_replaced")


def _window(verdicts: list[VerdictRecord]) -> list[VerdictRecord]:
    """Last WINDOW verdicts, newest per unit only, oldest first."""
    seen: set[str] = set()
    out: list[VerdictRecord] = []
    for v in reversed(verdicts):
        if v.unit_id in seen:
            continue
        seen.add(v.unit_id)
        out.append(v)
        if len(out) == WINDOW:
            break
    return out[::-1]


def hit_rate(verdicts: list[VerdictRecord]) -> float | None:
    w = _window(verdicts)
    return sum(v.verdict in HITS for v in w) / len(w) if w else None


def adjust_threshold(verdicts: list[VerdictRecord], current: float) -> tuple[float, str | None]:
    current = min(MAX_THRESHOLD, max(MIN_THRESHOLD, float(current)))
    if not verdicts:
        return current, None
    newest = verdicts[-1]
    earlier = verdicts[:-1]
    # A repeat of the same verdict from a unit already in the window is not new information.
    if any(v.unit_id == newest.unit_id and v.verdict == newest.verdict for v in _window(earlier)):
        return current, None
    w = _window(verdicts)
    if len(w) < MIN_VERDICTS:
        return current, None
    rate = sum(v.verdict in HITS for v in w) / len(w)
    if rate < LOW_HIT_RATE:
        new = min(MAX_THRESHOLD, round(current + STEP, 4))
    elif rate > HIGH_HIT_RATE:
        new = max(MIN_THRESHOLD, round(current - STEP, 4))
    else:
        new = current
    if new == current:
        return current, None
    why = "too many false alarms" if new > current else "alerts are almost always confirmed"
    msg = (f"Feedback received, threshold adjusted from {current:.2f} to {new:.2f} "
           f"({sum(v.verdict in HITS for v in w)} of the last {len(w)} alerts confirmed: {why}).")
    return new, msg


def urgency_multipliers(verdicts: list[VerdictRecord], today: int) -> dict[str, float]:
    """looks_fine lowers that unit's urgency for 7 simulated days (multiplier for the scheduler)."""
    out: dict[str, float] = {}
    for v in verdicts:
        if v.verdict == "looks_fine" and 0 <= today - v.sim_day < LOOKS_FINE_DAYS:
            out[v.unit_id] = LOOKS_FINE_URGENCY
        elif v.unit_id in out and v.verdict != "looks_fine" and v.sim_day >= today - LOOKS_FINE_DAYS:
            out.pop(v.unit_id)  # a later confirmation cancels the discount
    return out


def process_feedback(verdicts: list[VerdictRecord], current: float, today: int) -> FeedbackResult:
    """Everything the API needs after a new verdict: threshold, message, urgency, units to reset."""
    new, msg = adjust_threshold(verdicts, current)
    reset = [verdicts[-1].unit_id] if verdicts and verdicts[-1].verdict == "part_replaced" else []
    return FeedbackResult(threshold=new, message=msg, urgency=urgency_multipliers(verdicts, today), reset_units=reset)
