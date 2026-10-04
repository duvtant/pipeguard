"""Call guardrails and the call state machine (techstack 7.8, Ebube guide section 9).

Ring timers live in call_requests.ring_expires_at (DB clock), never in process memory, so a restart
cannot lose a ringing call. Every state change is a compare-and-set UPDATE: a late answer or two
sweepers cannot double-fire.

    ringing --answer--> answered --call ends--> done
       +--decline / expiry--> missed --> attempt 2 (backup) ringing
                                            +--missed--> escalated + manager_alert
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import timezone

from sqlalchemy import text
from sqlmodel import Session

from core.config import get_settings
from core.db import notify, session_scope

log = logging.getLogger(__name__)
settings = get_settings()

TOP_BAND = 3        # at-risk units that may trigger a call per evaluation
DEDUP_DAYS = 3      # no repeat call for the same unit inside this many sim days...
WORSENED_BY = 0.15  # ...unless p_fail rose by at least this much since the last call


def _rows(s: Session, sql: str, **params) -> list:
    return s.execute(text(sql), params).mappings().all()


def sim_today(s: Session) -> int:
    return int(s.execute(text("SELECT sim_day FROM sim_state WHERE id = 1")).scalar() or 0)


def add_event(s: Session, sim_day: int, typ: str, unit_id: str | None, title: str, detail: str,
              severity: str = "info", payload: dict | None = None) -> int:
    """Insert into the decision log and tell the SSE relay. The NOTIFY fires on commit."""
    eid = s.execute(text(
        "INSERT INTO events (sim_day, type, unit_id, title, detail, severity, payload) "
        "VALUES (:d, :t, :u, :ti, :de, :sv, CAST(:p AS jsonb)) RETURNING id"),
        {"d": sim_day, "t": typ, "u": unit_id, "ti": title, "de": detail, "sv": severity,
         "p": json.dumps(payload or {})}).scalar_one()
    notify(s, "ui_event", eid)
    return eid


# ---------------------------------------------------------------- roster
def station_techs(s: Session, unit_id: str) -> list:
    """Technicians at the unit's station, primaries first, then backups."""
    return _rows(s, "SELECT t.id, t.name, t.language, t.is_backup FROM technicians t "
                    "JOIN units u ON u.station_id = t.station_id WHERE u.id = :u "
                    "ORDER BY t.is_backup, t.id", u=unit_id)


def _calls_today(s: Session, tech_id: int, day: int) -> int:
    return s.execute(text("SELECT count(*) FROM call_requests WHERE technician_id = :t AND sim_day = :d"),
                     {"t": tech_id, "d": day}).scalar_one()


def _pick_technician(s: Session, unit_id: str, day: int):
    for t in station_techs(s, unit_id):
        if _calls_today(s, t["id"], day) < settings.max_calls_per_tech_per_day:
            return t
    return None


def _backup_for(s: Session, unit_id: str, missed_tech_id: int):
    others = [t for t in station_techs(s, unit_id) if t["id"] != missed_tech_id]
    others.sort(key=lambda t: (not t["is_backup"], t["id"]))  # real backup first
    return others[0] if others else None


# ---------------------------------------------------------------- guardrails
def _saving(p_fail: float) -> float:
    return p_fail * settings.cost_breakdown - settings.cost_service


def _dup_reason(s: Session, unit_id: str, day: int, p_now: float) -> str | None:
    last = s.execute(text(
        "SELECT cr.sim_day, p.p_fail_h FROM call_requests cr "
        "LEFT JOIN predictions p ON p.unit_id = cr.unit_id AND p.sim_day = cr.sim_day "
        "WHERE cr.unit_id = :u ORDER BY cr.id DESC LIMIT 1"), {"u": unit_id}).first()
    if last is None or day - last.sim_day >= DEDUP_DAYS:
        return None
    if last.p_fail_h is not None and p_now - last.p_fail_h >= WORSENED_BY - 1e-9:
        return None  # status worsened since the last call
    return f"already called {day - last.sim_day} day(s) ago and the risk has not worsened"


