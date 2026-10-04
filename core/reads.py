"""Read-side queries for the dashboard. Every function returns plain dicts shaped like web/src/lib/types.ts.

Caller owns the session. Nothing here writes. Missing data degrades to safe defaults (a unit with no
prediction yet still appears) because a half-empty database must not take the dashboard down.
"""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from sqlalchemy import text
from sqlmodel import Session

from core.config import get_settings
from core import app_settings, approvals
from core.contracts import display_status
from core.simcal import day_date, weekday

settings = get_settings()

HISTORY_DAYS = 120   # prediction history on the unit page
SENSOR_DAYS = 60     # sensor chart window
EVENT_TAIL = 300     # events returned when the client asks for "everything"
EVENT_PAGE = 500     # most events returned in one response

# Plain-English sensor names (techstack 5.2). The dashboard shows these, never the s-codes.
SENSOR_LABELS = {
    "s2": "Low-pressure compressor outlet temperature", "s3": "High-pressure compressor outlet temperature",
    "s4": "Low-pressure turbine outlet temperature", "s7": "High-pressure compressor outlet pressure",
    "s8": "Fan speed", "s9": "Core speed", "s11": "High-pressure compressor static pressure",
    "s12": "Fuel flow to pressure ratio", "s13": "Corrected fan speed", "s14": "Corrected core speed",
    "s15": "Bypass ratio", "s17": "Bleed enthalpy", "s20": "High-pressure turbine coolant bleed",
    "s21": "Low-pressure turbine coolant bleed",
}


def _rows(s: Session, sql: str, **p) -> list:
    return s.execute(text(sql), p).mappings().all()


# ---------------------------------------------------------------- clock
def sim_state(s: Session) -> dict:
    r = s.execute(text("SELECT sim_day, status, speed_seconds_per_day FROM sim_state WHERE id = 1")).mappings().first()
    return dict(r) if r else {"sim_day": 0, "status": "paused", "speed_seconds_per_day": 1.0}


def clock_view(s: Session) -> dict:
    c = sim_state(s)
    d = day_date(int(c["sim_day"]))
    return {"status": c["status"], "speed_seconds_per_day": float(c["speed_seconds_per_day"]),
            "sim_day": int(c["sim_day"]), "calendar_date": d.isoformat(), "weekday": weekday(int(c["sim_day"]))}


# ---------------------------------------------------------------- fleet
_FLEET_SQL = """
SELECT u.id AS unit_id, st.code AS station_code, st.name AS station, u.status AS unit_status,
       p.status AS p_status, p.rul_low, p.rul_likely, p.rul_high, p.p_fail_h, p.confidence, p.reason,
       p.top_sensors, p.data_source, p.model_version,
       EXISTS (SELECT 1 FROM quality_flags q WHERE q.unit_id = u.id AND q.resolved_day IS NULL) AS sensor_issue,
       (SELECT min(pi.planned_day) FROM plan_items pi WHERE pi.unit_id = u.id AND pi.state = 'planned') AS next_day,
       EXISTS (SELECT 1 FROM plan_items pi WHERE pi.unit_id = u.id AND pi.state = 'needs_manager_decision') AS flagged,
       EXISTS (SELECT 1 FROM plan_items pi WHERE pi.unit_id = u.id
               AND pi.state IN ('planned', 'needs_manager_decision')) AS has_plan
FROM units u JOIN stations st ON st.id = u.station_id
LEFT JOIN LATERAL (SELECT * FROM predictions WHERE unit_id = u.id AND sim_day <= :day
                   ORDER BY sim_day DESC LIMIT 1) p ON true
{where}
ORDER BY u.id
"""


