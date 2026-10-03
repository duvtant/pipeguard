"""Builds the mock API fixtures (api/fixtures/*.json). Mock data only.

Shapes follow docs/delegation/00_TEAM_CONTRACT.md 4.3 and Olise's core/contracts.py.
Deterministic: run it twice, get identical files.
Run from the repo root:  python api/fixtures/generate.py
"""
import json
import random
from datetime import date, timedelta
from pathlib import Path

OUT = Path(__file__).parent
rng = random.Random(42)  # fixed seed so reruns don't change the files

CALENDAR_START = date(2026, 10, 5)  # sim_day 0 = a Monday (scenario.json calendar_start)
SIM_DAY = 31                        # "today" in the fixtures (a Thursday)

STATIONS = {"EDS": "Edson", "HIN": "Hinton", "WHT": "Whitecourt", "GPR": "Grande Prairie", "DRH": "Drumheller"}
ORDER = list(STATIONS)  # same order as the contract's STATION_ORDER

# Plain-English sensor labels (techstack 5.2). The UI shows these, never raw ids.
LABEL = {
    "s2": "Low-pressure compressor outlet temperature",
    "s3": "High-pressure compressor outlet temperature",
    "s4": "Low-pressure turbine outlet temperature",
    "s7": "High-pressure compressor outlet pressure",
    "s8": "Fan speed",
    "s9": "Core speed",
    "s11": "High-pressure compressor static pressure",
    "s12": "Fuel flow to pressure ratio",
    "s13": "Corrected fan speed",
    "s14": "Corrected core speed",
    "s15": "Bypass ratio",
    "s17": "Bleed enthalpy",
    "s20": "High-pressure turbine coolant bleed",
    "s21": "Low-pressure turbine coolant bleed",
}
# Typical values, only used to draw believable trend lines.
BASE = {"s2": 642.5, "s3": 1589, "s4": 1408, "s7": 553.4, "s8": 2388.1, "s9": 9046, "s11": 47.5,
        "s12": 521.4, "s13": 2388.1, "s14": 8138.6, "s15": 8.42, "s17": 392, "s20": 38.9, "s21": 23.3}

# Hand-picked units so the dashboard has every state to render.
# unit: (rul_low, rul_likely, rul_high, p_fail, drifting_sensor, days_rising, next_service_day)
AT_RISK = {
    "EDS-07": (14, 22, 35, 0.62, "s3", 6, 32),    # the demo unit (French call below)
    "HIN-04": (9, 15, 24, 0.78, "s11", 8, 33),
    "WHT-17": (11, 19, 30, 0.55, "s4", 5, 34),
    "GPR-02": (7, 12, 19, 0.86, "s7", 9, 32),
    "WHT-03": (10, 17, 27, 0.70, "s8", 7, 35),    # red AND sensor issue (contract D1)
    "EDS-14": (6, 10, 16, 0.91, "s15", 10, None), # no crew slot: needs manager decision
}
WATCH = {
    "EDS-12": (28, 41, 58, 0.22, "s2", 4),
    "HIN-18": (31, 44, 60, 0.18, "s9", 3),
    "WHT-09": (25, 38, 55, 0.27, "s14", 5),
    "DRH-09": (30, 46, 62, 0.15, "s21", 3),
    "DRH-15": (27, 40, 57, 0.24, "s12", 4),
}
SENSOR_ISSUE = {"HIN-12": "s8", "WHT-03": "s13"}  # unit -> offline sensor
ISSUE_DAY = {"HIN-12": 22, "WHT-03": 30}          # day the sensor went dead
NEEDS_DECISION = {"EDS-14"}
FAILED = "GPR-15"


def dump(name, obj):
    # ensure_ascii=False keeps the French accents readable in the file.
    (OUT / name).write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def display_status(risk, sensor_issue):
    # Contract D1: a real risk is never hidden behind a sensor fault.
    return "sensor_issue" if sensor_issue and risk != "at_risk" else risk