def create_call_requests(s: Session, sim_day: int | None = None, top_n: int = TOP_BAND) -> dict:
    """Evaluate the guardrails and ring the technicians that pass. Called by the engine after each tick.

    Returns {"created": [call_request_id], "suppressed": [(unit_id, reason)]}.
    """
    day = sim_today(s) if sim_day is None else sim_day
    latest = _rows(s, "SELECT DISTINCT ON (p.unit_id) p.unit_id, p.p_fail_h, p.status "
                      "FROM predictions p JOIN units u ON u.id = p.unit_id "
                      "WHERE p.sim_day <= :day AND u.status <> 'failed' "
                      "ORDER BY p.unit_id, p.sim_day DESC", day=day)
    busy = {r["unit_id"] for r in _rows(s, "SELECT unit_id FROM call_requests "
                                           "WHERE state IN ('ringing', 'answered')")}
    cands = [(r["unit_id"], r["p_fail_h"]) for r in latest
             if r["status"] == "at_risk" and r["unit_id"] not in busy]
    # Same order as the scheduler: saving rounded to $1,000, then unit id.
    cands.sort(key=lambda c: (-round(_saving(c[1]), -3), c[0]))

    out: dict = {"created": [], "suppressed": []}
    for uid, p_now in cands[:top_n]:
        s.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"call:{uid}"})
        if s.execute(text("SELECT 1 FROM call_requests WHERE unit_id = :u AND state IN ('ringing', 'answered')"),
                     {"u": uid}).first():
            continue  # someone else just created it
        why = _dup_reason(s, uid, day, p_now)
        tech = None if why else _pick_technician(s, uid, day)
        if not why and tech is None:
            why = "daily call cap reached for every technician at the station"
        if why:
            log.info("call suppressed for %s: %s", uid, why)
            out["suppressed"].append((uid, why))
            continue
        out["created"].append(_ring(s, uid, tech, day, attempt=1))
    return out


# ---------------------------------------------------------------- state machine
def _ring(s: Session, unit_id: str, tech, day: int, attempt: int) -> int:
    cid = s.execute(text(
        "INSERT INTO call_requests (unit_id, technician_id, sim_day, state, attempt, ring_expires_at) "
        "VALUES (:u, :t, :d, 'ringing', :a, now() + make_interval(secs => :secs)) RETURNING id"),
        {"u": unit_id, "t": tech["id"], "d": day, "a": attempt,
         "secs": float(settings.ring_seconds)}).scalar_one()
    add_event(s, day, "call_requested", unit_id, "Call requested",
              f"Calling {tech['name']} about {unit_id}." + (" (backup technician)" if attempt == 2 else ""),
              payload={"technician_id": tech["id"], "call_request_id": cid})
    return cid


def answer_call(s: Session, cid: int) -> bool:
    """ringing -> answered. False if it already expired or was answered (late answer fails cleanly)."""
    row = s.execute(text(
        "UPDATE call_requests SET state = 'answered' "
        "WHERE id = :id AND state = 'ringing' AND ring_expires_at > now() "
        "RETURNING unit_id, technician_id, sim_day"), {"id": cid}).first()
    if row is None:
        return False
    t = s.execute(text("SELECT name, language FROM technicians WHERE id = :t"), {"t": row.technician_id}).one()
    add_event(s, row.sim_day, "call_answered", row.unit_id, "Call answered",
              f"{t.name} answered. The call is in {'French' if t.language == 'fr' else 'English'}.",
              payload={"call_request_id": cid})
    return True


def miss_call(s: Session, cid: int, why: str = "expired") -> bool:
    """ringing -> missed. Attempt 1 rings the backup; otherwise escalate to the manager."""
    row = s.execute(text(
        "UPDATE call_requests SET state = 'missed' WHERE id = :id AND state = 'ringing' "
        "RETURNING unit_id, technician_id, sim_day, attempt"), {"id": cid}).first()
    if row is None:
        return False
    log.info("call %s (%s) %s", cid, row.unit_id, why)
    if row.attempt == 1:
        backup = _backup_for(s, row.unit_id, row.technician_id)
        if backup:
            _ring(s, row.unit_id, backup, row.sim_day, attempt=2)
            return True
    s.execute(text("UPDATE call_requests SET state = 'escalated' WHERE id = :id AND state = 'missed'"), {"id": cid})
    add_event(s, row.sim_day, "manager_alert", row.unit_id, "Call not answered",
              f"No technician answered for {row.unit_id}. A manager needs to follow up.", "critical",
              {"call_request_id": cid})
    return True