def _fleet_unit(r, decision: dict | None = None, today: int = 0) -> dict:
    risk = r["p_status"] if r["p_status"] in ("healthy", "watch", "at_risk") else "healthy"
    failed = r["unit_status"] == "failed"
    sensor_issue = bool(r["sensor_issue"])
    has_prediction = r["p_status"] is not None
    # An at-risk unit that no crew slot could take never gets a plan row, so "no row" is the signal (item 2).
    no_slot = risk == "at_risk" and not failed and not r["has_plan"]
    next_day = r["next_day"]
    if decision:  # a manager already decided: no more warning, and overtime is a real service day
        no_slot, flagged = False, False
        if decision["choice"] == "overtime" and next_day is None and (decision["day"] or -1) >= today:
            next_day = decision["day"]
    else:
        flagged = bool(r["flagged"])
    return {
        "unit_id": r["unit_id"], "station_code": r["station_code"], "station": r["station"],
        "risk_status": risk, "sensor_issue": sensor_issue, "display_status": display_status(risk, sensor_issue),
        "rul": {"low": float(r["rul_low"] or 0), "likely": float(r["rul_likely"] or 0), "high": float(r["rul_high"] or 0)},
        "p_fail": float(r["p_fail_h"] or 0), "confidence": r["confidence"] or ("normal" if has_prediction else "low"),
        "reason": r["reason"] or ("" if has_prediction else "Waiting for the first prediction."),
        "top_sensors": list(r["top_sensors"] or []),
        "next_service_day": next_day, "needs_manager_decision": bool(flagged or no_slot),
        "failed": failed, "data_source": r["data_source"] or "live", "model_version": r["model_version"] or "v1",
    }


def fleet(s: Session) -> dict:
    clock = clock_view(s)
    rows = _rows(s, _FLEET_SQL.format(where=""), day=clock["sim_day"])
    dec = approvals.decisions(s)
    return {"sim_day": clock["sim_day"], "clock": clock,
            "units": [_fleet_unit(r, dec.get(r["unit_id"]), clock["sim_day"]) for r in rows]}


# ---------------------------------------------------------------- events
def _event(r) -> dict:
    return {"event_id": r["id"], "type": r["type"], "sim_day": r["sim_day"], "unit_id": r["unit_id"],
            "title": r["title"] or "", "detail": r["detail"] or "", "severity": r["severity"] or "info",
            "payload": r["payload"] if isinstance(r["payload"], dict) else {}}


_EVENT_COLS = "id, type, sim_day, unit_id, title, detail, severity, payload"


def events_after(s: Session, after_id: int = 0, limit: int = EVENT_PAGE) -> list[dict]:
    """Events with id > after_id, oldest first. after_id=0 means 'the recent log': the latest EVENT_TAIL."""
    if after_id <= 0:
        rows = _rows(s, f"SELECT {_EVENT_COLS} FROM events ORDER BY id DESC LIMIT :n", n=EVENT_TAIL)[::-1]
    else:
        rows = _rows(s, f"SELECT {_EVENT_COLS} FROM events WHERE id > :a ORDER BY id LIMIT :n", a=after_id, n=limit)
    return [_event(r) for r in rows]


def events_since(s: Session, cursor: int, limit: int = 200) -> list[dict]:
    """Strictly newer than cursor, oldest first. The SSE stream polls this."""
    return [_event(r) for r in _rows(s, f"SELECT {_EVENT_COLS} FROM events WHERE id > :c ORDER BY id LIMIT :n",
                                     c=cursor, n=limit)]


def unit_events(s: Session, unit_id: str, limit: int = 200) -> list[dict]:
    rows = _rows(s, f"SELECT {_EVENT_COLS} FROM events WHERE unit_id = :u ORDER BY id DESC LIMIT :n", u=unit_id, n=limit)
    return [_event(r) for r in rows[::-1]]


def max_event_id(s: Session) -> int:
    return int(s.execute(text("SELECT COALESCE(max(id), 0) FROM events")).scalar())


# ---------------------------------------------------------------- calls
_CALL_SQL = """
SELECT c.id, c.call_request_id, cr.unit_id, cr.technician_id, t.name AS technician_name, c.conversation_id,
       c.language, c.transcript, c.summary, c.data_collection, c.duration_secs, c.received_via, c.evaluation
FROM calls c JOIN call_requests cr ON cr.id = c.call_request_id JOIN technicians t ON t.id = cr.technician_id
WHERE (c.transcript IS NOT NULL OR c.summary IS NOT NULL) {where}
ORDER BY c.id
"""


