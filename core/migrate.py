"""Idempotent column additions for databases created before a model change (no Alembic in this project).

Fresh databases get these columns from create_all; existing ones get them here. Safe to run every start.
"""
from sqlalchemy import text

from core.db import engine

ADD_COLUMNS = (
    ("calls", "evaluation", "jsonb"),        # ElevenLabs report card: [{criteria_id, result, rationale}]
    ("calls", "ended_at", "timestamptz"),    # phone reported hang-up: starts the 60 s webhook timer
)


def ensure_columns() -> None:
    with engine.begin() as conn:
        for table, column, sql_type in ADD_COLUMNS:
            if conn.execute(text("SELECT to_regclass(:t)"), {"t": table}).scalar():
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {sql_type}"))
