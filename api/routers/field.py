"""API router: technician phone page (techstack 11.3, 12.7)."""
import asyncio
import json
import logging
import urllib.parse
import urllib.request

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text

from core import alerts
from core.config import get_settings
from core.db import session_scope
from core.simcal import today_text, weekday
from core.tech_actions import VERDICTS, record_feedback

log = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter(prefix="/api/field", tags=["field"])

# technician id -> open /stream connections. The technicians endpoint reads this for "online".
CONNECTED: dict[int, int] = {}

MOCK_SIGNED_URL = "wss://mock.invalid/v1/convai/conversation?agent_id=mock"


def _tech(s, slug: str):
    t = alerts.technician_by_slug(s, slug)
    if t is None:
        raise HTTPException(404, "unknown technician page")
    return t


def _signed_url() -> tuple[str, str | None]:
    """(signed_url, conversation_id or None). Without ElevenLabs keys, a mock URL for UI testing."""
    if not settings.elevenlabs_api_key or not settings.elevenlabs_agent_id:
        log.warning("ELEVENLABS_API_KEY / AGENT_ID not set: returning a mock signed URL")
        return MOCK_SIGNED_URL, None
    qs = {"agent_id": settings.elevenlabs_agent_id, "include_conversation_id": "true"}
    if settings.elevenlabs_environment:
        qs["environment"] = settings.elevenlabs_environment
    req = urllib.request.Request(
        "https://api.elevenlabs.io/v1/convai/conversation/get-signed-url?" + urllib.parse.urlencode(qs),
        headers={"xi-api-key": settings.elevenlabs_api_key})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.load(resp)
        url = data["signed_url"]
    except Exception as exc:
        log.error("signed URL request failed: %s", exc)
        raise HTTPException(502, "could not start the voice session, try again")
    conv = data.get("conversation_id") or urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get(
        "conversation_id", [None])[0]
    return url, conv


# ---------------------------------------------------------------- ring stream
def _poll_rings(tech_id: int, sent: set[int]) -> list[str]:
    with session_scope() as s:
        ids = [r[0] for r in s.execute(text(
            "SELECT id FROM call_requests WHERE technician_id = :t AND state = 'ringing' "
            "AND ring_expires_at > now() ORDER BY id"), {"t": tech_id})]
        frames = []
        for cid in ids:
            if cid not in sent:
                sent.add(cid)
                # Named "ring" event: the phone page uses addEventListener('ring', ...).
                frames.append(f"event: ring\ndata: {json.dumps(alerts.ring_payload(s, cid))}\n\n")
        return frames


@router.get("/{slug}/stream")
async def field_stream(slug: str, request: Request):
    def lookup():
        with session_scope() as s:
            return _tech(s, slug)["id"]
    tech_id = await asyncio.to_thread(lookup)

    async def gen():
        CONNECTED[tech_id] = CONNECTED.get(tech_id, 0) + 1
        sent: set[int] = set()  # a ring already ringing when the phone connects is still sent
        ticks = 0
        try:
            yield ": connected\n\n"
            while not await request.is_disconnected():
                for frame in await asyncio.to_thread(_poll_rings, tech_id, sent):
                    yield frame
                ticks += 1
                if ticks % 15 == 0:
                    yield ": keep-alive\n\n"
                await asyncio.sleep(1)
        finally:
            CONNECTED[tech_id] -= 1

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---------------------------------------------------------------- answer / decline
@router.post("/{slug}/answer")
def field_answer(slug: str):
    with session_scope() as s:
        tech = _tech(s, slug)
        cid = alerts.ringing_request(s, tech["id"])
        if cid is None:
            raise HTTPException(410, "call expired")
        # Fetch the credential first: if ElevenLabs fails, the ring stays alive and the phone can retry.
        signed_url, conv_id = _signed_url()
        if not alerts.answer_call(s, cid):
            raise HTTPException(410, "call expired")  # ran out while we were fetching
        if conv_id:
            alerts.link_conversation(s, tech["id"], conv_id)
        p = alerts.ring_payload(s, cid)
        day = alerts.sim_today(s)
        planned = s.execute(text("SELECT planned_day FROM plan_items WHERE unit_id = :u "
                                 "AND state IN ('planned', 'needs_manager_decision') "
                                 "ORDER BY planned_day LIMIT 1"), {"u": p["unit_id"]}).scalar()
        return {
            "signed_url": signed_url,
            "language": tech["language"],
            "dynamic_variables": {  # all strings (contract 4.3)
                "technician_id": str(tech["id"]), "technician_name": tech["name"], "unit_id": p["unit_id"],
                "station_name": p["station_name"], "rul_low": str(round(p["rul_low"])),
                "rul_high": str(round(p["rul_high"])), "reason": p["reason"],
                "proposed_day": weekday(planned) if planned is not None else "this week",
                "call_request_id": str(cid), "sim_today": today_text(day),
            },
        }


@router.post("/{slug}/decline")
def field_decline(slug: str):
    with session_scope() as s:
        tech = _tech(s, slug)
        cid = alerts.ringing_request(s, tech["id"], live_only=False)
        if cid is None or not alerts.miss_call(s, cid, "declined"):
            raise HTTPException(410, "no call ringing")
        return {"ok": True}


# ---------------------------------------------------------------- feedback / conversation
class FeedbackBody(BaseModel):
    unit_id: str
    verdict: str
    note: str | None = None


@router.post("/{slug}/feedback")
def field_feedback(slug: str, body: FeedbackBody):
    with session_scope() as s:
        tech = _tech(s, slug)
        if body.verdict not in VERDICTS:
            raise HTTPException(422, "bad verdict")
        try:
            res = record_feedback(s, body.unit_id, tech["id"], body.verdict, body.note)
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        return {"ok": True, "threshold": res["threshold"]}


class ConversationBody(BaseModel):
    conversation_id: str
    ended: bool = False  # phone sends true on hang-up


@router.post("/{slug}/conversation")
def field_conversation(slug: str, body: ConversationBody):
    with session_scope() as s:
        tech = _tech(s, slug)
        alerts.link_conversation(s, tech["id"], body.conversation_id, body.ended)
        return {"ok": True}