def _call(r) -> dict:
    dc = r["data_collection"] if isinstance(r["data_collection"], dict) else {}
    summary = r["summary"] or ""
    out = {
        "id": r["id"], "call_request_id": r["call_request_id"], "unit_id": r["unit_id"],
        "technician_id": r["technician_id"], "technician_name": r["technician_name"],
        "conversation_id": r["conversation_id"] or "", "language": r["language"] or "en",
        "transcript": r["transcript"] if isinstance(r["transcript"], list) else [],  # exactly as ElevenLabs sent it
        "summary": summary, "summary_en": dc.get("english_summary") or summary,
        "duration_secs": r["duration_secs"] or 0, "received_via": r["received_via"] or "webhook",
        "data_collection": dc,
    }
    if r["evaluation"] is not None:
        out["evaluation"] = r["evaluation"]
    return out


def calls_for_unit(s: Session, unit_id: str) -> list[dict]:
    return [_call(r) for r in _rows(s, _CALL_SQL.format(where="AND cr.unit_id = :u"), u=unit_id)]


def call_record(s: Session, call_id: int) -> dict | None:
    rows = _rows(s, _CALL_SQL.format(where="AND c.id = :i"), i=call_id)
    return _call(rows[0]) if rows else None


# ---------------------------------------------------------------- unit detail
def unit_detail(s: Session, unit_id: str) -> dict | None:
    clock = sim_state(s)
    day = int(clock["sim_day"])
    rows = _rows(s, _FLEET_SQL.format(where="WHERE u.id = :uid"), day=day, uid=unit_id)
    if not rows:
        return None
    hist = _rows(s, "SELECT sim_day, rul_low, rul_likely, rul_high, p_fail_h FROM predictions WHERE unit_id = :u "
                    "ORDER BY sim_day DESC LIMIT :n", u=unit_id, n=HISTORY_DAYS)[::-1]
    cols = ", ".join(SENSOR_LABELS)
    readings = _rows(s, f"SELECT sim_day, {cols} FROM readings WHERE unit_id = :u AND sim_day > :d AND sim_day <= :t "
                        "ORDER BY sim_day", u=unit_id, d=day - SENSOR_DAYS, t=day)
    sensors = [{"sensor": code, "label": label,
                "points": [{"sim_day": r["sim_day"], "value": float(r[code])} for r in readings if r[code] is not None]}
               for code, label in SENSOR_LABELS.items()]
    flags = _rows(s, "SELECT id, unit_id, sim_day, sensor, flag_type, resolved_day FROM quality_flags "
                     "WHERE unit_id = :u ORDER BY id", u=unit_id)
    return {**_fleet_unit(rows[0], approvals.decisions(s).get(unit_id), day),
            "history": [{"sim_day": h["sim_day"], "rul_low": float(h["rul_low"]), "rul_likely": float(h["rul_likely"]),
                         "rul_high": float(h["rul_high"]), "p_fail": float(h["p_fail_h"])} for h in hist],
            "sensors": sensors, "events": unit_events(s, unit_id), "calls": calls_for_unit(s, unit_id),
            "quality_flags": [dict(f) for f in flags]}


# ---------------------------------------------------------------- plan
_PLAN_SQL = """
SELECT p.id, p.unit_id, st.code AS station_code, p.planned_day, p.technician_id, t.name AS technician_name,
       p.expected_saving, p.reason, p.state
FROM plan_items p JOIN units u ON u.id = p.unit_id JOIN stations st ON st.id = u.station_id
LEFT JOIN technicians t ON t.id = p.technician_id
WHERE (p.state <> 'done' OR p.planned_day >= :since)
ORDER BY p.planned_day, p.unit_id
"""

