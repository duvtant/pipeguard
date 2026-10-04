"""Tests run against their own database (pipeguard_test), never the seeded demo database."""
import os
import sys
from pathlib import Path

import psycopg
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import get_settings  # noqa: E402

_base = os.environ.get("DATABASE_URL") or get_settings().database_url
_test_url = _base.rsplit("/", 1)[0] + "/pipeguard_test"
os.environ["DATABASE_URL"] = _test_url
get_settings.cache_clear()

with psycopg.connect(_base.replace("postgresql+psycopg://", "postgresql://", 1), autocommit=True) as _c:
    if not _c.execute("SELECT 1 FROM pg_database WHERE datname = 'pipeguard_test'").fetchone():
        _c.execute("CREATE DATABASE pipeguard_test")

from sqlalchemy import text  # noqa: E402
from sqlmodel import Session  # noqa: E402

from core.db import engine, init_db  # noqa: E402

init_db()

from core.migrate import ensure_columns  # noqa: E402

ensure_columns()  # test database may predate the newest columns

ALL = ("stations, units, technicians, sim_state, readings, quality_flags, predictions, engine_params, "
       "plan_items, constraints, call_requests, calls, feedback, faults, events")


@pytest.fixture
def db():
    """Empty tables plus a tiny roster. EDS has two primaries and a backup, HIN has one tech and no backup."""
    with Session(engine) as s:
        s.execute(text(f"TRUNCATE {ALL} RESTART IDENTITY CASCADE"))
        s.execute(text("INSERT INTO stations (code, name) VALUES ('EDS', 'Edson'), ('HIN', 'Hinton')"))
        s.execute(text("INSERT INTO technicians (name, station_id, shift, language, field_page_id, is_backup) VALUES "
                       "('Anna Primary', 1, 'day', 'en', 'slug-anna', false), ('Marc Tremblay', 1, 'day', 'fr', 'slug-marc', false), "
                       "('Bo Backup', 1, 'day', 'en', 'slug-bo', true), ('Hana Solo', 2, 'day', 'en', 'slug-hana', false)"))
        for i in range(1, 6):
            s.execute(text("INSERT INTO units (id, station_id, source_engine, start_offset, life_start_day, status, serviced_count, above_count, below_count) VALUES (:u, 1, :i, 0, 0, 'healthy', 0, 0, 0)"),
                      {"u": f"EDS-{i:02d}", "i": i})
        s.execute(text("INSERT INTO units (id, station_id, source_engine, start_offset, life_start_day, status, serviced_count, above_count, below_count) VALUES ('HIN-01', 2, 21, 0, 0, 'healthy', 0, 0, 0)"))
        s.execute(text("INSERT INTO sim_state (id, sim_day, status, speed_seconds_per_day, scenario_id, epoch) VALUES (1, 10, 'paused', 1.0, 'demo_v1', 0)"))
        s.commit()
        yield s
        s.rollback()


def predict(s, unit_id, p_fail, status="at_risk", day=10, rul_low=6.0, rul_high=14.0, reason="Fan speed drifting"):
    s.execute(text("INSERT INTO predictions (unit_id, sim_day, rul_low, rul_likely, rul_high, p_fail_h, status, reason, "
                   "confidence, model_version, data_source) VALUES (:u, :d, :lo, :li, :hi, :p, :st, :r, 'normal', 'v1', 'live') ON CONFLICT (unit_id, sim_day) DO UPDATE SET "
                   "p_fail_h = :p, status = :st, rul_low = :lo, rul_likely = :li, rul_high = :hi, reason = :r"),
              {"u": unit_id, "d": day, "lo": rul_low, "li": (rul_low + rul_high) / 2, "hi": rul_high,
               "p": p_fail, "st": status, "r": reason})
    s.commit()
