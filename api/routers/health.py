"""API router: real health check (replaces the mock one). The preflight script and the dashboard banner read it."""
import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from core import reads
from core.db import session_scope

log = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get("/api/health")
def health():
    try:
        with session_scope() as s:
            return reads.health(s)
    except Exception as exc:
        log.exception("health check failed")
        return JSONResponse({"status": "degraded", "ok": False, "mock_api": False, "database": False,
                             "detail": type(exc).__name__}, status_code=503)