# At-risk units that no crew slot could take have no plan row, so the manager's card is built from this.
_NO_SLOT_SQL = """
SELECT u.id AS unit_id, st.code AS station_code, p.p_fail_h,
       (SELECT t.id FROM technicians t WHERE t.station_id = u.station_id ORDER BY t.is_backup, t.id LIMIT 1) AS tech_id,
       (SELECT t.name FROM technicians t WHERE t.station_id = u.station_id ORDER BY t.is_backup, t.id LIMIT 1) AS tech_name
FROM units u JOIN stations st ON st.id = u.station_id
JOIN LATERAL (SELECT status, p_fail_h FROM predictions WHERE unit_id = u.id AND sim_day <= :day
              ORDER BY sim_day DESC LIMIT 1) p ON true
WHERE u.status <> 'failed' AND p.status = 'at_risk'
  AND NOT EXISTS (SELECT 1 FROM plan_items pi WHERE pi.unit_id = u.id AND pi.state IN ('planned', 'needs_manager_decision'))
ORDER BY u.id
"""


def _item(row_id, unit_id, station, day, tech_id, tech_name, saving, reason, state, approval, decision=None) -> dict:
    out = {"id": row_id, "unit_id": unit_id, "station_code": station, "planned_day": day,
           "planned_date": day_date(day).isoformat(), "technician_id": tech_id if tech_id is not None else 0,
           "technician_name": tech_name or "Unassigned", "expected_saving": float(saving or 0),
           "reason": reason or "", "state": state, "approval": approval}
    if decision:
        out["decision"] = decision
    return out


def plan_items(s: Session) -> list[dict]:
    """Plan rows plus what the manager screens need: approval on every item, a card for each unit no crew
    could take, and overtime items. Items are sorted by day."""
    day = int(sim_state(s)["sim_day"])
    props, dec = approvals.proposed(s), approvals.decisions(s)
    app = app_settings.read(s)  # the manager's cost settings
    items = []
    for r in _rows(s, _PLAN_SQL, since=day - 7):
        d = dec.get(r["unit_id"])
        if r["state"] == "needs_manager_decision":
            if d and d["choice"] == "overtime" and (d["day"] or -1) >= day:   # resolved: an extra crew tomorrow
                items.append(_item(r["id"], r["unit_id"], r["station_code"], d["day"], r["technician_id"], r["technician_name"],
                                   r["expected_saving"], r["reason"], "planned", "approved", "overtime"))
            else:
                items.append(_item(r["id"], r["unit_id"], r["station_code"], r["planned_day"], r["technician_id"],
                                   r["technician_name"], r["expected_saving"], r["reason"], r["state"], "proposed",
                                   "deferred" if d and d["choice"] == "deferred" else None))
            continue
        proposal = r["state"] == "planned" and (r["unit_id"], r["planned_day"]) in props
        items.append(_item(r["id"], r["unit_id"], r["station_code"], r["planned_day"], r["technician_id"],
                           r["technician_name"], r["expected_saving"], r["reason"], r["state"],
                           "proposed" if proposal else "approved"))
    for r in _rows(s, _NO_SLOT_SQL, day=day):
        d = dec.get(r["unit_id"])
        saving = float(r["p_fail_h"]) * app["cost_breakdown"] - app["cost_service"]
        why = "No crew slot is free this week."
        if d and d["choice"] == "overtime":
            if (d["day"] or -1) >= day:
                items.append(_item(approvals.synth_id(r["unit_id"]), r["unit_id"], r["station_code"], d["day"], r["tech_id"],
                                   r["tech_name"], saving, "Overtime crew approved by a manager.", "planned", "approved", "overtime"))
        else:
            items.append(_item(approvals.synth_id(r["unit_id"]), r["unit_id"], r["station_code"], day, None, None, saving,
                               why + " A manager needs to decide.", "needs_manager_decision", "proposed",
                               "deferred" if d else None))
    return sorted(items, key=lambda i: (i["planned_day"], i["unit_id"]))


