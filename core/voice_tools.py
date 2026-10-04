"""Logic behind the ElevenLabs server tools (techstack 11.4).

Rules: a person is on the line. Every function returns {"ok": bool, "say": str} and never raises.
Bad input gives ok=False and a question the agent can speak. Same input twice changes nothing twice.
"""
from __future__ import annotations

import logging
import re

from sqlalchemy import text
from sqlmodel import Session

from core.alerts import add_event, sim_today
from core.dayparse import ASK, resolve_day, weekday_name
from core.tech_actions import VERDICTS, record_feedback

log = logging.getLogger(__name__)

SAY = {
    "en": {
        "unknown_unit": "Sorry, I don't recognise that unit. Can you repeat the unit number?",
        "moved": "Got it. {unit} moves to {day}.",
        "also": " {other} also moves to {oday}.",
        "unchanged": "Got it. {unit} is already planned for {day}, so nothing changes.",
        "not_planned": "Noted. {unit} won't be scheduled before {day}.",
        "removed": "Got it. {unit} is no longer on this week's plan.",
        "manager": "Got it, but {unit} cannot be serviced before it may fail. I've flagged it for a manager.",
        "degraded": "Got it. I've noted that you can't service {unit} before {day}. The plan will update shortly.",
        "error": "Sorry, something went wrong on my side. A manager will follow up.",
        "feedback": "Thanks, I've recorded that.",
        "bad_verdict": "Sorry, I didn't catch that. Is the wear confirmed, does it look fine, or was the part replaced?",
        "report": "Thanks, I've logged your field report.",
        "status": "{unit} is {state}.{rul}{plan}",
        "state": {"healthy": "healthy", "watch": "on watch", "at_risk": "at risk"},
        "rul": " About {lo} to {hi} days left.",
        "plan": " It is planned for {day}.",
        "no_plan": " It is not on this week's plan.",
        "no_data": "{unit} has no prediction yet.",
    },
    "fr": {
        "unknown_unit": "Désolé, je ne reconnais pas cette unité. Pouvez-vous répéter le numéro ?",
        "moved": "C'est noté. {unit} est décalé à {day}.",
        "also": " {other} passe aussi à {oday}.",
        "unchanged": "C'est noté. {unit} est déjà prévu pour {day}, rien ne change.",
        "not_planned": "C'est noté. {unit} ne sera pas planifié avant {day}.",
        "removed": "C'est noté. {unit} n'est plus au plan de cette semaine.",
        "manager": "C'est noté, mais {unit} ne peut pas être traité avant un risque de panne. J'ai prévenu un responsable.",
        "degraded": "C'est noté. Vous ne pouvez pas intervenir sur {unit} avant {day}. Le plan sera mis à jour sous peu.",
        "error": "Désolé, un problème est survenu de mon côté. Un responsable vous recontactera.",
        "feedback": "Merci, c'est enregistré.",
        "bad_verdict": "Désolé, je n'ai pas compris. L'usure est-elle confirmée, tout va bien, ou la pièce a-t-elle été remplacée ?",
        "report": "Merci, j'ai enregistré votre rapport.",
        "status": "{unit} est {state}.{rul}{plan}",
        "state": {"healthy": "en bonne santé", "watch": "sous surveillance", "at_risk": "à risque"},
        "rul": " Environ {lo} à {hi} jours restants.",
        "plan": " Il est prévu pour {day}.",
        "no_plan": " Il n'est pas au plan de cette semaine.",
        "no_data": "{unit} n'a pas encore de prédiction.",
    },
}


def _t(lang: str, key: str, **kw) -> str:
    return SAY["fr" if lang == "fr" else "en"][key].format(**kw)


# ---------------------------------------------------------------- input cleaning (the LLM fills these in)
def norm_unit(raw) -> str | None:
    """'eds 7', 'EDS-07', 'unit EDS-7' -> 'EDS-07'."""
    m = re.search(r"([A-Za-z]{3})[\s\-_]*0*(\d{1,2})\b", str(raw or ""))
    return f"{m.group(1).upper()}-{int(m.group(2)):02d}" if m else None


