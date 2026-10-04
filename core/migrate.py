"""Idempotent column additions and defaults for databases created before a model change (no Alembic in this project).

Fresh databases get these columns from create_all; existing ones get them here. Safe to run every start.
"""
from sqlalchemy import text

from core.db import engine
from core.models import AppSettings

ADD_COLUMNS = (
    ("calls", "evaluation", "jsonb"),        # ElevenLabs report card: [{criteria_id, result, rationale}]
    ("calls", "ended_at", "timestamptz"),    # phone reported hang-up: starts the 60 s webhook timer
)


# NOT NULL columns that other lanes (the engine) insert into without naming them.
SET_DEFAULTS = (
    ("plan_items", "crew", "0"),
    ("quality_flags", "detail", "''"),
)


def ensure_columns() -> None:
    with engine.begin() as conn:
        AppSettings.__table__.create(conn, checkfirst=True)  # a table added after the database was first seeded
        for table, column, sql_type in ADD_COLUMNS:
            if conn.execute(text("SELECT to_regclass(:t)"), {"t": table}).scalar():
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {sql_type}"))
        for table, column, default in SET_DEFAULTS:
            if conn.execute(text("SELECT to_regclass(:t)"), {"t": table}).scalar():
                conn.execute(text(f"ALTER TABLE {table} ALTER COLUMN {column} SET DEFAULT {default}"))
