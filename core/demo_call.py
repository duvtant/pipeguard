"""Simulate a technician call with no phone: the demo safety net (guide 8.8).

It goes through EXACTLY the code a live call uses: the call request and its state machine (core.alerts),
the voice tool (core.voice_tools.submit_availability) and the call record store (core.call_records.store_call).
If this path ever diverged from a real call it would be worthless as a fallback. Only the voice is replaced:
a recorded conversation (infra/recorded_call.json, or a built-in script when that file is absent).

The steps are spaced out so the dashboard fills in live, like a real call, instead of everything at once.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from sqlalchemy import text
from sqlmodel import Session

from core import alerts
from core.call_records import store_call
from core.db import session_scope
from core.dayparse import weekday_name
from core.voice_tools import norm_unit, submit_availability

log = logging.getLogger(__name__)

RECORDED = Path(__file__).resolve().parents[1] / "infra" / "recorded_call.json"
STEP_SECS = 1.5  # pause between the visible steps; tests set it to 0


class NothingToSimulate(ValueError):
    pass


def pick_target(s: Session, unit_id: str | None = None, technician_id: int | None = None) -> dict:
    """The unit whose planned service the call will move, and the technician who gets the call."""
    uid = norm_unit(unit_id) if unit_id else None
    if unit_id and not uid:
        raise NothingToSimulate("unknown unit")
    row = s.execute(text(
        "SELECT p.unit_id, p.planned_day, p.technician_id FROM plan_items p WHERE p.state = 'planned' "
        + ("AND p.unit_id = :u " if uid else "") + "ORDER BY p.planned_day, p.expected_saving DESC, p.unit_id LIMIT 1"),
        {"u": uid} if uid else {}).mappings().first()
    if row is None:
        raise NothingToSimulate("no planned service to move" if not uid else "unit has no planned service to move")
    tech_id = technician_id or row["technician_id"]
    tech = s.execute(text(
        "SELECT t.id, t.name, t.language, t.field_page_id FROM technicians t JOIN units u ON u.station_id = t.station_id "
        "WHERE u.id = :u AND (:t IS NULL OR t.id = :t) ORDER BY t.is_backup, t.id LIMIT 1"),
        {"u": row["unit_id"], "t": tech_id}).mappings().first()
    if tech is None:
        raise NothingToSimulate("unknown technician for this unit")
    return {"unit_id": row["unit_id"], "planned_day": int(row["planned_day"]), "technician": dict(tech)}


def start(s: Session, target: dict) -> int:
    """Step 1: the ring. Same insert and event as a real call (guardrails are the engine's job, not ours)."""
    return alerts._ring(s, target["unit_id"], target["technician"], alerts.sim_today(s), attempt=1)


def _day_text(today: int, planned_day: int) -> str:
    """Ask for the day after the current plan, so the call visibly moves the unit."""
    n = planned_day + 1 - today
    return weekday_name(planned_day + 1) if 0 < n < 7 else f"in {max(n, 1)} days"


def _recorded() -> dict | None:
    try:
        raw = json.loads(RECORDED.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    data = raw.get("data") if isinstance(raw, dict) and isinstance(raw.get("data"), dict) else raw
    return data if isinstance(data, dict) and isinstance(data.get("transcript"), list) else None


def _recorded_day_text(data: dict) -> str | None:
    for turn in data["transcript"]:
        for call in (turn or {}).get("tool_calls") or []:
            if isinstance(call, dict) and call.get("tool_name") == "submit_availability":
                try:
                    txt = json.loads(call.get("params_as_json") or "{}").get("earliest_day_text")
                except ValueError:
                    continue
                if txt:
                    return str(txt)
    dc = (data.get("analysis") or {}).get("data_collection_results") or {}
    value = (dc.get("available_day") or {}).get("value") if isinstance(dc.get("available_day"), dict) else dc.get("available_day")
    return str(value) if value else None


def _scripted(target: dict, day_text: str, result: dict, cid: int, rul: tuple[float, float]) -> dict:
    """The built-in call, shaped like an ElevenLabs conversation so it is stored like any other."""
    tech, uid = target["technician"], target["unit_id"]
    first = tech["name"].split()[0]
    params = json.dumps({"unit_id": uid, "technician_id": tech["id"], "earliest_day_text": day_text})
    say = result.get("say", "")
    summary = f"{tech['name']} cannot service {uid} before {day_text}. {say}"
    return {
        "conversation_id": f"conv_sim_{cid}", "status": "done",
        "transcript": [
            {"role": "agent", "time_in_call_secs": 0, "message":
                f"Hi {first}, this is PipeGuard. {uid} is showing wear and may fail in {rul[0]:.0f} to {rul[1]:.0f} days. "
                "Can your crew service it this week?"},
            {"role": "user", "time_in_call_secs": 9, "message": f"Not before {day_text}."},
            {"role": "agent", "time_in_call_secs": 12, "message": "", "tool_calls": [
                {"request_id": f"sim_{cid}", "tool_name": "submit_availability", "params_as_json": params,
                 "tool_has_been_called": True}],
             "tool_results": [{"request_id": f"sim_{cid}", "tool_name": "submit_availability", "is_error": False,
                               "result_value": json.dumps(result), "tool_latency_secs": 0.1}]},
            {"role": "agent", "time_in_call_secs": 14, "message": say},
        ],
        "metadata": {"call_duration_secs": 24},
        "analysis": {"transcript_summary": summary, "call_successful": "success",
                     "data_collection_results": {"available_day": {"value": day_text}, "verdict": {"value": ""},
                                                 "unit_mentioned": {"value": uid},
                                                 "english_summary": {"value": summary}}},
        "conversation_initiation_client_data": {"dynamic_variables": {"call_request_id": str(cid), "unit_id": uid}},
    }


def finish(cid: int, target: dict, step_secs: float | None = None) -> None:
    """Steps 2 to 4, run in the background: answer, the voice tool, then the call record (the 'webhook')."""
    pause = STEP_SECS if step_secs is None else step_secs
    uid, tech = target["unit_id"], target["technician"]
    try:
        time.sleep(pause)
        with session_scope() as s:
            if not alerts.answer_call(s, cid):  # same compare-and-set as a real answer
                log.warning("simulate-call %s: ring already expired or answered", cid)
                return
        time.sleep(pause)
        recorded = _recorded()
        with session_scope() as s:
            today = alerts.sim_today(s)
            day_text = (_recorded_day_text(recorded) if recorded else None) or _day_text(today, target["planned_day"])
            rul = s.execute(text("SELECT rul_low, rul_high FROM predictions WHERE unit_id = :u ORDER BY sim_day DESC LIMIT 1"),
                            {"u": uid}).first() or (0.0, 0.0)
        with session_scope() as s:
            result = submit_availability(s, {"unit_id": uid, "technician_id": tech["id"],
                                             "earliest_day_text": day_text, "call_request_id": cid})
        time.sleep(pause)
        data = recorded if recorded else _scripted(target, day_text, result, cid, (float(rul[0]), float(rul[1])))
        if recorded:  # link the recording to this call request, with an id that cannot collide on a repeat
            data = {**recorded, "conversation_id": f"conv_sim_{cid}"}
            init = dict(data.get("conversation_initiation_client_data") or {})
            init["dynamic_variables"] = {**(init.get("dynamic_variables") or {}), "call_request_id": str(cid), "unit_id": uid}
            data["conversation_initiation_client_data"] = init
        with session_scope() as s:
            store_call(s, data, received_via="simulated")
    except Exception:
        log.exception("simulate-call %s failed", cid)