def norm_int(raw) -> int | None:
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return None


def _tech(s: Session, tech_id: int | None):
    if tech_id is None:
        return None
    return s.execute(text("SELECT id, name, language FROM technicians WHERE id = :t"), {"t": tech_id}).mappings().first()


def _unit_exists(s: Session, unit_id: str | None) -> bool:
    return bool(unit_id) and s.execute(text("SELECT 1 FROM units WHERE id = :u"), {"u": unit_id}).first() is not None


def error_say(lang: str = "en") -> dict:
    return {"ok": False, "say": _t(lang, "error")}


# ---------------------------------------------------------------- tools
def submit_availability(s: Session, data: dict) -> dict:
    unit_id, tech_id = norm_unit(data.get("unit_id")), norm_int(data.get("technician_id"))
    tech = _tech(s, tech_id)
    lang = tech["language"] if tech else "en"
    if not _unit_exists(s, unit_id):
        return {"ok": False, "say": _t(lang, "unknown_unit")}

    today = sim_today(s)
    parsed = resolve_day(str(data.get("earliest_day_text") or ""), today, lang)
    if parsed.day is None:
        return {"ok": False, "say": parsed.clarify or ASK[lang]}
    day = parsed.day
    note = (str(data.get("note")) if data.get("note") else None)

    # The tool does not send call_request_id, so use this technician's current call about this unit.
    cr_id = norm_int(data.get("call_request_id"))
    if cr_id is None and tech_id is not None:
        cr_id = s.execute(text("SELECT id FROM call_requests WHERE technician_id = :t AND unit_id = :u "
                               "AND state IN ('answered', 'done') ORDER BY id DESC LIMIT 1"),
                          {"t": tech_id, "u": unit_id}).scalar()

    # Idempotent: the LLM may call this twice. NULLs are distinct in the unique index, so check in code too.
    s.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"constraint:{unit_id}"})
    exists = s.execute(text(
        "SELECT 1 FROM constraints WHERE unit_id = :u AND technician_id IS NOT DISTINCT FROM :t "
        "AND earliest_day = :d AND call_request_id IS NOT DISTINCT FROM :c"),
        {"u": unit_id, "t": tech_id, "d": day, "c": cr_id}).first()
    if not exists:
        s.execute(text("INSERT INTO constraints (technician_id, unit_id, earliest_day, note, source, call_request_id) "
                       "VALUES (:t, :u, :d, :n, 'voice', :c)"),
                  {"t": tech_id, "u": unit_id, "d": day, "n": note, "c": cr_id})
        who = tech["name"] if tech else "The technician"
        add_event(s, today, "constraint_added", unit_id, "Constraint added",
                  f"{who} cannot service {unit_id} before day {day} ({weekday_name(day)}).",
                  payload={"earliest_day": day, "call_request_id": cr_id})

    dayname = weekday_name(day, lang)
    try:
        from core.replan import replan
        with s.begin_nested():  # a failed re-plan must not undo the saved constraint
            result = replan(s, reason=f"technician unavailable before {weekday_name(day)}")
    except Exception:
        log.exception("replan failed after constraint for %s", unit_id)
        return {"ok": True, "say": _t(lang, "degraded", unit=unit_id, day=dayname), "earliest_day": day}

    return {"ok": True, "say": _plan_sentence(result, unit_id, lang, day), "earliest_day": day}


