"""API router: the weekly plan, work orders, manager approval and manager decisions (techstack 11.1).

Approval and decision state is derived from the event log (core/approvals.py), so it survives the engine
rewriting plan rows. Approving or deciding twice changes nothing and writes no second event.
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from core import approvals, reads
from core.db import session_scope

router = APIRouter(tags=["plan"])


def _find(items: list[dict], item_id: int) -> dict:
    item = next((i for i in items if i["id"] == item_id), None)
    if item is None:
        raise HTTPException(404, "unknown plan item")
    return item


@router.get("/api/plan")
def plan():
    with session_scope() as s:
        return reads.plan_items(s)


@router.post("/api/plan/approve-all")
def approve_all():
    """Release every proposed item. Items that need a manager decision are not approved here."""
    with session_scope() as s:
        waiting = [i for i in reads.plan_items(s) if i["approval"] == "proposed" and i["state"] != "needs_manager_decision"]
        return {"approved": sum(approvals.approve(s, i["unit_id"], i["planned_day"]) for i in waiting)}


@router.post("/api/plan/{item_id}/approve")
def approve(item_id: int):
    with session_scope() as s:
        item = _find(reads.plan_items(s), item_id)
        if item["state"] != "needs_manager_decision":
            approvals.approve(s, item["unit_id"], item["planned_day"])
        return _find(reads.plan_items(s), item_id)


class DecideBody(BaseModel):
    choice: str  # overtime | defer


@router.post("/api/plan/{item_id}/decide")
def decide(item_id: int, body: DecideBody):
    if body.choice not in ("overtime", "defer"):
        raise HTTPException(422, "choice must be overtime or defer")
    with session_scope() as s:
        items = reads.plan_items(s)
        item = _find(items, item_id)
        if item["state"] != "needs_manager_decision" and not item.get("decision"):
            raise HTTPException(409, "this item does not need a decision")
        approvals.decide(s, item["unit_id"], body.choice)
        return next(i for i in reads.plan_items(s) if i["unit_id"] == item["unit_id"])


@router.get("/api/work-orders.csv")
def work_orders():
    with session_scope() as s:
        filename, body = reads.work_orders_csv(s)
    return Response(body, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
