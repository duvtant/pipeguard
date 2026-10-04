"""Settings the manager can change while the app runs (Settings page: GET and PUT /api/settings).

ONE shared database row, because the API, the engine and the simulator are separate processes: a value changed in the API
must be seen by the engine on its next tick. Before this module the six settings lived in four unrelated places (an env var read
by the engine, config defaults copied into two files, and two rules hard-coded), so no endpoint could have changed anything.

Defaults equal the previous behaviour, so nothing changes until someone edits a value. If the table or the row is missing (an older
database, or just after a demo reset, which truncates every table) readers fall back to the defaults.
"""
from __future__ import annotations

import os

from sqlalchemy import text
from sqlmodel import Session

from core.config import get_settings

FIELDS = ("crews_per_station", "cost_breakdown", "cost_service", "ring_timeout_secs",
          "call_backup_when_missed", "require_manager_for_conflicts")
_COLUMNS = ", ".join(FIELDS)


def defaults() -> dict:
    cfg = get_settings()
    return {"crews_per_station": int(os.environ.get("CREWS_PER_STATION", 2)),
            "cost_breakdown": float(cfg.cost_breakdown), "cost_service": float(cfg.cost_service),
            "ring_timeout_secs": int(cfg.ring_seconds),
            "call_backup_when_missed": True,
            "require_manager_for_conflicts": True}  # stored and shown, not enforced yet (the scheduler always asks a manager)


def _clean(row) -> dict:
    out = defaults()
    if row:
        out.update({k: row[k] for k in FIELDS if row[k] is not None})
    return {"crews_per_station": int(out["crews_per_station"]), "cost_breakdown": float(out["cost_breakdown"]),
            "cost_service": float(out["cost_service"]), "ring_timeout_secs": int(out["ring_timeout_secs"]),
            "call_backup_when_missed": bool(out["call_backup_when_missed"]),
            "require_manager_for_conflicts": bool(out["require_manager_for_conflicts"])}


def read(s: Session) -> dict:
    """For the API and the alert code (SQLAlchemy session)."""
    if not s.execute(text("SELECT to_regclass('app_settings')")).scalar():
        return defaults()
    return _clean(s.execute(text(f"SELECT {_COLUMNS} FROM app_settings WHERE id = 1")).mappings().first())


def read_conn(conn) -> dict:
    """For the engine (a psycopg connection with dict rows, see engine/pg_store.py)."""
    if not conn.execute("SELECT to_regclass('app_settings') IS NOT NULL AS ok").fetchone()["ok"]:
        return defaults()
    return _clean(conn.execute(f"SELECT {_COLUMNS} FROM app_settings WHERE id = 1").fetchone())


def update(s: Session, patch: dict) -> dict:
    """Merge the given fields into the shared row (creating it if needed) and return the full settings."""
    new = {**read(s), **{k: v for k, v in patch.items() if k in FIELDS and v is not None}}
    s.execute(text(
        "INSERT INTO app_settings (id, " + _COLUMNS + ", updated_at) VALUES (1, " + ", ".join(f":{k}" for k in FIELDS) + ", now()) "
        "ON CONFLICT (id) DO UPDATE SET " + ", ".join(f"{k} = EXCLUDED.{k}" for k in FIELDS) + ", updated_at = now()"), new)
    s.commit()
    return new