def finish_call(s: Session, cid: int) -> bool:
    """answered -> done. A call that ends with no tool call changes nothing and the unit stays flagged."""
    return s.execute(text("UPDATE call_requests SET state = 'done' WHERE id = :id AND state = 'answered' "
                          "RETURNING id"), {"id": cid}).first() is not None


def sweep_expired(s: Session, limit: int = 50) -> int:
    """Expire rings whose time ran out. SKIP LOCKED: two sweepers never handle the same row."""
    ids = [r[0] for r in s.execute(text(
        "SELECT id FROM call_requests WHERE state = 'ringing' AND ring_expires_at < now() "
        "ORDER BY id LIMIT :n FOR UPDATE SKIP LOCKED"), {"n": limit})]
    return sum(miss_call(s, i, "expired") for i in ids)


def sweep_once() -> int:
    with session_scope() as s:
        return sweep_expired(s)


async def sweeper_loop(interval: float = 1.0) -> None:
    """Background task started by the API. A failed tick is logged and retried, never fatal."""
    while True:
        try:
            await asyncio.to_thread(sweep_once)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("sweeper tick failed")
        await asyncio.sleep(interval)


# ---------------------------------------------------------------- phone page helpers
def technician_by_slug(s: Session, slug: str):
    return s.execute(text("SELECT id, name, language, is_backup FROM technicians WHERE field_page_id = :s"),
                     {"s": slug}).mappings().first()


def ringing_request(s: Session, tech_id: int, live_only: bool = True) -> int | None:
    """The call currently ringing for this technician. live_only skips rings past their expiry."""
    extra = " AND ring_expires_at > now()" if live_only else ""
    return s.execute(text("SELECT id FROM call_requests WHERE technician_id = :t AND state = 'ringing'"
                          + extra + " ORDER BY id DESC LIMIT 1"), {"t": tech_id}).scalar()


def ring_payload(s: Session, cid: int) -> dict | None:
    """RingEvent shape (contract 4.3) for one call request."""
    r = s.execute(text(
        "SELECT cr.id, cr.unit_id, cr.technician_id, cr.ring_expires_at, t.name AS tname, t.language, "
        "st.name AS sname, COALESCE(p.rul_low, 0) AS rul_low, COALESCE(p.rul_high, 0) AS rul_high, "
        "COALESCE(p.reason, '') AS reason "
        "FROM call_requests cr JOIN technicians t ON t.id = cr.technician_id "
        "JOIN units u ON u.id = cr.unit_id JOIN stations st ON st.id = u.station_id "
        "LEFT JOIN LATERAL (SELECT rul_low, rul_high, reason FROM predictions "
        "                   WHERE unit_id = cr.unit_id ORDER BY sim_day DESC LIMIT 1) p ON true "
        "WHERE cr.id = :id"), {"id": cid}).mappings().first()
    if r is None:
        return None
    return {"type": "ring", "call_request_id": r["id"], "unit_id": r["unit_id"], "station_name": r["sname"],
            "technician_id": r["technician_id"], "technician_name": r["tname"], "language": r["language"],
            "rul_low": float(r["rul_low"]), "rul_high": float(r["rul_high"]), "reason": r["reason"],
            "expires_at": r["ring_expires_at"].astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}


def link_conversation(s: Session, tech_id: int, conversation_id: str, ended: bool = False) -> None:
    """Phone reports the ElevenLabs conversation id (on connect, again on hang-up). Idempotent."""
    cr = s.execute(text("SELECT cr.id, t.language FROM call_requests cr JOIN technicians t ON t.id = cr.technician_id "
                        "WHERE cr.technician_id = :t AND cr.state IN ('answered', 'done') "
                        "ORDER BY cr.id DESC LIMIT 1"), {"t": tech_id}).first()
    if cr is None:
        return
    s.execute(text("INSERT INTO calls (call_request_id, conversation_id, language) VALUES (:c, :v, :l) "
                   "ON CONFLICT (conversation_id) DO UPDATE SET "
                   "call_request_id = COALESCE(calls.call_request_id, EXCLUDED.call_request_id)"),
              {"c": cr.id, "v": conversation_id, "l": cr.language})
    if ended:
        finish_call(s, cr.id)
