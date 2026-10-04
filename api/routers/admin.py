"""API router: admin (techstack 11.2). Everything here needs X-Admin-Token."""
import asyncio
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from api.deps import require_admin
from core import demo_call, impact
from core.admin_ops import reset_demo
from core.db import session_scope

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.post("/reset")
async def admin_reset():
    """The demo reset: pause, wipe, reload the scenario. Takes a few seconds."""
    try:
        await asyncio.to_thread(reset_demo)
    except RuntimeError as exc:
        log.error("reset failed: %s", exc)
        raise HTTPException(500, f"reset failed: {exc}")
    return {"ok": True}


@router.post("/tune")
async def admin_tune():
    """Re-run the self-tuning on the cross-fitted predictions and store the winner in engine_params."""
    try:
        return await asyncio.to_thread(impact.tune_now)
    except impact.ImpactUnavailable as exc:
        raise HTTPException(503, f"simulation data not available: {exc}")


class SimCallBody(BaseModel):
    unit_id: str | None = None        # default: the earliest planned service
    technician_id: int | None = None  # default: that unit's technician
    ring: bool = False                # True: only ring the phone page, a human answers


@router.post("/simulate-call")
def simulate_call(background: BackgroundTasks, body: SimCallBody = SimCallBody()):
    try:
        with session_scope() as s:
            target = demo_call.pick_target(s, body.unit_id, body.technician_id)
            cid = demo_call.start(s, target)
    except demo_call.NothingToSimulate as exc:
        raise HTTPException(422, str(exc))
    if body.ring:
        return {"ok": True, "call_request_id": cid, "field_page": f"/field/{target['technician']['field_page_id']}"}
    background.add_task(demo_call.finish, cid, target)  # answer, tool call and record, spaced out
    return {"ok": True, "call_request_id": cid, "unit_id": target["unit_id"], "staged": True}
