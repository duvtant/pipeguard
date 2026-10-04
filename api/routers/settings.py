"""API router: the manager's runtime settings (techstack 11.1, Settings page).

GET returns the six settings; PUT merges the fields it is given, saves them in the one shared row (core/app_settings.py) and returns
all six. No admin token: this is a manager screen (single demo tenant), and every value is range-checked. The engine, the alert code
and the voice re-plan read the same row, so a change here takes effect on their next tick or call.
"""
from fastapi import APIRouter
from pydantic import BaseModel, Field

from core import app_settings
from core.db import session_scope

router = APIRouter(tags=["settings"])


class SettingsPatch(BaseModel):
    crews_per_station: int | None = Field(default=None, ge=0, le=5)
    cost_breakdown: float | None = Field(default=None, ge=0, le=5_000_000)
    cost_service: float | None = Field(default=None, ge=0, le=1_000_000)
    ring_timeout_secs: int | None = Field(default=None, ge=5, le=120)
    call_backup_when_missed: bool | None = None
    require_manager_for_conflicts: bool | None = None


@router.get("/api/settings")
def get_settings():
    with session_scope() as s:
        return app_settings.read(s)


@router.put("/api/settings")
def put_settings(body: SettingsPatch):
    with session_scope() as s:
        return app_settings.update(s, body.model_dump(exclude_none=True))