def work_orders_csv(s: Session) -> tuple[str, str]:
    """(filename, csv text with a BOM so Excel opens the UTF-8 cleanly). Approved planned work only."""
    day = int(sim_state(s)["sim_day"])
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["date", "station", "unit", "technician", "expected_saving", "reason"])
    for p in plan_items(s):
        if p["state"] == "planned" and p["approval"] == "approved":
            w.writerow([p["planned_date"], p["station_code"], p["unit_id"], p["technician_name"],
                        p["expected_saving"], p["reason"]])
    return f"work_orders_day_{day}.csv", "\ufeff" + buf.getvalue()


# ---------------------------------------------------------------- technicians
def technicians(s: Session, online: dict[int, int]) -> list[dict]:
    rows = _rows(s, "SELECT t.id, t.name, st.code AS station_code, t.shift, t.language, t.is_backup, t.field_page_id "
                    "FROM technicians t JOIN stations st ON st.id = t.station_id ORDER BY t.id")
    return [{"id": r["id"], "name": r["name"], "station_code": r["station_code"], "shift": r["shift"],
             "language": r["language"], "is_backup": bool(r["is_backup"]), "online": online.get(r["id"], 0) > 0,
             "field_page_id": r["field_page_id"]} for r in rows]


# ---------------------------------------------------------------- small extras
def trend(s: Session, days: int = 30) -> list[dict]:
    day = int(sim_state(s)["sim_day"])
    rows = _rows(s, "SELECT sim_day, count(*) FILTER (WHERE status = 'at_risk') AS n FROM predictions "
                    "WHERE sim_day > :d AND sim_day <= :t GROUP BY sim_day ORDER BY sim_day", d=day - days, t=day)
    return [{"sim_day": r["sim_day"], "needing_attention": int(r["n"])} for r in rows]


def feedback_stats(s: Session) -> dict:
    r = s.execute(text("SELECT count(*), count(*) FILTER (WHERE verdict IN ('confirmed_wear', 'part_replaced')) "
                       "FROM feedback")).one()
    return {"total": int(r[0]), "confirmed": int(r[1])}


def _metadata() -> dict:
    for base in (Path(settings.model_dir), Path(__file__).resolve().parents[1] / "ml" / "artifacts"):
        try:
            return json.loads((base / "metadata.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return {}


def model_metrics() -> dict | None:
    m = _metadata()
    try:
        return {"rmse": round(float(m["test"]["rmse"]), 1), "baseline_rmse": round(float(m["baseline_linear_test"]["rmse"]), 1),
                "model_version": str(m.get("model_version", "v1"))}
    except (KeyError, TypeError, ValueError):
        return None


# ---------------------------------------------------------------- health
def health(s: Session) -> dict:
    clock = sim_state(s)
    day = int(clock["sim_day"])
    mix = {r["data_source"]: int(r["n"]) for r in _rows(
        s, "SELECT data_source, count(*) AS n FROM (SELECT DISTINCT ON (unit_id) data_source FROM predictions "
           "ORDER BY unit_id, sim_day DESC) x GROUP BY data_source")}
    last_pred = s.execute(text("SELECT max(sim_day) FROM predictions")).scalar()
    tick_age = s.execute(text("SELECT EXTRACT(EPOCH FROM now() - updated_at) FROM sim_state WHERE id = 1")).scalar()
    return {
        "status": "ok", "ok": True, "mock_api": False, "database": True, "sim_day": day,
        "clock_status": clock["status"],
        "simulator_tick_age_secs": round(float(tick_age), 1) if tick_age is not None else None,
        "engine_lag_days": (day - int(last_pred)) if last_pred is not None else None,
        "model_version": (model_metrics() or {}).get("model_version", "v1"),
        "data_source": {"live": mix.get("live", 0), "fallback": mix.get("fallback", 0)},
        "elevenlabs_configured": bool(settings.elevenlabs_api_key and settings.elevenlabs_agent_id),
        "webhook_secret_set": bool(settings.elevenlabs_webhook_secret),
        "voice_tool_secret_set": bool(settings.voice_tool_secret),
        "admin_token_set": bool(settings.admin_token),
    }
