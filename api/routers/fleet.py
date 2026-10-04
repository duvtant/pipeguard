"""API router: fleet, unit detail, technicians, calls and the small chart endpoints (techstack 11.1)."""
from fastapi import APIRouter, HTTPException

from api.routers.field import CONNECTED
from core import reads
from core.db import session_scope

router = APIRouter(tags=["fleet"])


@router.get("/api/fleet")
def fleet():
    with session_scope() as s:
        return reads.fleet(s)


@router.get("/api/fleet/trend")
def fleet_trend():
    with session_scope() as s:
        return reads.trend(s)


@router.get("/api/units/{unit_id}")
def unit_detail(unit_id: str):
    with session_scope() as s:
        out = reads.unit_detail(s, unit_id)
    if out is None:
        raise HTTPException(404, "unknown unit")
    return out


@router.get("/api/technicians")
def technicians():
    with session_scope() as s:
        return reads.technicians(s, CONNECTED)


@router.get("/api/calls/{call_id}")
def get_call(call_id: int):
    with session_scope() as s:
        out = reads.call_record(s, call_id)
    if out is None:
        raise HTTPException(404, "unknown call")
    return out


@router.get("/api/feedback/stats")
def feedback_stats():
    with session_scope() as s:
        return reads.feedback_stats(s)


@router.get("/api/model")
def model():
    out = reads.model_metrics()
    if out is None:
        raise HTTPException(404, "model metadata not available")  # the dashboard hides the card
    return out
