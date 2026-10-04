"""API router: the Impact tab (techstack 11.1). Olise's simulation, in-process, loaded once."""
import asyncio
import logging

from fastapi import APIRouter, HTTPException

from core import impact
from core.contracts import SimulateRequest

log = logging.getLogger(__name__)
router = APIRouter(tags=["simulate"])


async def _run(fn, *args):
    try:
        return await asyncio.to_thread(fn, *args)
    except impact.ImpactUnavailable as exc:
        raise HTTPException(503, f"simulation data not available: {exc}")


@router.post("/api/simulate")
async def simulate(body: SimulateRequest):
    return await _run(impact.run, body)


@router.get("/api/impact")
async def get_impact():
    # David's handlers still define this one. The dashboard should use POST /api/simulate.
    return await _run(impact.impact_default)
