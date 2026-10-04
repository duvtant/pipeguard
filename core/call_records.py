"""Store ElevenLabs call records: the post-call webhook and the pull fallback (techstack 12.6, guide 8.6).

One function, store_call(), serves both paths, so a pulled call and a webhook call look identical.
It never rejects a payload for a missing or unknown field. Same conversation twice changes nothing twice.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import urllib.request

from sqlalchemy import text
from sqlmodel import Session

from core.alerts import add_event, finish_call, sim_today
from core.config import get_settings
from core.db import session_scope
from core.tech_actions import VERDICTS, record_feedback
from core.voice_tools import norm_int, norm_unit, submit_availability

log = logging.getLogger(__name__)
settings = get_settings()

PULL_RETRY_SECS = 15.0     # between pull attempts for one conversation
PULL_GIVE_UP_MINUTES = 15  # stop trying after this long
_last_pull: dict[str, float] = {}


# ---------------------------------------------------------------- reading the payload (all tolerant)
def _evaluation(analysis: dict):
    """The report card as [{criteria_id, result, rationale}], or None when the call has none."""
    lst = analysis.get("evaluation_criteria_results_list")
    if isinstance(lst, list):
        return lst
    alt = analysis.get("evaluation_criteria_results")
    if isinstance(alt, list):
        return alt
    if isinstance(alt, dict):
        return [{"criteria_id": k, "result": (v or {}).get("result") if isinstance(v, dict) else None,
                 "rationale": (v or {}).get("rationale") if isinstance(v, dict) else None}
                for k, v in alt.items()]
    return None


def _flatten(collected) -> dict | None:
    """data_collection_results {name: {value, rationale}} -> {name: value}, the shape the dashboard reads."""
    if not isinstance(collected, dict):
        return None
    return {k: (v.get("value") if isinstance(v, dict) else v) for k, v in collected.items()}


def _tool_succeeded(transcript, tool_name: str) -> bool:
    """True if the live tool call worked, so the after-call fallback must not apply it a second time."""
    for turn in transcript if isinstance(transcript, list) else []:
        for r in (turn or {}).get("tool_results") or []:
            if not isinstance(r, dict) or r.get("tool_name") != tool_name or r.get("is_error"):
                continue
            try:
                if json.loads(r.get("result_value") or "{}").get("ok") is True:
                    return True
            except (TypeError, ValueError, AttributeError):
                continue
    return False


# ---------------------------------------------------------------- storing
def store_call(s: Session, data: dict, received_via: str = "webhook") -> dict:
    """Upsert the calls row, close the call request, write one call_summary event, apply fallbacks."""
    conv = data.get("conversation_id")
    if not conv:
        return {"stored": False, "reason": "no conversation_id"}
    analysis = data.get("analysis") if isinstance(data.get("analysis"), dict) else {}
    meta = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    init = data.get("conversation_initiation_client_data")
    dyn = (init.get("dynamic_variables") if isinstance(init, dict) else None) or {}
    transcript = data.get("transcript")  # stored exactly as sent: it carries tool_calls, tool_results, guardrails
    collected = _flatten(analysis.get("data_collection_results"))
    evaluation = _evaluation(analysis)
    cr_id = norm_int(dyn.get("call_request_id"))

    s.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"conv:{conv}"})
    cr = s.execute(text("SELECT cr.id, cr.unit_id, cr.technician_id, t.language FROM call_requests cr "
                        "JOIN technicians t ON t.id = cr.technician_id WHERE cr.id = :c"),
                   {"c": cr_id}).mappings().first() if cr_id is not None else None

    row = s.execute(text(
        "INSERT INTO calls (call_request_id, conversation_id, language, transcript, summary, data_collection, "
        "evaluation, duration_secs, received_via) "
        "VALUES (:c, :v, COALESCE(:l, 'en'), CAST(:t AS jsonb), :s, CAST(:d AS jsonb), CAST(:e AS jsonb), :n, :r) "
        "ON CONFLICT (conversation_id) DO UPDATE SET "
        "call_request_id = COALESCE(EXCLUDED.call_request_id, calls.call_request_id), "
        "language = COALESCE(:l, calls.language), "
        "transcript = COALESCE(EXCLUDED.transcript, calls.transcript), "
        "summary = COALESCE(EXCLUDED.summary, calls.summary), "
        "data_collection = COALESCE(EXCLUDED.data_collection, calls.data_collection), "
        "evaluation = COALESCE(EXCLUDED.evaluation, calls.evaluation), "
        "duration_secs = COALESCE(EXCLUDED.duration_secs, calls.duration_secs), "
        "received_via = EXCLUDED.received_via "
        "RETURNING id, call_request_id"),
        {"c": cr_id, "v": conv, "l": cr["language"] if cr else None,
         "t": json.dumps(transcript) if transcript is not None else None,
         "s": analysis.get("transcript_summary"),
         "d": json.dumps(collected) if collected is not None else None,
         "e": json.dumps(evaluation) if evaluation is not None else None,
         "n": norm_int(meta.get("call_duration_secs")), "r": received_via}).mappings().one()
    call_id = row["id"]

    # The phone may have linked this conversation earlier, so the request id can come from the stored row.
    if cr is None and row["call_request_id"] is not None:
        cr = s.execute(text("SELECT cr.id, cr.unit_id, cr.technician_id, t.language FROM call_requests cr "
                            "JOIN technicians t ON t.id = cr.technician_id WHERE cr.id = :c"),
                       {"c": row["call_request_id"]}).mappings().first()
    cr_id = cr["id"] if cr else None
    unit_id = (cr["unit_id"] if cr else None) or norm_unit(dyn.get("unit_id")) or norm_unit((collected or {}).get("unit_mentioned"))

    if cr_id is not None:
        finish_call(s, cr_id)  # a webhook means the call is over, even if the phone never said so

    fallback = _apply_fallbacks(s, cr, collected, transcript) if cr else []
    if fallback:
        s.execute(text("UPDATE calls SET received_via = 'webhook_fallback' WHERE id = :i"), {"i": call_id})

    if not s.execute(text("SELECT 1 FROM events WHERE type = 'call_summary' AND payload->>'call_id' = :i"),
                     {"i": str(call_id)}).first():
        detail = ((collected or {}).get("english_summary") or analysis.get("transcript_summary")
                  or "The call has ended.")  # English first: French calls need it for the manager
        add_event(s, sim_today(s), "call_summary", unit_id, "Call summary", str(detail),
                  payload={"call_id": call_id, "call_request_id": cr_id})
    return {"stored": True, "call_id": call_id, "call_request_id": cr_id, "fallback": fallback}


def _apply_fallbacks(s: Session, cr, collected: dict | None, transcript) -> list[str]:
    """If a live tool call failed, apply what the after-call extraction heard. Never applies anything twice."""
    applied: list[str] = []
    collected = collected or {}
    day_text = str(collected.get("available_day") or "").strip()
    already = s.execute(text("SELECT 1 FROM constraints WHERE call_request_id = :c"), {"c": cr["id"]}).first()
    if day_text and not already and not _tool_succeeded(transcript, "submit_availability"):
        try:
            with s.begin_nested():
                r = submit_availability(s, {"unit_id": cr["unit_id"], "technician_id": cr["technician_id"],
                                            "earliest_day_text": day_text, "call_request_id": cr["id"]})
            if r.get("ok"):
                applied.append("availability")
        except Exception:
            log.exception("availability fallback failed for call request %s", cr["id"])
    verdict = str(collected.get("verdict") or "").strip().lower()
    if verdict in VERDICTS and not _tool_succeeded(transcript, "feedback"):
        try:
            with s.begin_nested():
                record_feedback(s, cr["unit_id"], cr["technician_id"], verdict, None)
            applied.append("feedback")
        except Exception:
            log.exception("feedback fallback failed for call request %s", cr["id"])
    return applied


# ---------------------------------------------------------------- pull fallback
def fetch_conversation(conversation_id: str) -> dict | None:
    """GET the conversation from ElevenLabs. None if not configured, not ready or failing."""
    if not settings.elevenlabs_api_key:
        return None
    req = urllib.request.Request(f"https://api.elevenlabs.io/v1/convai/conversations/{conversation_id}",
                                 headers={"xi-api-key": settings.elevenlabs_api_key})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.load(resp)
    except Exception as exc:  # 404 while ElevenLabs is still processing is normal: retry later
        log.info("pull for %s not ready: %s", conversation_id, exc)
        return None


def pull_pending() -> int:
    """Calls that ended over a minute ago and still have no transcript: fetch them. Returns how many stored."""
    with session_scope() as s:
        due = [r[0] for r in s.execute(text(
            "SELECT conversation_id FROM calls WHERE transcript IS NULL AND ended_at IS NOT NULL "
            "AND ended_at < now() - make_interval(secs => :w) "
            "AND ended_at > now() - make_interval(secs => :m)"),
            {"w": float(settings.webhook_pull_seconds), "m": PULL_GIVE_UP_MINUTES * 60.0})]
    stored = 0
    for conv in due:
        if time.monotonic() - _last_pull.get(conv, -1e9) < PULL_RETRY_SECS:
            continue
        _last_pull[conv] = time.monotonic()
        data = fetch_conversation(conv)
        if not data or not data.get("transcript"):
            continue
        data.setdefault("conversation_id", conv)
        with session_scope() as s:
            stored += bool(store_call(s, data, received_via="pull").get("stored"))
    return stored


async def pull_loop(interval: float = 5.0) -> None:
    while True:
        try:
            await asyncio.to_thread(pull_pending)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("pull tick failed")
        await asyncio.sleep(interval)
