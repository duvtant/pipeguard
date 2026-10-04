"""FastAPI app. With MOCK_API=1 it serves api/fixtures/*.json from memory and needs no database,
so David can build the dashboard and the phone page before the real engine exists.
Response shapes follow web/src/lib/types.ts. Real routers (api/routers/*) get included in the
non-mock branch as they're built.
"""
import asyncio
import csv
import hmac
import io
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from core.config import get_settings

settings = get_settings()
from contextlib import asynccontextmanager, suppress


@asynccontextmanager
async def lifespan(_app):
    # Real mode only: the one-second sweeper expires unanswered rings (core/alerts.py).
    task = None
    if not settings.mock_api:
        from core.alerts import sweeper_loop
        task = asyncio.create_task(sweeper_loop())
    yield
    if task:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="PipeGuard API", lifespan=lifespan)
FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@app.get("/api/health")
def health():
    # Real checks (DB, simulator and engine tick age) come with the real API.
    return {"status": "ok", "ok": True, "mock_api": settings.mock_api, "model_version": "v1",
            "data_source": {"live": 100, "fallback": 0}}


if settings.mock_api:
    # Browser on another origin (Vite dev server, Codespaces URL) needs CORS. Mock mode only.
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    CALENDAR_START = date(2026, 10, 5)  # sim_day 0 = Monday, same as scenario.json
    RING_SECONDS = 30                   # real seconds before an unanswered ring counts as missed

    # Plain-English sensor labels (techstack 5.2).
    LABEL = {
        "s2": "Low-pressure compressor outlet temperature", "s3": "High-pressure compressor outlet temperature",
        "s4": "Low-pressure turbine outlet temperature", "s7": "High-pressure compressor outlet pressure",
        "s8": "Fan speed", "s9": "Core speed", "s11": "High-pressure compressor static pressure",
        "s12": "Fuel flow to pressure ratio", "s13": "Corrected fan speed", "s14": "Corrected core speed",
        "s15": "Bypass ratio", "s17": "Bleed enthalpy", "s20": "High-pressure turbine coolant bleed",
        "s21": "Low-pressure turbine coolant bleed",
    }
    FAULT_FLAG = {"dead": "sensor_offline", "stuck": "sensor_stuck",
                  "spike": "sensor_spike", "out_of_range": "sensor_out_of_range"}
    FAULT_WORDS = {"dead": "is offline", "stuck": "is stuck on one value",
                   "spike": "is giving spiking values", "out_of_range": "is reading an impossible value"}
    VERDICTS = {"confirmed_wear", "looks_fine", "part_replaced"}

    TECHS = {t["id"]: t for t in load("technicians.json")}  # plain array on disk
    DETAILS = load("unit_details.json")

    ids = {"event": 814, "call": 42, "fault": 3, "call_record": 2}  # never reset, so ids only go up
    connected: dict[int, int] = {}                                    # technician id -> open /field streams
    S: dict = {}                                                      # all mutable mock state, rebuilt by init_state()

    def day_date(day: int) -> date:
        return CALENDAR_START + timedelta(days=day)

    def weekday(day: int) -> str:
        return day_date(day).strftime("%A")

    def add_event(typ, unit_id, title, detail, severity="info", payload=None):
        e = {"event_id": ids["event"], "type": typ, "sim_day": S["clock"]["sim_day"], "unit_id": unit_id,
             "title": title, "detail": detail, "severity": severity, "payload": payload or {}}
        ids["event"] += 1
        S["events"].append(e)
        return e

    def refresh(uid: str):
        """Rebuild one fleet unit from its base record plus open faults (contract D1)."""
        u = dict(S["base"][uid])
        open_f = [f for f in S["faults"] if f["unit_id"] == uid and f["end_day"] is None]
        if open_f:
            f = open_f[0]
            u["sensor_issue"] = True
            u["confidence"] = "low"  # a masked sensor widens the range
            # D1: a real risk stays red with a wrench badge. Everything else turns grey.
            if u["risk_status"] != "at_risk":
                u["display_status"] = "sensor_issue"
            if u["risk_status"] == "healthy":
                u["reason"] = f"{LABEL[f['sensor']]} sensor {FAULT_WORDS[f['type']]}. Prediction continues on the other sensors."
        S["units"][uid] = u

    def flags_for(uid: str):
        # QualityFlag per types.ts: the id is the fault id.
        return [{"id": f["id"], "unit_id": uid, "sensor": f["sensor"], "flag_type": FAULT_FLAG[f["type"]],
                 "sim_day": f["start_day"], "resolved_day": f["end_day"]}
                for f in S["faults"] if f["unit_id"] == uid]

    def init_state():
        """Fresh demo state. Also what 'reset' does."""
        base = load("fleet.json")["units"]
        for u in base:  # strip fault effects from the fixture, refresh() re-applies them from the fault list
            u["sensor_issue"] = False
            u["confidence"] = "normal"
            u["display_status"] = u["risk_status"]
            if u["risk_status"] == "healthy":
                u["reason"] = "No unusual sensor drift"
        S.clear()
        S.update(
            clock={"sim_day": 31, "status": "paused", "speed_seconds_per_day": 1.0},
            base={u["unit_id"]: u for u in base},
            units={},
            plan=load("plan.json"),                                     # plain array of plan items
            events=load("events.json"),                                 # plain array of events
            calls={},                                                   # call REQUESTS (ringing, answered...)
            call_records={c["id"]: c for c in load("calls.json")},      # finished calls (CallRecord)
            faults=[  # planted faults, same as the fixtures
                {"id": 1, "unit_id": "HIN-12", "sensor": "s8", "type": "dead", "start_day": 22, "end_day": None, "source": "planted"},
                {"id": 2, "unit_id": "WHT-03", "sensor": "s13", "type": "dead", "start_day": 30, "end_day": None, "source": "planted"},
            ],
        )
        for uid in S["base"]:
            refresh(uid)

    init_state()

    def clock_view():
        c = S["clock"]
        d = day_date(c["sim_day"])
        return {**c, "calendar_date": d.isoformat(), "weekday": d.strftime("%A")}

    def require_admin(x_admin_token: str | None = Header(default=None)):
        # Open when ADMIN_TOKEN is empty (mock convenience). Set it in .env to lock admin and test mode.
        if settings.admin_token and not hmac.compare_digest(x_admin_token or "", settings.admin_token):
            raise HTTPException(401, "bad admin token")

    # ---------------------------------------------------------------- dashboard reads
    @app.get("/api/fleet")
    def fleet():
        return {"sim_day": S["clock"]["sim_day"], "clock": clock_view(),
                "units": [S["units"][uid] for uid in S["base"]]}

    @app.get("/api/units/{unit_id}")
    def unit_detail(unit_id: str):
        if unit_id not in S["units"]:
            raise HTTPException(404, "unknown unit")
        detail = DETAILS.get(unit_id, {"history": [], "sensors": []})
        # Live fleet fields, events, calls and flags override the static fixture.
        return {**detail, **S["units"][unit_id],
                "events": [e for e in S["events"] if e["unit_id"] == unit_id],
                "calls": [c for c in S["call_records"].values() if c["unit_id"] == unit_id],
                "quality_flags": flags_for(unit_id)}

    @app.get("/api/calls/{call_id}")
    def get_call(call_id: int):
        c = S["call_records"].get(call_id)
        if not c:
            raise HTTPException(404, "unknown call")
        return c

    @app.get("/api/plan")
    def plan():
        return S["plan"]  # plain array

    @app.get("/api/events")
    def events(after_id: int = 0):
        # Polling fallback for the SSE stream: same data, filtered by id. Plain array.
        return [e for e in S["events"] if e["event_id"] > after_id]

    @app.get("/api/technicians")
    def technicians():
        return [{**t, "online": connected.get(t["id"], 0) > 0} for t in TECHS.values()]  # plain array

    @app.get("/api/work-orders.csv")
    def work_orders():
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["date", "station", "unit", "technician", "expected_saving", "reason"])
        for p in S["plan"]:
            w.writerow([p["planned_date"], p["station_code"], p["unit_id"], p["technician_name"],
                        p["expected_saving"], p["reason"]])
        # BOM so Excel opens the UTF-8 file cleanly.
        return Response("\ufeff" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="work_orders_day_{S["clock"]["sim_day"]}.csv"'})

    # Local request models. Switch to core.contracts once Olise's file is merged to main.
    class SimBody(BaseModel):
        crews_per_station: int = 2
        cost_breakdown: float = 200_000
        cost_service: float = 20_000
        threshold: float | None = None
        horizon_days: int | None = None

    @app.post("/api/simulate")
    def simulate(body: SimBody):
        data = load("simulate.json")
        # Recompute costs from the sliders so the Impact tab visibly reacts. Crews have no effect in mock mode.
        for p in data["policies"]:
            p["total_cost"] = p["breakdowns"] * body.cost_breakdown + p["planned_services"] * body.cost_service
        # Keep tuned and default consistent with the recomputed pipeguard row.
        ratio = data["default"]["total_cost"] / data["tuned"]["total_cost"]
        pg = next(p for p in data["policies"] if p["policy"] == "pipeguard")["total_cost"]
        data["tuned"]["total_cost"] = pg
        data["default"]["total_cost"] = round(pg * ratio)
        return data

    @app.get("/api/impact")
    def impact():
        # David's handlers.ts still defines it, so keep it. Dashboard should use POST /api/simulate.
        return load("simulate.json")

    class ClockBody(BaseModel):
        action: str  # play | pause | speed | reset | advance
        speed_seconds_per_day: float | None = None
        days: int | None = None

    @app.post("/api/clock")
    def set_clock(body: ClockBody):
        c = S["clock"]
        if body.action == "play":
            c["status"] = "running"
        elif body.action == "pause":
            c["status"] = "paused"
        elif body.action == "speed" and body.speed_seconds_per_day is not None:
            c["speed_seconds_per_day"] = max(0.25, min(5.0, body.speed_seconds_per_day))  # allowed range 0.25-5
        elif body.action == "advance":
            c["sim_day"] += body.days or 1
        elif body.action == "reset":
            init_state()
        else:
            raise HTTPException(422, "bad clock action")
        return clock_view()

    def sse(e: dict) -> str:
        # One SSE frame. The id lets the browser resume with Last-Event-ID.
        # No "event:" name, so one onmessage handler receives every event. The type is inside the JSON.
        return f"id: {e['event_id']}\ndata: {json.dumps(e)}\n\n"

    @app.get("/api/stream")
    async def stream(request: Request):
        last = int(request.headers.get("last-event-id", 0))

        async def gen():
            high = 0
            for e in list(S["events"]):  # replay from last_id - 20 like the real API; clients de-duplicate
                high = max(high, e["event_id"])
                if e["event_id"] > last - 20:
                    yield sse(e)
            ticks = 0
            while not await request.is_disconnected():
                for e in [e for e in list(S["events"]) if e["event_id"] > high]:  # events added since
                    high = e["event_id"]
                    yield sse(e)
                ticks += 1
                if ticks % 15 == 0:
                    yield ": keep-alive\n\n"  # comment frame keeps proxies from closing the stream
                await asyncio.sleep(1)

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    # ---------------------------------------------------------------- calls (mock state machine)
    def start_call(unit_id: str, tech: dict, attempt: int = 1) -> dict:
        cr = {"call_request_id": ids["call"], "unit_id": unit_id, "technician_id": tech["id"],
              "state": "ringing", "attempt": attempt,
              "expires_at": datetime.now(timezone.utc) + timedelta(seconds=RING_SECONDS)}
        ids["call"] += 1
        S["calls"][cr["call_request_id"]] = cr
        add_event("call_requested", unit_id, "Call requested",
                  f"Calling {tech['name']} about {unit_id}." + (" (backup technician)" if attempt == 2 else ""),
                  payload={"technician_id": tech["id"], "call_request_id": cr["call_request_id"]})
        return cr

    def ring_event(cr: dict) -> dict:
        u, t = S["units"][cr["unit_id"]], TECHS[cr["technician_id"]]
        return {"type": "ring", "call_request_id": cr["call_request_id"], "unit_id": cr["unit_id"],
                "station_name": u["station"], "technician_id": t["id"], "technician_name": t["name"],
                "language": t["language"], "rul_low": u["rul"]["low"], "rul_high": u["rul"]["high"],
                "reason": u["reason"], "expires_at": cr["expires_at"].strftime("%Y-%m-%dT%H:%M:%SZ")}

    def miss(cr: dict):
        """Declined or unanswered: backup rings, then a manager alert (same as the real state machine)."""
        t = TECHS[cr["technician_id"]]
        if cr["attempt"] == 1:
            cr["state"] = "missed"
            backup = next((b for b in TECHS.values()
                           if b["is_backup"] and b["station_code"] == t["station_code"] and b["id"] != t["id"]), None)
            if backup:
                start_call(cr["unit_id"], backup, attempt=2)
                return
        cr["state"] = "escalated"
        add_event("manager_alert", cr["unit_id"], "Call not answered",
                  f"No technician answered for {cr['unit_id']}. A manager needs to follow up.", "critical")

    def sweep():
        # Real API runs this as a background sweeper. The mock runs it whenever a phone asks.
        now = datetime.now(timezone.utc)
        for cr in list(S["calls"].values()):
            if cr["state"] == "ringing" and cr["expires_at"] < now:
                miss(cr)

    # ---------------------------------------------------------------- technician (/field) page
    def tech_for_slug(slug: str) -> dict:
        for t in TECHS.values():
            if slug == t["field_page_id"]:
                return t
        raise HTTPException(404, "unknown technician page")

    def ringing_for(tech: dict):
        return next((c for c in S["calls"].values()
                     if c["technician_id"] == tech["id"] and c["state"] == "ringing"), None)

    @app.get("/api/field/{slug}/stream")
    async def field_stream(slug: str, request: Request):
        tech = tech_for_slug(slug)

        async def gen():
            connected[tech["id"]] = connected.get(tech["id"], 0) + 1
            sent: set[int] = set()  # a ring already ringing when the phone connects is still sent
            ticks = 0
            try:
                while not await request.is_disconnected():
                    sweep()
                    for cr in list(S["calls"].values()):
                        if (cr["technician_id"] == tech["id"] and cr["state"] == "ringing"
                                and cr["call_request_id"] not in sent):
                            sent.add(cr["call_request_id"])
                            # Named "ring" event on purpose: the phone page uses addEventListener('ring', ...).
                            yield f"event: ring\ndata: {json.dumps(ring_event(cr))}\n\n"
                    ticks += 1
                    if ticks % 15 == 0:
                        yield ": keep-alive\n\n"
                    await asyncio.sleep(1)
            finally:
                connected[tech["id"]] -= 1  # runs when the phone disconnects

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.post("/api/field/{slug}/answer")
    def field_answer(slug: str):
        tech = tech_for_slug(slug)
        sweep()
        cr = ringing_for(tech)
        if not cr:
            raise HTTPException(410, "call expired")  # late answer fails cleanly
        cr["state"] = "answered"
        u = S["units"][cr["unit_id"]]
        add_event("call_answered", cr["unit_id"], "Call answered",
                  f"{tech['name']} answered. The call is in {'French' if tech['language'] == 'fr' else 'English'}.",
                  payload={"call_request_id": cr["call_request_id"]})
        today = day_date(S["clock"]["sim_day"])
        nxt = u["next_service_day"]
        return {
            # Fake URL: the ElevenLabs SDK cannot connect to it. Real signed URL comes with the real API.
            "signed_url": "wss://mock.invalid/v1/convai/conversation?agent_id=mock",
            "language": tech["language"],
            "dynamic_variables": {  # all strings (contract 4.3)
                "technician_id": str(tech["id"]), "technician_name": tech["name"], "unit_id": u["unit_id"],
                "station_name": u["station"], "rul_low": str(round(u["rul"]["low"])),
                "rul_high": str(round(u["rul"]["high"])), "reason": u["reason"],
                "proposed_day": weekday(nxt) if nxt is not None else "this week",
                "call_request_id": str(cr["call_request_id"]),
                "sim_today": f"{today.strftime('%A, %B')} {today.day}",
            },
        }

    @app.post("/api/field/{slug}/decline")
    def field_decline(slug: str):
        tech = tech_for_slug(slug)
        cr = ringing_for(tech)
        if not cr:
            raise HTTPException(410, "no call ringing")
        miss(cr)  # backup rings immediately
        return {"ok": True}

    class FeedbackBody(BaseModel):
        unit_id: str
        verdict: str
        note: str | None = None

    @app.post("/api/field/{slug}/feedback")
    def field_feedback(slug: str, body: FeedbackBody):
        tech_for_slug(slug)
        if body.verdict not in VERDICTS or body.unit_id not in S["base"]:
            raise HTTPException(422, "bad verdict or unit")
        add_event("feedback_received", body.unit_id, "Feedback received",
                  f"Technician verdict: {body.verdict.replace('_', ' ')}.", payload={"verdict": body.verdict})
        return {"ok": True, "threshold": 0.5}  # mock never moves the threshold

    class ConversationBody(BaseModel):
        conversation_id: str

    @app.post("/api/field/{slug}/conversation")
    def field_conversation(slug: str, body: ConversationBody):
        tech_for_slug(slug)  # real API stores the id to link the webhook. Idempotent.
        return {"ok": True}

    # ---------------------------------------------------------------- test mode and admin
    class FaultBody(BaseModel):
        unit_id: str
        sensor: str
        type: str

    @app.get("/api/testmode/faults", dependencies=[Depends(require_admin)])
    def list_faults():
        return [f for f in S["faults"] if f["end_day"] is None]  # plain array, open faults only

    @app.post("/api/testmode/faults", dependencies=[Depends(require_admin)])
    def add_fault(body: FaultBody):
        if body.unit_id not in S["base"] or body.sensor not in LABEL or body.type not in FAULT_FLAG:
            raise HTTPException(422, "unknown unit, sensor or fault type")
        if S["base"][body.unit_id]["failed"]:
            return {"ok": True, "ignored": "unit already failed"}  # faults on failed units are ignored
        same = next((f for f in S["faults"] if f["unit_id"] == body.unit_id and f["sensor"] == body.sensor
                     and f["end_day"] is None), None)
        if same:
            return same  # idempotent: a second click leaves one open fault
        f = {"id": ids["fault"], "unit_id": body.unit_id, "sensor": body.sensor, "type": body.type,
             "start_day": S["clock"]["sim_day"], "end_day": None, "source": "toggle"}
        ids["fault"] += 1
        S["faults"].append(f)
        refresh(body.unit_id)
        add_event("sensor_issue", body.unit_id, "Sensor issue",
                  f"{LABEL[body.sensor]} sensor {FAULT_WORDS[body.type]}. Instrument check requested, no crew call.",
                  "warning", {"sensor": body.sensor, "flag_type": FAULT_FLAG[body.type]})
        return f

    @app.delete("/api/testmode/faults/{fault_id}", dependencies=[Depends(require_admin)])
    def end_fault(fault_id: int):
        f = next((f for f in S["faults"] if f["id"] == fault_id), None)
        if not f:
            raise HTTPException(404, "unknown fault")
        if f["end_day"] is None:
            f["end_day"] = S["clock"]["sim_day"]
            refresh(f["unit_id"])
        return f  # types.ts Fault

    @app.post("/api/admin/reset", dependencies=[Depends(require_admin)])
    def admin_reset():
        init_state()
        return {"ok": True}

    @app.post("/api/admin/tune", dependencies=[Depends(require_admin)])
    def admin_tune():
        return {"threshold": 0.4, "horizon_days": 14}  # mock: real one re-runs ml/tune

    class SimCallBody(BaseModel):
        unit_id: str = "GPR-02"
        technician_id: int = 8
        earliest_day: int = 35  # day 35 is a Monday ("not before Monday")
        ring: bool = False      # True: only ring the phone page, a human answers

    @app.post("/api/admin/simulate-call", dependencies=[Depends(require_admin)])
    def simulate_call(body: SimCallBody = SimCallBody()):
        tech = TECHS.get(body.technician_id)
        if body.unit_id not in S["units"] or not tech:
            raise HTTPException(422, "unknown unit or technician")
        item = next((i for i in S["plan"] if i["unit_id"] == body.unit_id), None)
        if not body.ring and not item:
            raise HTTPException(422, "unit has no planned service to move")
        cr = start_call(body.unit_id, tech)
        if body.ring:
            return {"ok": True, "call_request_id": cr["call_request_id"], "field_page": f"/field/{tech['field_page_id']}"}
        # Full recorded flow with no phone. The real one replays recorded_call.json through the same code as a live call.
        uid, old, day = body.unit_id, item["planned_day"], body.earliest_day
        cr["state"] = "done"
        add_event("call_answered", uid, "Call answered", f"{tech['name']} answered.", payload={"call_request_id": cr["call_request_id"]})
        add_event("constraint_added", uid, "Constraint added",
                  f"{tech['name']} cannot service {uid} before day {day} ({weekday(day)}).", payload={"earliest_day": day})
        item["planned_day"], item["planned_date"] = day, day_date(day).isoformat()
        S["plan"].sort(key=lambda i: (i["planned_day"], i["unit_id"]))
        S["base"][uid]["next_service_day"] = day
        refresh(uid)
        add_event("plan_changed", uid, "Plan changed",
                  f"{uid} moved to day {day} (technician unavailable before {weekday(day)}).",
                  payload={"changes": [{"kind": "moved", "unit_id": uid, "old_day": old, "new_day": day}]})
        summary = f"{tech['name']} cannot service {uid} before {weekday(day)}. The plan moved {uid} to day {day}."
        rec_id = ids["call_record"]
        ids["call_record"] += 1
        S["call_records"][rec_id] = {  # CallRecord (types.ts). received_via "simulated" marks it as a replay
            "id": rec_id, "call_request_id": cr["call_request_id"], "unit_id": uid, "technician_id": tech["id"],
            "technician_name": tech["name"], "conversation_id": f"conv_sim_{rec_id:04d}", "language": "en",
            "transcript": [
                {"role": "agent", "message": f"Hi {tech['name'].split()[0]}, this is PipeGuard. Unit {uid} needs attention. Can your crew service it by Thursday?", "time_in_call_secs": 0},
                {"role": "user", "message": f"Not before {weekday(day)}.", "time_in_call_secs": 9},
                {"role": "agent", "message": f"So {weekday(day)}, correct?", "time_in_call_secs": 12},
                {"role": "user", "message": "Yes.", "time_in_call_secs": 15},
                {"role": "agent", "message": f"Got it. {uid} moves to {weekday(day)}.", "time_in_call_secs": 17},
            ],
            "summary": summary, "summary_en": summary, "duration_secs": 24, "received_via": "simulated",
            "data_collection": {"available_day": weekday(day), "verdict": "", "unit_mentioned": uid},
        }
        add_event("call_summary", uid, "Call summary", summary,
                  payload={"call_id": rec_id, "call_request_id": cr["call_request_id"]})
        return {"ok": True, "plan_changed": {"unit_id": uid, "old_day": old, "new_day": day}}


else:
    # Real mode. Routers are added here as they are built.
    from api.routers import field, voice, webhooks
    app.include_router(field.router)
    app.include_router(voice.router)
    app.include_router(webhooks.router)