def _plan_sentence(result, unit_id: str, lang: str, requested_day: int) -> str:
    mine = next((c for c in result.changes if c.unit_id == unit_id and c.kind != "unchanged"), None)
    item = next((i for i in result.items if i.unit_id == unit_id), None)
    if unit_id in result.needs_manager_decision:
        return _t(lang, "manager", unit=unit_id)
    if mine and mine.kind in ("moved", "added"):
        say = _t(lang, "moved", unit=unit_id, day=weekday_name(mine.new_day, lang))
    elif mine and mine.kind == "removed":
        return _t(lang, "removed", unit=unit_id)
    elif item:
        return _t(lang, "unchanged", unit=unit_id, day=weekday_name(item.planned_day, lang))
    else:
        return _t(lang, "not_planned", unit=unit_id, day=weekday_name(requested_day, lang))
    other = next((c for c in result.changes if c.unit_id != unit_id and c.kind in ("moved", "added")), None)
    if other:
        say += _t(lang, "also", other=other.unit_id, oday=weekday_name(other.new_day, lang))
    return say


def unit_status(s: Session, data: dict) -> dict:
    unit_id = norm_unit(data.get("unit_id"))
    tech = _tech(s, norm_int(data.get("technician_id")))
    lang = tech["language"] if tech else "en"
    if not _unit_exists(s, unit_id):
        return {"ok": False, "say": _t(lang, "unknown_unit")}
    p = s.execute(text("SELECT status, rul_low, rul_high FROM predictions WHERE unit_id = :u "
                       "ORDER BY sim_day DESC LIMIT 1"), {"u": unit_id}).first()
    if p is None:
        return {"ok": True, "say": _t(lang, "no_data", unit=unit_id)}
    planned = s.execute(text("SELECT planned_day FROM plan_items WHERE unit_id = :u AND state <> 'done' "
                             "ORDER BY planned_day LIMIT 1"), {"u": unit_id}).scalar()
    rul = _t(lang, "rul", lo=round(p.rul_low), hi=round(p.rul_high)) if p.status != "healthy" else ""
    plan = (_t(lang, "plan", day=weekday_name(planned, lang)) if planned is not None
            else (_t(lang, "no_plan") if p.status != "healthy" else ""))
    return {"ok": True, "say": _t(lang, "status", unit=unit_id, state=SAY[lang]["state"].get(p.status, p.status),
                                  rul=rul, plan=plan)}


def feedback(s: Session, data: dict) -> dict:
    unit_id, tech_id = norm_unit(data.get("unit_id")), norm_int(data.get("technician_id"))
    lang = (_tech(s, tech_id) or {}).get("language", "en")
    verdict = str(data.get("verdict") or "").strip().lower()
    if verdict not in VERDICTS:
        return {"ok": False, "say": _t(lang, "bad_verdict")}
    if not _unit_exists(s, unit_id):
        return {"ok": False, "say": _t(lang, "unknown_unit")}
    record_feedback(s, unit_id, tech_id or 0, verdict, data.get("note") or None)
    return {"ok": True, "say": _t(lang, "feedback")}


def field_report(s: Session, data: dict) -> dict:
    unit_id, tech_id = norm_unit(data.get("unit_id")), norm_int(data.get("technician_id"))
    lang = (_tech(s, tech_id) or {}).get("language", "en")
    note = str(data.get("note") or "").strip()
    if not _unit_exists(s, unit_id):
        return {"ok": False, "say": _t(lang, "unknown_unit")}
    if not note:
        return {"ok": False, "say": ASK["fr"] if lang == "fr" else "Sorry, what would you like me to note down?"}
    day = sim_today(s)
    dup = s.execute(text(
        "SELECT 1 FROM events WHERE type = 'feedback_received' AND unit_id = :u AND sim_day = :d "
        "AND payload->>'kind' = 'field_report' AND payload->>'technician_id' = :t AND payload->>'note' = :n"),
        {"u": unit_id, "d": day, "t": str(tech_id), "n": note}).first()
    if not dup:  # reuses an existing event type; the contract has no field_report type
        add_event(s, day, "feedback_received", unit_id, "Field report", note,
                  payload={"kind": "field_report", "technician_id": str(tech_id), "note": note})
    return {"ok": True, "say": _t(lang, "report")}