def make_unit(i):
    """One FleetUnit (contract 4.3). Engines 1-20 are EDS-01..20, 21-40 HIN-01..20, and so on."""
    code = ORDER[i // 20]
    uid = f"{code}-{i % 20 + 1:02d}"
    issue = SENSOR_ISSUE.get(uid)

    # Default: healthy unit with plenty of life left (RUL is capped at 125).
    likely = rng.randint(95, 115)
    risk, failed = "healthy", False
    rul = {"low": likely - 15, "likely": likely, "high": min(125, likely + 10)}
    p_fail = round(rng.uniform(0.0, 0.08), 2)  # healthy means p_fail < 0.10 (contract D2)
    reason, top, next_day = "No unusual sensor drift", [], None

    spec = AT_RISK.get(uid) or WATCH.get(uid)
    if spec:
        low, likely, high, p_fail, sensor, days = spec[:6]
        risk = "at_risk" if uid in AT_RISK else "watch"
        rul = {"low": low, "likely": likely, "high": high}
        reason = f"{LABEL[sensor]} has been rising for {days} days"
        top = [sensor] + rng.sample([s for s in LABEL if s != sensor], 2)
        next_day = spec[6] if uid in AT_RISK else None
    elif issue:
        reason = f"{LABEL[issue]} sensor is offline. Prediction continues on the other sensors."

    if uid == FAILED:
        risk, failed = "at_risk", True
        rul, p_fail, reason, top, next_day = {"low": 0, "likely": 0, "high": 0}, 1.0, "Unit failed in service", [], None

    return {
        "unit_id": uid, "station_code": code, "station": STATIONS[code],
        "risk_status": risk, "sensor_issue": bool(issue),
        "display_status": display_status(risk, bool(issue)),
        "rul": rul, "p_fail": p_fail,
        "confidence": "low" if issue else "normal",  # masked sensor means low confidence
        "reason": reason, "top_sensors": top, "next_service_day": next_day,
        "needs_manager_decision": uid in NEEDS_DECISION, "failed": failed,
        "data_source": "live", "model_version": "v1",
    }


units = [make_unit(i) for i in range(100)]
by_id = {u["unit_id"]: u for u in units}
today = CALENDAR_START + timedelta(days=SIM_DAY)
dump("fleet.json", {
    "sim_day": SIM_DAY,
    "clock": {"sim_day": SIM_DAY, "calendar_date": today.isoformat(), "weekday": today.strftime("%A"),
              "status": "paused", "speed_seconds_per_day": 1.0},
    "units": units,
})

# --- Roster. field_page_id is NOT exposed: the slug in the /field URL is its only protection. ---
ROSTER = [  # id, name, station, shift, language, is_backup
    (1, "Sam Whitford", "EDS", "day", "en", False), (2, "Priya Nair", "EDS", "night", "en", True),
    (3, "Marc Tremblay", "EDS", "day", "fr", False), (4, "Jordan Cardinal", "HIN", "day", "en", False),
    (5, "Aisha Bello", "HIN", "night", "en", True), (6, "Luc Gagnon", "WHT", "day", "fr", False),
    (7, "Dana Kowalski", "WHT", "night", "en", True), (8, "Chris Lavoie", "GPR", "day", "en", False),
    (9, "Mei Lin Zhao", "GPR", "night", "en", True), (10, "Tom Redcrow", "GPR", "day", "en", False),
    (11, "Elena Petrova", "DRH", "day", "en", False), (12, "Omar Haddad", "DRH", "night", "en", True),
]
techs = [{"id": t[0], "name": t[1], "station_code": t[2], "station": STATIONS[t[2]], "shift": t[3],
          "language": t[4], "is_backup": t[5], "online": t[0] in (1, 3)} for t in ROSTER]
tech_by_id = {t["id"]: t for t in techs}
dump("technicians.json", {"technicians": techs})

# --- Plan: every at-risk unit that has a service day. Primary day-shift tech per station. ---
PRIMARY = {"EDS": 3, "HIN": 4, "WHT": 6, "GPR": 8, "DRH": 11}
items = []
for u in sorted(units, key=lambda x: (x["next_service_day"] or 999, x["unit_id"])):
    if u["risk_status"] == "at_risk" and u["next_service_day"] is not None and not u["failed"]:
        tid = PRIMARY[u["station_code"]]
        items.append({
            "id": len(items) + 1, "unit_id": u["unit_id"], "station_code": u["station_code"],
            "planned_day": u["next_service_day"],
            "planned_date": (CALENDAR_START + timedelta(days=u["next_service_day"])).isoformat(),
            "technician_id": tid, "technician_name": tech_by_id[tid]["name"],
            "expected_saving": round(u["p_fail"] * 200_000 - 20_000),  # p_fail * breakdown cost - service cost
            "reason": u["reason"], "state": "planned",
        })
dump("plan.json", {
    "sim_day": SIM_DAY, "items": items,
    "needs_manager_decision": [{"unit_id": "EDS-14", "station_code": "EDS",
                                "reason": "No crew slot opens before this unit may fail (6 to 16 days left)."}],
})

# --- One French call, used in the event log and EDS-07's detail. ---
CALL = {
    "call_id": 1, "call_request_id": 41, "conversation_id": "conv_mock_0001",
    "technician_id": 3, "technician_name": "Marc Tremblay", "language": "fr",
    "sim_day": 31, "duration_secs": 38, "received_via": "webhook",
    "summary_en": "Marc cannot service EDS-07 before Friday. The plan moved EDS-07 to day 32.",
    "data_collection": {"available_day": "vendredi", "verdict": "", "unit_mentioned": "EDS-07",
                        "english_summary": "Marc cannot service EDS-07 before Friday. The plan moved EDS-07 to day 32."},
    "transcript": [
        {"role": "agent", "message": "Bonjour Marc, ici PipeGuard pour Prairie Gas. L'unité EDS-07 à Edson a entre 14 et 35 jours de vie utile. Pouvez-vous l'entretenir d'ici jeudi?", "time_in_call_secs": 0},
        {"role": "user", "message": "Pas avant vendredi.", "time_in_call_secs": 12},
        {"role": "agent", "message": "Donc vendredi, c'est bien ça?", "time_in_call_secs": 15},
        {"role": "user", "message": "Oui, vendredi.", "time_in_call_secs": 18},
        {"role": "agent", "message": "C'est noté. EDS-07 passe à vendredi. Merci Marc.", "time_in_call_secs": 21},
    ],
}


def ev(eid, day, typ, unit, title, detail, severity="info", payload=None):
    return {"event_id": eid, "type": typ, "sim_day": day, "unit_id": unit, "title": title,
            "detail": detail, "severity": severity, "payload": payload or {}}


events = [
    ev(801, 22, "sensor_issue", "HIN-12", "Sensor offline", "Fan speed sensor on HIN-12 stopped reporting. Instrument check requested, no crew call.", "warning", {"sensor": "s8", "flag_type": "sensor_offline"}),
    ev(802, 24, "failure", "GPR-15", "Unit failed", "GPR-15 failed in service before a crew could reach it.", "critical"),
    ev(803, 26, "feedback_received", "WHT-09", "Feedback received", "Technician verdict: looks fine. Counted as a false alarm.", "info", {"verdict": "looks_fine"}),
    ev(804, 26, "threshold_adjusted", None, "Threshold adjusted", "Hit rate over the last 10 verdicts fell to 50%. Alert threshold raised from 0.50 to 0.55.", "info", {"old": 0.5, "new": 0.55}),
    ev(805, 27, "status_change", "HIN-04", "Status changed", "HIN-04 moved from watch to at risk.", "warning"),
    ev(806, 28, "status_change", "EDS-07", "Status changed", "EDS-07 moved from watch to at risk.", "warning"),
    ev(807, 29, "manager_alert", "EDS-14", "Needs manager decision", "EDS-14 may fail before any crew slot opens (6 to 16 days left). A manager needs to decide.", "critical"),
    ev(808, 30, "sensor_issue", "WHT-03", "Sensor offline", "Corrected fan speed sensor on WHT-03 stopped reporting. The unit stays at risk; instrument check requested.", "warning", {"sensor": "s13", "flag_type": "sensor_offline"}),
    ev(809, 30, "call_requested", "EDS-07", "Call requested", "Calling Marc Tremblay about EDS-07.", "info", {"technician_id": 3, "call_request_id": 41}),
    ev(810, 31, "call_answered", "EDS-07", "Call answered", "Marc Tremblay answered. The call is in French.", "info", {"call_request_id": 41}),
    ev(811, 31, "constraint_added", "EDS-07", "Constraint added", "Marc Tremblay cannot service EDS-07 before day 32 (Friday).", "info", {"earliest_day": 32}),
    ev(812, 31, "plan_changed", "EDS-07", "Plan changed", "EDS-07 moved to day 32 (technician unavailable before Friday).", "info",
       {"changes": [{"kind": "moved", "unit_id": "EDS-07", "old_day": 31, "new_day": 32}]}),
    ev(813, 31, "call_summary", "EDS-07", "Call summary", CALL["summary_en"], "info", CALL),
]
dump("events.json", {"events": events})


# --- Unit detail for the interesting units (the API fills in the rest with empty lists). ---
def series(sensor, rising_days, dead_from=None):
    """60 days of one sensor. A rising sensor drifts up; a dead one goes null."""
    pts = []
    for k in range(60):
        d = SIM_DAY - 59 + k
        noise = rng.uniform(-1, 1) * BASE[sensor] * 0.0003
        drift = BASE[sensor] * 0.0006 * max(0, d - (SIM_DAY - rising_days))
        dead = dead_from is not None and d >= dead_from
        pts.append({"sim_day": d, "value": None if dead else round(BASE[sensor] + noise + drift, 3)})
    return {"sensor": sensor, "label": LABEL[sensor], "points": pts}


def history(u):
    """30 days of predictions. Flagged units lose one day of life per day."""
    flagged = u["risk_status"] != "healthy" or u["failed"]
    pts = []
    for k in range(30):
        back = 29 - k
        lag = back if flagged else 0
        pts.append({
            "sim_day": SIM_DAY - back,
            "rul_low": min(125, u["rul"]["low"] + lag),
            "rul_likely": min(125, u["rul"]["likely"] + lag),
            "rul_high": min(125, u["rul"]["high"] + lag),
            "p_fail": round(max(0.0, u["p_fail"] - back * 0.02), 2) if flagged else u["p_fail"],
        })
    return pts


def plots(uid, u):
    if uid in SENSOR_ISSUE and not u["top_sensors"]:  # HIN-12: show the dead sensor
        return [series(SENSOR_ISSUE[uid], 0, dead_from=ISSUE_DAY[uid])]
    spec = AT_RISK.get(uid) or WATCH.get(uid)
    return [series(s, spec[5] if n == 0 else 0) for n, s in enumerate(u["top_sensors"])]


details = {}
for uid in dict.fromkeys([*AT_RISK, *WATCH, *SENSOR_ISSUE, FAILED, "EDS-01"]):  # dedupe, keep order
    u = by_id[uid]
    flags = []
    if uid in SENSOR_ISSUE:
        s = SENSOR_ISSUE[uid]
        flags = [{"unit_id": uid, "sensor": s, "flag_type": "sensor_offline", "sim_day": ISSUE_DAY[uid],
                  "resolved_day": None, "detail": f"{LABEL[s]} stopped reporting"}]
    details[uid] = {**u, "history": history(u), "sensors": plots(uid, u),
                    "events": [e for e in events if e["unit_id"] == uid],
                    "calls": [CALL] if uid == "EDS-07" else [], "quality_flags": flags}
dump("unit_details.json", details)

# --- Simulate / impact. PLACEHOLDER numbers that show the shape. They are not results. ---
dump("simulate.json", {
    "policies": [
        {"policy": "run_to_failure", "breakdowns": 100, "planned_services": 0, "wasted_services": 0, "crew_days": 0, "total_cost": 20_000_000, "operating_days": 0, "cost_per_operating_day": 0.0},
        {"policy": "fixed_schedule", "breakdowns": 31, "planned_services": 160, "wasted_services": 84, "crew_days": 160, "total_cost": 9_400_000, "operating_days": 0, "cost_per_operating_day": 0.0},
        {"policy": "pipeguard", "breakdowns": 6, "planned_services": 109, "wasted_services": 9, "crew_days": 109, "total_cost": 3_380_000, "operating_days": 0, "cost_per_operating_day": 0.0},
    ],
    "default": {"threshold": 0.5, "horizon_days": 14, "total_cost": 4_100_000, "detected": 84, "actioned": 79, "total": 100, "meets_service_level": False},
    "tuned": {"threshold": 0.4, "horizon_days": 14, "total_cost": 3_380_000, "detected": 91, "actioned": 88, "total": 100, "meets_service_level": True},
    "headline": {"detected": 91, "actioned": 88, "total": 100, "lead_days": 14,
                 "text": "MOCK: PipeGuard would have caught 88 of 100 failures at least 14 days early.",
                 "false_alarms": 7, "false_alarm_days": 60, "lead_time_p10": 16.0, "lead_time_median": 31.0, "lead_time_p90": 52.0,
                 "definition": "Detected = at risk at least 14 days before failure. Actioned = also serviced in time."},
    "computed_ms": 240,
    "assumptions": ["MOCK DATA: placeholder numbers, not results. Only the cost sliders change them."],
})
print("fixtures written to", OUT)