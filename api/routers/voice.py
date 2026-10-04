"""API router: ElevenLabs server tools (techstack 11.4).

A person is waiting on the line, so after auth every endpoint answers HTTP 200 with {ok, say}, even for
garbage input or an internal error. Auth failure is the only non-200 (the agent never calls without its key).
"""
import asyncio
import hmac
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from core import voice_tools
from core.config import get_settings
from core.db import session_scope

log = logging.getLogger(__name__)
settings = get_settings()


def require_tool_secret(authorization: str | None = Header(default=None)):
    # Open when VOICE_TOOL_SECRET is empty (local dev). Set it in .env for the demo.
    if settings.voice_tool_secret and not hmac.compare_digest(
            authorization or "", f"Bearer {settings.voice_tool_secret}"):
        raise HTTPException(401, "bad tool secret")


router = APIRouter(prefix="/api/voice/tools", tags=["voice"], dependencies=[Depends(require_tool_secret)])


async def _body(request: Request) -> dict:
    try:
        data = await request.json()
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _run(fn, data: dict) -> dict:
    try:
        with session_scope() as s:
            return fn(s, data)
    except Exception:
        log.exception("voice tool %s failed", fn.__name__)
        return voice_tools.error_say()


async def _call(fn, request: Request) -> dict:
    return await asyncio.to_thread(_run, fn, await _body(request))


@router.post("/unit-status")
async def unit_status(request: Request):
    return await _call(voice_tools.unit_status, request)


@router.post("/submit-availability")
async def submit_availability(request: Request):
    return await _call(voice_tools.submit_availability, request)


@router.post("/field-report")
async def field_report(request: Request):
    return await _call(voice_tools.field_report, request)


@router.post("/feedback")
async def feedback(request: Request):
    return await _call(voice_tools.feedback, request)
