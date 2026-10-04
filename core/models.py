"""SQLModel tables (techstack section 10). Shared file: tell Olise and David before changing a column."""
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime, Index, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

# The 14 sensors that carry wear signal (techstack 5.2). Flat sensors are dropped.
# Matches SENSORS in Olise's core/sensors.py. Keep in sync.
SENSOR_COLUMNS = ("s2", "s3", "s4", "s7", "s8", "s9", "s11", "s12", "s13", "s14", "s15", "s17", "s20", "s21")


def _ts(onupdate: bool = False) -> Column:
    # timestamptz set by the DB, so every row uses one clock (UTC).
    kwargs = {"onupdate": func.now()} if onupdate else {}
    return Column(DateTime(timezone=True), server_default=func.now(), nullable=False, **kwargs)


class Station(SQLModel, table=True):
    __tablename__ = "stations"
    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(unique=True, index=True)  # NEW: EDS, HIN, WHT, GPR, DRH (used in API shapes)
    name: str
    lat: Optional[float] = None
    lon: Optional[float] = None


class Unit(SQLModel, table=True):
    __tablename__ = "units"
    id: str = Field(primary_key=True)  # e.g. "EDS-07"
    station_id: int = Field(foreign_key="stations.id", index=True)
    source_engine: int                 # NASA engine id this unit replays
    start_offset: int                  # NASA cycle where the replay starts
    # sim_day of this life's cycle 1. Negative for backfilled units. Reset on part_replaced.
    life_start_day: int = 0
    status: str = "healthy"            # healthy | watch | at_risk | failed
    serviced_count: int = 0
    # NEW: status memory for the "3 readings in a row" rule, so an engine restart doesn't forget it.
    above_count: int = 0               # consecutive readings with p_fail >= threshold
    below_count: int = 0               # consecutive readings under threshold - hysteresis


class Technician(SQLModel, table=True):
    __tablename__ = "technicians"
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    station_id: int = Field(foreign_key="stations.id", index=True)
    shift: str = "day"
    language: str = "en"               # en | fr
    field_page_id: str = Field(unique=True, index=True)  # unguessable slug in the /field URL
    is_backup: bool = False


class SimState(SQLModel, table=True):
    __tablename__ = "sim_state"
    id: int = Field(default=1, primary_key=True)  # single row, always id=1
    sim_day: int = 0
    status: str = "paused"             # running | paused
    speed_seconds_per_day: float = 1.0
    scenario_id: str = "demo_v1"
    # Bumped on every reset. Workers drop any message from an older epoch.
    epoch: int = 0
    updated_at: Optional[datetime] = Field(default=None, sa_column=_ts(onupdate=True))


class Reading(SQLModel, table=True):
    __tablename__ = "readings"
    # No FK on purpose: ~30k rows load via COPY and FK checks only slow it down.
    unit_id: str = Field(primary_key=True)
    sim_day: int = Field(primary_key=True)  # negative = backfilled warm-up history
    s2: Optional[float] = None
    s3: Optional[float] = None
    s4: Optional[float] = None
    s7: Optional[float] = None
    s8: Optional[float] = None
    s9: Optional[float] = None
    s11: Optional[float] = None
    s12: Optional[float] = None
    s13: Optional[float] = None
    s14: Optional[float] = None
    s15: Optional[float] = None
    s17: Optional[float] = None
    s20: Optional[float] = None
    s21: Optional[float] = None  # NULL means dead sensor or masked value


class QualityFlag(SQLModel, table=True):
    __tablename__ = "quality_flags"
    id: Optional[int] = Field(default=None, primary_key=True)
    unit_id: str = Field(index=True)
    sim_day: int                       # day the episode started
    sensor: str
    flag_type: str                     # sensor_offline | sensor_stuck | sensor_spike | sensor_out_of_range
    resolved_day: Optional[int] = None
    detail: str = Field(default="", sa_column_kwargs={"server_default": ""})  # note from the quality check
    # Idempotency: at most one OPEN flag per (unit, sensor, type).
    __table_args__ = (
        Index("uq_open_quality_flag", "unit_id", "sensor", "flag_type",
              unique=True, postgresql_where=text("resolved_day IS NULL")),
    )


class Prediction(SQLModel, table=True):
    __tablename__ = "predictions"
    # PK makes the engine's upsert on (unit_id, sim_day) idempotent.
    unit_id: str = Field(primary_key=True)
    sim_day: int = Field(primary_key=True)
    rul_low: float
    rul_likely: float
    rul_high: float
    p_fail_h: float                    # probability of failure within the horizon
    confidence: str = "normal"         # normal | low
    status: str = "healthy"
    reason: Optional[str] = None
    model_version: str = "v1"
    data_source: str = "live"          # live | fallback (precomputed predictions)
    # NEW: sensor lists the API returns as top_sensors (chart) and shows when values were masked.
    top_sensors: Optional[list] = Field(default=None, sa_column=Column(JSONB))
    masked_sensors: Optional[list] = Field(default=None, sa_column=Column(JSONB))
    # Newest-prediction-per-unit lookup for /api/fleet (DISTINCT ON ... sim_day DESC).
    __table_args__ = (Index("ix_predictions_unit_day_desc", "unit_id", text("sim_day DESC")),)


