"""The Impact tab: Olise's policy simulation, served from memory (techstack 7.5, guide 8.7).

The cross-fitted predictions load once per process. core.simulate keys its cache on that exact DataFrame
object, so never reload it per request. Missing data raises ImpactUnavailable, which the API turns into 503.
"""
from __future__ import annotations

import logging
import os
import threading
from functools import lru_cache
from pathlib import Path

from sqlalchemy import text

from core.config import get_settings
from core.db import session_scope

log = logging.getLogger(__name__)
settings = get_settings()

# Same source as the engine (engine/pg_store.py get_capacity), so the Impact tab and the live plan agree.
CREWS_PER_STATION = int(os.environ.get("CREWS_PER_STATION", 2))

_lock = threading.Lock()
_oof = None
MAX_CONCURRENT = 2
_gate = threading.BoundedSemaphore(MAX_CONCURRENT)


class ImpactUnavailable(RuntimeError):
    pass


def _oof_paths() -> list[Path]:
    repo = Path(__file__).resolve().parents[1] / "ml" / "artifacts"
    return [Path(settings.model_dir) / "oof_predictions.parquet", repo / "oof_predictions.parquet"]


def get_oof():
    global _oof
    with _lock:
        if _oof is None:
            import pandas as pd
            for path in _oof_paths():
                if path.exists():
                    _oof = pd.read_parquet(path)
                    log.info("loaded %d cross-fitted prediction rows from %s", len(_oof), path)
                    break
            else:
                raise ImpactUnavailable("ml/artifacts/oof_predictions.parquet not found")
        return _oof


def stored_tuned() -> dict | None:
    with session_scope() as s:
        r = s.execute(text("SELECT threshold, horizon_days FROM engine_params WHERE id = 1")).first()
    return {"threshold": float(r[0]), "horizon_days": int(r[1])} if r else None


def run(request) -> dict:
    """request: core.contracts.SimulateRequest or a dict. Returns the SimulateResponse as a dict."""
    from core.simulate import run_policies
    oof = get_oof()
    with _gate:  # a few runs at once, the rest wait their turn
        return run_policies(oof, None, request, stored_tuned()).model_dump()


def default_request() -> dict:
    return {"crews_per_station": CREWS_PER_STATION, "cost_breakdown": settings.cost_breakdown,
            "cost_service": settings.cost_service, "threshold": None, "horizon_days": None}


@lru_cache(maxsize=4)
def _impact_cached(tuned: tuple | None) -> dict:
    return run(default_request())


def impact_default() -> dict:
    """The headline numbers at the default slider positions. Recomputed only when the tuned setting changes."""
    t = stored_tuned()
    return _impact_cached((t["threshold"], t["horizon_days"]) if t else None)


def tune_now() -> dict:
    """Self-tuning: pick the cheapest setting that still catches 90% of failures 14 days early, store it."""
    from core.simulate import get_sim_data, tune_grid
    best = tune_grid(get_sim_data(get_oof()), CREWS_PER_STATION, settings.cost_breakdown, settings.cost_service)[0]
    with session_scope() as s:
        s.execute(text("UPDATE engine_params SET threshold = :t, horizon_days = :h, tuned_at = now() WHERE id = 1"),
                  {"t": float(best.threshold), "h": int(best.horizon_days)})
    return {"threshold": float(best.threshold), "horizon_days": int(best.horizon_days)}


def warm() -> None:
    """At API start: build the arrays and memoise the default slider positions so the first request is fast."""
    from core.simulate import warm_up
    warm_up(get_oof(), stored_tuned())
