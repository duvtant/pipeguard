"""API router: ElevenLabs post-call webhook (techstack 12.6, guide 8.6).

Order matters: read the RAW body, verify the signature, then parse. Never log the body (it is a transcript).
The work runs inside the request (about 20 ms) so a database failure returns 500 and ElevenLabs retries,
which is safe because storing is idempotent on conversation_id.
"""
import asyncio
import hashlib
import hmac
import logging
import time
from functools import lru_cache

from fastapi import APIRouter, HTTPException, Request

from core.call_records import store_call
from core.config import get_settings
from core.db import session_scope

log = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

TOLERANCE_SECS = 30 * 60


@lru_cache
def _client():
    from elevenlabs.client import ElevenLabs
    return ElevenLabs(api_key=settings.elevenlabs_api_key or "unused")


def _manual_verify(raw: str, header: str, secret: str) -> dict:
    """Fallback if the SDK cannot be imported: HMAC-SHA256 of '{timestamp}.{body}', header 't=...,v0=...'."""
    import json
    parts = dict(p.split("=", 1) for p in header.split(",") if "=" in p)
    stamp, sig = parts.get("t", ""), parts.get("v0", "")
    if not stamp.isdigit() or abs(time.time() - int(stamp)) > TOLERANCE_SECS:
        raise ValueError("stale or missing timestamp")
    expected = hmac.new(secret.encode(), f"{stamp}.{raw}".encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        raise ValueError("bad signature")
    return json.loads(raw)


def verify(raw: bytes, header: str) -> dict:
    """Return the parsed event, or raise 401. Fails closed when the secret is not configured."""
    secret = settings.elevenlabs_webhook_secret
    if not secret:
        log.error("ELEVENLABS_WEBHOOK_SECRET is not set: rejecting webhook")
        raise HTTPException(401, "webhook secret not configured")
    try:
        body = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(401, "bad body")
    try:
        try:
            client = _client()
        except ImportError:
            return _manual_verify(body, header, secret)
        return client.webhooks.construct_event(rawBody=body, sig_header=header, secret=secret)
    except Exception:
        raise HTTPException(401, "bad signature")


def _store(data: dict) -> dict:
    with session_scope() as s:
        return store_call(s, data, received_via="webhook")


@router.post("/elevenlabs/post-call")
async def post_call(request: Request):
    raw = await request.body()
    event = verify(raw, request.headers.get("elevenlabs-signature", ""))
    if not isinstance(event, dict) or event.get("type") != "post_call_transcription":
        return {"ok": True, "ignored": str(event.get("type")) if isinstance(event, dict) else None}
    data = event.get("data")
    result = await asyncio.to_thread(_store, data if isinstance(data, dict) else {})
    return {"ok": True, "stored": bool(result.get("stored"))}
