"""FastAPI app. With MOCK_API=1 it serves api/fixtures/*.json and needs no database,
 David you can build the dashboard before the real engine exists.
Real routers (api/routers/*) get included in the non-mock branch as they're built.
"""
import asyncio
import json
from datetime import date, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.config import get_settings

settings = get_settings()
app = FastAPI(title="PipeGuard API")
FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str):
    # Read per request: the files are small, and edits show up without a restart.
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@app.get("/api/health")
def health():
    # Real checks (DB, simulator and engine tick age) come with the real API.
    return {"ok": True, "mock_api": settings.mock_api, "model_version": "v1",
            "data_source": {"live": 100, "fallback": 0}}


if settings.mock_api:
    # Browser on another origin (Vite dev server, Codespaces URL) needs CORS. Mock mode only.
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    CALENDAR_START = date(2026, 10, 5)  # sim_day 0 = Monday, same as scenario.json
    # In-memory clock so play, pause and speed clicks in the dashboard visibly do something.
    clock = {"sim_day": 31, "status": "paused", "speed_seconds_per_day": 1.0}

    def clock_view():
        d = CALENDAR_START + timedelta(days=clock["sim_day"])
        return {**clock, "calendar_date": d.isoformat(), "weekday": d.strftime("%A")}

    @app.get("/api/fleet")
    def fleet():
        data = load("fleet.json")
        data["sim_day"], data["clock"] = clock["sim_day"], clock_view()
        return data

    @app.get("/api/units/{unit_id}")
    def unit_detail(unit_id: str):
        details = load("unit_details.json")
        if unit_id in details:
            return details[unit_id]
        # Units without a hand-built detail: fleet fields plus empty lists.
        for u in load("fleet.json")["units"]:
            if u["unit_id"] == unit_id:
                return {**u, "history": [], "sensors": [], "events": [], "calls": [], "quality_flags": []}
        raise HTTPException(404, "unknown unit")

    @app.get("/api/plan")
    def plan():
        return load("plan.json")

    @app.get("/api/events")
    def events(after_id: int = 0):
        # Polling fallback for the SSE stream: same data, filtered by id.
        return {"events": [e for e in load("events.json")["events"] if e["event_id"] > after_id]}

    @app.get("/api/technicians")
    def technicians():
        return load("technicians.json")

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
        # Keep the tuned and default cards roughly consistent with the recomputed pipeguard row.
        ratio = data["default"]["total_cost"] / data["tuned"]["total_cost"]
        pg = next(p for p in data["policies"] if p["policy"] == "pipeguard")["total_cost"]
        data["tuned"]["total_cost"] = pg
        data["default"]["total_cost"] = round(pg * ratio)
        return data

    @app.get("/api/impact")
    def impact():
        return load("simulate.json")

    class ClockBody(BaseModel):
        action: str  # play | pause | speed | reset | advance
        speed_seconds_per_day: float | None = None
        days: int | None = None

    @app.post("/api/clock")
    def set_clock(body: ClockBody):
        if body.action == "play":
            clock["status"] = "running"
        elif body.action == "pause":
            clock["status"] = "paused"
        elif body.action == "speed" and body.speed_seconds_per_day is not None:
            clock["speed_seconds_per_day"] = max(0.25, min(5.0, body.speed_seconds_per_day))  # allowed range 0.25-5
        elif body.action == "advance":
            clock["sim_day"] += body.days or 1
        elif body.action == "reset":
            clock.update(sim_day=31, status="paused", speed_seconds_per_day=1.0)
        else:
            raise HTTPException(422, "bad clock action")
        return clock_view()

    def sse(e: dict) -> str:
        # One SSE frame. The id lets the browser resume with Last-Event-ID.
        return f"id: {e['event_id']}\nevent: {e['type']}\ndata: {json.dumps(e)}\n\n"

    @app.get("/api/stream")
    async def stream(request: Request):
        last = int(request.headers.get("last-event-id", 0))

        async def gen():
            # Replay from last_id - 20 like the real API; clients de-duplicate by event_id.
            for e in load("events.json")["events"]:
                if e["event_id"] > last - 20:
                    yield sse(e)
            while not await request.is_disconnected():
                yield ": keep-alive\n\n"  # comment frame keeps proxies from closing the stream
                await asyncio.sleep(15)

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})