class EngineParams(SQLModel, table=True):
    __tablename__ = "engine_params"
    id: int = Field(default=1, primary_key=True)  # single row
    threshold: float = 0.5             # p_fail threshold for "at risk"; tuned, then nudged by feedback
    horizon_days: int = 14
    tuned_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    updated_at: Optional[datetime] = Field(default=None, sa_column=_ts(onupdate=True))


class PlanItem(SQLModel, table=True):
    __tablename__ = "plan_items"
    id: Optional[int] = Field(default=None, primary_key=True)
    unit_id: str = Field(index=True)
    planned_day: int
    technician_id: Optional[int] = None
    crew: int = Field(default=0, sa_column_kwargs={"server_default": "0"})  # 0-based crew slot
    expected_saving: float = 0.0
    reason: str = ""
    state: str = "planned"             # planned | done | blocked | needs_manager_decision


class Constraint(SQLModel, table=True):
    __tablename__ = "constraints"
    id: Optional[int] = Field(default=None, primary_key=True)
    technician_id: Optional[int] = None  # CHANGED: contract allows a constraint with no technician
    unit_id: str
    earliest_day: int                  # sim_day the technician can start
    note: Optional[str] = None
    source: str = "voice"              # voice | manual
    call_request_id: Optional[int] = None
    created_at: Optional[datetime] = Field(default=None, sa_column=_ts())
    # Idempotency for voice calls (both IDs are set there). Postgres treats NULLs as distinct,
    # so manual constraints must be de-duplicated in code.
    __table_args__ = (
        UniqueConstraint("unit_id", "technician_id", "earliest_day", "call_request_id", name="uq_constraint_once"),
    )


class CallRequest(SQLModel, table=True):
    __tablename__ = "call_requests"
    id: Optional[int] = Field(default=None, primary_key=True)
    unit_id: str = Field(index=True)
    technician_id: int
    sim_day: int
    state: str = "ringing"             # ringing | answered | missed | escalated | done
    attempt: int = 1                   # 1 = primary technician, 2 = backup
    # REAL time, stored in the DB so a restart cannot lose a ringing call.
    ring_expires_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    # The sweeper finds expired rings with (state, ring_expires_at).
    __table_args__ = (Index("ix_call_requests_state_expiry", "state", "ring_expires_at"),)


class Call(SQLModel, table=True):
    __tablename__ = "calls"
    id: Optional[int] = Field(default=None, primary_key=True)
    call_request_id: Optional[int] = Field(default=None, index=True)
    # Unique: webhook retries upsert the same row.
    conversation_id: Optional[str] = Field(default=None, unique=True)
    language: str = "en"
    transcript: Optional[list] = Field(default=None, sa_column=Column(JSONB))
    summary: Optional[str] = None
    data_collection: Optional[dict] = Field(default=None, sa_column=Column(JSONB))
    duration_secs: Optional[int] = None
    received_via: Optional[str] = None  # webhook | pull | webhook_fallback
    # ElevenLabs report card, [{criteria_id, result, rationale}]. Null when the call has none.
    evaluation: Optional[list] = Field(default=None, sa_column=Column(JSONB))
    # Set when the phone page reports hang-up. The sweeper pulls the transcript if no webhook arrives.
    ended_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))


class Feedback(SQLModel, table=True):
    __tablename__ = "feedback"
    id: Optional[int] = Field(default=None, primary_key=True)
    unit_id: str
    technician_id: int
    verdict: str                       # confirmed_wear | looks_fine | part_replaced
    note: Optional[str] = None
    sim_day: int


class Fault(SQLModel, table=True):
    __tablename__ = "faults"
    id: Optional[int] = Field(default=None, primary_key=True)
    unit_id: str
    sensor: str
    type: str                          # dead | stuck | spike | out_of_range
    start_day: int
    end_day: Optional[int] = None
    source: str = "toggle"             # planted | toggle
    # Clicking the same toggle twice must leave one open fault.
    __table_args__ = (
        Index("uq_open_fault", "unit_id", "sensor", unique=True, postgresql_where=text("end_day IS NULL")),
    )


class Event(SQLModel, table=True):
    __tablename__ = "events"
    id: Optional[int] = Field(default=None, primary_key=True)  # also the SSE event_id
    sim_day: int
    type: str                          # status_change | plan_changed | call_summary | failure | ...
    unit_id: Optional[str] = None
    # NEW: shown directly in the decision log. payload keeps any extra structured data.
    title: str = ""
    detail: str = ""
    severity: str = "info"             # info | warning | critical
    payload: Optional[dict] = Field(default=None, sa_column=Column(JSONB))
    created_at: Optional[datetime] = Field(default=None, sa_column=_ts())
    # Decision log per unit.
    __table_args__ = (Index("ix_events_unit_id_id", "unit_id", "id"),)