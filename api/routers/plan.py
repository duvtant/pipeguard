"""API router: the weekly plan and work orders (techstack 11.1). Approval and decisions come later."""
from fastapi import APIRouter
from fastapi.responses import Response

from core import reads
from core.db import session_scope

router = APIRouter(tags=["plan"])


@router.get("/api/plan")
def plan():
    with session_scope() as s:
        return reads.plan_items(s)


@router.get("/api/work-orders.csv")
def work_orders():
    with session_scope() as s:
        filename, body = reads.work_orders_csv(s)
    return Response(body, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
