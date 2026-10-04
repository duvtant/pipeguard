"""API router: the decision log and its live stream (techstack 11.5).

The stream polls the events table twice a second instead of relaying NOTIFY. It cannot drop an event, it
survives a database restart, and the cost is one tiny query per open dashboard.
"""
import asyncio
import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from core import reads
from core.db import session_scope

log = logging.getLogger(__name__)
router = APIRouter(tags=["events"])

REPLAY = 20          # events re-sent on connect; the dashboard de-duplicates by event_id
POLL_SECS = 0.5
KEEPALIVE_TICKS = 30  # a comment line every ~15 s keeps proxies from closing an idle stream


@router.get("/api/events")
def events(after_id: int = 0):
    with session_scope() as s:
        return reads.events_after(s, after_id)


def start_cursor(last_event_id: str | None) -> int:
    """Where a new stream starts. Reconnects resume just before what the browser last saw."""
    with session_scope() as s:
        newest = reads.max_event_id(s)
    try:
        last = int(last_event_id) if last_event_id else None
    except ValueError:
        last = None
    return max((last if last is not None else newest) - REPLAY, 0)


def fetch_after(cursor: int) -> list[dict]:
    with session_scope() as s:
        return reads.events_since(s, cursor)


def frame(e: dict) -> str:
    # No "event:" name, so one onmessage handler receives everything. The type is inside the JSON.
    return f"id: {e['event_id']}\ndata: {json.dumps(e)}\n\n"


@router.get("/api/stream")
async def stream(request: Request):
    cursor = await asyncio.to_thread(start_cursor, request.headers.get("last-event-id"))

    async def gen():
        nonlocal cursor
        yield ": connected\n\n"
        ticks = 0
        while not await request.is_disconnected():
            try:
                for e in await asyncio.to_thread(fetch_after, cursor):
                    cursor = e["event_id"]
                    yield frame(e)
            except Exception:
                log.exception("event stream poll failed, retrying")
            ticks += 1
            if ticks % KEEPALIVE_TICKS == 0:
                yield ": keep-alive\n\n"
            await asyncio.sleep(POLL_SECS)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
