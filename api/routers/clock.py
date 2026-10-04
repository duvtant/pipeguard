"""API router: the simulated clock (techstack 11.2). The simulator polls sim_state and listens for clock_cmd."""
import asyncio
import logging

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from api.deps import require_admin
from core import reads
from core.admin_ops import reset_demo
from core.db import notify, session_scope

log = logging.getLogger(__name__)
router = APIRouter(tags=["clock"])

SPEED_MIN, SPEED_MAX = 0.25, 5.0   # seconds per simulated day
ADVANCE_MAX = 1000                 # same cap the simulator applies
# Play, pause and speed are the manager's replay controls (bounded: the worst case is a paused clock) and stay open. Reset wipes the whole
# demo and advance can burn up to ADVANCE_MAX days of the scenario, so those two need the admin token, like /api/admin/reset (the same
# operation) always did. Found open on the deployed server, Oct 4.
ADMIN_ACTIONS = ("reset", "advance")


class ClockBody(BaseModel):
    action: str                    # play | pause | speed | advance | reset
    speed_seconds_per_day: float | None = None
    days: int | None = None


@router.get("/api/clock")
def get_clock():
    with session_scope() as s:
        return reads.clock_view(s)


def _apply(body: ClockBody) -> None:
    with session_scope() as s:
        if body.action in ("play", "pause"):
            done = s.execute(text("UPDATE sim_state SET status = :st WHERE id = 1"),
                             {"st": "running" if body.action == "play" else "paused"}).rowcount
        elif body.action == "speed":
            if body.speed_seconds_per_day is None:
                raise HTTPException(422, "speed needs speed_seconds_per_day")
            speed = max(SPEED_MIN, min(SPEED_MAX, float(body.speed_seconds_per_day)))
            done = s.execute(text("UPDATE sim_state SET speed_seconds_per_day = :v WHERE id = 1"), {"v": speed}).rowcount
        else:  # advance: works while paused; the simulator fast-forwards that many days
            n = max(1, min(int(body.days or 1), ADVANCE_MAX))
            done = 1 if s.execute(text("SELECT 1 FROM sim_state WHERE id = 1")).first() else 0
            notify(s, "clock_cmd", f"advance:{n}")
        if not done:
            raise HTTPException(409, "the database has not been seeded yet")


@router.post("/api/clock")
async def set_clock(body: ClockBody, x_admin_token: str | None = Header(default=None)):
    if body.action not in ("play", "pause", "speed", "advance", "reset"):
        raise HTTPException(422, "action must be play, pause, speed, advance or reset")
    if body.action in ADMIN_ACTIONS:
        require_admin(x_admin_token)
    if body.action == "reset":
        try:
            await asyncio.to_thread(reset_demo)
        except RuntimeError as exc:
            log.error("reset failed: %s", exc)
            raise HTTPException(500, f"reset failed: {exc}")
    else:
        await asyncio.to_thread(_apply, body)
    return await asyncio.to_thread(get_clock)
