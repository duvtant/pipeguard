"""What the engine worker needs from the database, as an interface, plus an in-memory version.

Owner: Olise. The worker only talks to a `Store`. `engine/pg_store.py` implements it on PostgreSQL
(techstack section 10 schema); `MemoryStore` implements it in memory for tests and dry runs.
When Ebube's core/db.py helpers land, PgStore should delegate to them (one place for SQL).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Protocol

import pandas as pd

from core.contracts import Capacity, Constraint, EventDraft, PlanItem, PlanResult, QualityFlag, VerdictRecord
from engine.pipeline import UnitInfo


@dataclass
class SimState:
    sim_day: int
    epoch: int
    status: str = "running"


@dataclass
class PredictionRow:
    unit_id: str
    sim_day: int
    rul_low: float
    rul_likely: float
    rul_high: float
    p_fail_h: float
    confidence: str
    status: str
    reason: str
    model_version: str
    data_source: str = "live"
    top_sensors: list[str] = field(default_factory=list)
    sensor_issue: bool = False
    display_status: str = "healthy"


class Store(Protocol):
    def get_sim_state(self) -> SimState: ...
    def get_engine_params(self) -> tuple[float, int]: ...                 # (threshold, horizon_days)
    def get_capacity(self) -> Capacity: ...
    def get_units(self) -> list[UnitInfo]: ...
    def get_readings(self, after_day: int, upto_day: int) -> pd.DataFrame: ...   # unit_id, sim_day, sensors
    def get_prediction_history(self, unit_id: str, from_day: int, before_day: int) -> list[PredictionRow]: ...
    def upsert_predictions(self, rows: list[PredictionRow]) -> None: ...
    def upsert_quality_flags(self, flags: list[QualityFlag]) -> tuple[list[QualityFlag], list[QualityFlag]]: ...  # (created, newly resolved)
    def get_constraints(self, today: int) -> list[Constraint]: ...
    def get_verdicts(self) -> list[VerdictRecord]: ...
    def replan(self, build: Callable[[list[PlanItem]], PlanResult], sim_day: int) -> PlanResult: ...  # under the advisory lock
    def write_events(self, events: list[EventDraft]) -> list[int]: ...    # inserts + NOTIFY ui_event
    def after_tick(self, sim_day: int) -> None: ...                        # alert policy hook (Ebube's core/alerts.py)


class MemoryStore:
    """In-memory Store. Same semantics as the database version (upserts keyed like the real tables)."""

    def __init__(self, units: list[UnitInfo], readings: pd.DataFrame, threshold: float = 0.5, horizon: int = 14,
                 crews: int = 2, sim_day: int = 0, epoch: int = 1):
        self.units = {u.unit_id: u for u in units}
        self.readings = readings.sort_values(["unit_id", "sim_day"]).reset_index(drop=True)
        self.state = SimState(sim_day=sim_day, epoch=epoch)
        self.params = (threshold, horizon)
        self.capacity = Capacity(crews_per_station=crews)
        self.predictions: dict[tuple[str, int], PredictionRow] = {}
        self.flags: dict[tuple[str, str, str, int], QualityFlag] = {}
        self.constraints: list[Constraint] = []
        self.verdicts: list[VerdictRecord] = []
        self.plan: list[PlanItem] = []
        self.events: list[EventDraft] = []
        self.ticks: list[int] = []

    def get_sim_state(self) -> SimState:
        return self.state

    def get_engine_params(self) -> tuple[float, int]:
        return self.params

    def get_capacity(self) -> Capacity:
        return self.capacity

    def get_units(self) -> list[UnitInfo]:
        return list(self.units.values())

    def get_readings(self, after_day: int, upto_day: int) -> pd.DataFrame:
        r = self.readings
        return r[(r["sim_day"] > after_day) & (r["sim_day"] <= upto_day)]

    def get_prediction_history(self, unit_id: str, from_day: int, before_day: int) -> list[PredictionRow]:
        return [p for (u, d), p in sorted(self.predictions.items()) if u == unit_id and from_day <= d < before_day]

    def upsert_predictions(self, rows: list[PredictionRow]) -> None:
        for r in rows:
            self.predictions[(r.unit_id, r.sim_day)] = r

    def upsert_quality_flags(self, flags: list[QualityFlag]) -> tuple[list[QualityFlag], list[QualityFlag]]:
        created, resolved = [], []
        for f in flags:
            key = (f.unit_id, f.sensor, f.flag_type, f.sim_day)
            old = self.flags.get(key)
            if old is None:
                created.append(f)
            if f.resolved_day is not None and (old is None or old.resolved_day is None):
                resolved.append(f)
            self.flags[key] = f
        return created, resolved

    def get_constraints(self, today: int) -> list[Constraint]:
        return list(self.constraints)

    def get_verdicts(self) -> list[VerdictRecord]:
        return list(self.verdicts)

    def replan(self, build, sim_day: int) -> PlanResult:
        result = build(list(self.plan))
        self.plan = list(result.items)
        return result

    def write_events(self, events: list[EventDraft]) -> list[int]:
        start = len(self.events)
        self.events.extend(events)
        return list(range(start + 1, start + 1 + len(events)))

    def after_tick(self, sim_day: int) -> None:
        self.ticks.append(sim_day)
