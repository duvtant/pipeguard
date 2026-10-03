"""DB engine, sessions, and NOTIFY/LISTEN helpers (techstack sections 4 and 9)."""
import logging
import time
from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg import sql
from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

from core.config import get_settings

log = logging.getLogger(__name__)
settings = get_settings()

# pool_pre_ping discards dead connections after a DB restart instead of erroring.
engine = create_engine(settings.database_url, pool_pre_ping=True, pool_size=10, max_overflow=10)

# Sentinel yielded by listen() after a reconnect. Consumers must catch up from tables.
RECONNECTED = "__reconnected__"


def psycopg_dsn() -> str:
    # SQLAlchemy URL carries "+psycopg"; raw psycopg wants the plain scheme.
    return settings.database_url.replace("postgresql+psycopg://", "postgresql://", 1)


@contextmanager
def session_scope() -> Iterator[Session]:
    # For workers and scripts: commit on success, roll back on any error.
    with Session(engine) as s:
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise


def get_session() -> Iterator[Session]:
    # FastAPI dependency (Depends(get_session)). Endpoints commit explicitly.
    with Session(engine) as s:
        yield s


def wait_for_db(timeout: float = 60.0) -> None:
    # Containers start in parallel, so retry until Postgres answers.
    deadline = time.monotonic() + timeout
    while True:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return
        except Exception as exc:
            if time.monotonic() > deadline:
                raise RuntimeError(f"database not reachable after {timeout}s") from exc
            time.sleep(1)


def init_db() -> None:
    # Import registers every table on SQLModel.metadata before create_all.
    from core import models  # noqa: F401

    wait_for_db()
    # create_all skips tables that exist. No Alembic: reset recreates everything.
    SQLModel.metadata.create_all(engine)


def notify(session: Session, channel: str, payload: str | int) -> None:
    # pg_notify delivers only when the transaction COMMITS. Never notify before commit.
    # Send IDs only (payload limit ~8000 bytes), receivers read the row.
    session.execute(text("SELECT pg_notify(:c, :p)"), {"c": channel, "p": str(payload)})


def listen(channels: list[str]) -> Iterator[tuple[str, str]]:
    """Yield (channel, payload) forever. One receiving method only: the notifies() generator.

    Uses its own autocommit connection, never one from the pool.
    Notifications are lost while disconnected, so after a reconnect we yield
    (RECONNECTED, "") and the consumer reads missed rows from the tables.
    """
    backoff = 1.0
    first = True
    while True:
        try:
            with psycopg.connect(psycopg_dsn(), autocommit=True) as conn:
                for ch in channels:
                    # Identifier() quotes the channel name safely.
                    conn.execute(sql.SQL("LISTEN {}").format(sql.Identifier(ch)))
                backoff = 1.0
                if not first:
                    yield RECONNECTED, ""
                first = False
                while True:
                    # timeout lets the loop spin so a dead connection is noticed.
                    for n in conn.notifies(timeout=30):
                        yield n.channel, n.payload
        except psycopg.OperationalError as exc:
            log.warning("listen connection lost (%s), retrying in %.0fs", exc, backoff)
            time.sleep(backoff)
            backoff = min(backoff * 2, 10.0)