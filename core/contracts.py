"""Pydantic types shared by all three lanes. Single source of truth. Shared file: changes need an ack.

Owner: Olise (v0), reviewed by Ebube and David. Spec: docs/delegation/00_TEAM_CONTRACT.md section 4
and docs/techstack.md. Enum spellings are exact (contract section 2).

Two groups of types live here:
  1. The engine interfaces (section 4.1): what the pure functions in core/ take and return.
  2. The HTTP shapes (section 4.3): what the API returns to the dashboard.

Bulk time series (readings, features, out-of-fold predictions) travel as pandas DataFrames, not as
lists of models, for speed. Their column contracts are the *_COLUMNS constants below.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from core.sensors import SENSORS

# ---------------------------------------------------------------------------------------------
# Enums (contract section 2, exact spellings)
# ---------------------------------------------------------------------------------------------
RiskStatus = Literal["healthy", "watch", "at_risk"]
DisplayStatus = Literal["healthy", "watch", "at_risk", "sensor_issue"]
Confidence = Literal["normal", "low"]
FaultType = Literal["dead", "stuck", "spike", "out_of_range"]
FlagType = Literal["sensor_offline", "sensor_stuck", "sensor_spike", "sensor_out_of_range"]
Verdict = Literal["confirmed_wear", "looks_fine", "part_replaced"]
PlanState = Literal["planned", "done", "blocked", "needs_manager_decision"]
CallState = Literal["ringing", "answered", "missed", "escalated", "done"]
EventType = Literal[
    "status_change", "sensor_issue", "call_requested", "call_answered", "constraint_added",
    "plan_changed", "call_summary", "feedback_received", "threshold_adjusted", "failure", "manager_alert",
]
Policy = Literal["run_to_failure", "fixed_schedule", "pipeguard"]
Severity = Literal["info", "warning", "critical"]
DataSource = Literal["live", "fallback"]
ChangeKind = Literal["added", "moved", "removed", "unchanged"]
Language = Literal["en", "fr"]

STATIONS: dict[str, str] = {
    "EDS": "Edson", "HIN": "Hinton", "WHT": "Whitecourt", "GPR": "Grande Prairie", "DRH": "Drumheller",
}
STATION_ORDER: list[str] = ["EDS", "HIN", "WHT", "GPR", "DRH"]


def unit_id_for_engine(source_engine: int) -> str:
    """NASA engine 1..100 -> unit id. Engines 1-20 are EDS-01..20, 21-40 HIN-01..20, and so on."""
    idx = int(source_engine) - 1
    return f"{STATION_ORDER[idx // 20]}-{idx % 20 + 1:02d}"


def station_of(unit_id: str) -> str:
    return unit_id.split("-")[0]


# ---------------------------------------------------------------------------------------------
# DataFrame column contracts
# ---------------------------------------------------------------------------------------------
# Readings for one or more units, one row per (unit_id, sim_day), sorted by sim_day within a unit.
# Only rows of the current life (sim_day >= life_start_day). Sensor values may be NaN (dead/masked).
READING_COLUMNS: list[str] = ["unit_id", "sim_day", "cycle", *SENSORS]

# ml/artifacts/oof_predictions.parquet: one row per (source_engine, cycle) of the 100 training engines.
OOF_COLUMNS: list[str] = [
    "source_engine", "unit_id", "cycle", "max_cycle", "rul_true", "rul_capped", "fold",
    "rul_low", "rul_likely", "rul_high",
]

# ml/artifacts/fallback/fallback_predictions.parquet: one row per (unit_id, scenario sim_day).
FALLBACK_COLUMNS: list[str] = [
    "unit_id", "source_engine", "sim_day", "cycle", "rul_low", "rul_likely", "rul_high", "confidence",
]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------------------------
# 1. Engine interfaces (contract section 4.1)
# ---------------------------------------------------------------------------------------------
class QualityFlag(_Model):
    """One flag per (unit, sensor, flag_type) episode, not one per day.

    `start_day` is the first reading the rule fired on. `resolved_day` is the reading on which the
    sensor completed 5 consecutive clean readings, or None while the episode is still open.
    """
    unit_id: str
    sensor: str
    flag_type: FlagType
    sim_day: int = Field(description="Day the episode started")
    resolved_day: int | None = None
    detail: str = ""


class Prediction(_Model):
    """Output of Predictor.predict for one unit on one day. Floats; round only in the UI."""
    unit_id: str
    sim_day: int
    rul_low: float
    rul_likely: float
    rul_high: float
    confidence: Confidence
    data_source: DataSource = "live"
    model_version: str = ""
    masked_sensors: list[str] = Field(default_factory=list)


class StatusState(_Model):
    """Per-unit status memory for classify(). Reset to StatusState() when a unit's life restarts."""
    status: RiskStatus = "healthy"
    above_count: int = 0   # consecutive reliable readings with p_fail >= threshold
    below_count: int = 0   # consecutive reliable readings with p_fail < threshold - hysteresis (while at_risk)


class Explanation(_Model):
    reason: str
    top_sensors: list[str] = Field(default_factory=list, description="Sensor ids, for the chart only")


# --- Scheduler -------------------------------------------------------------------------------
class PlanUnit(_Model):
    """A unit as the scheduler sees it."""
    unit_id: str
    station_code: str
    p_fail: float
    risk_status: RiskStatus
    rul_low: float
    failed: bool = False
    done: bool = False                 # already serviced in this life (excluded from the plan)
    urgency: float = 1.0               # feedback multiplier (looks_fine lowers it for 7 days)


class Capacity(_Model):
    """Crew slots. One service slot per crew per day."""
    crews_per_station: int = 2
    per_station: dict[str, int] = Field(default_factory=dict, description="Optional override per station code")
    blocked_days: dict[str, list[int]] = Field(default_factory=dict, description="station code -> days with no crew")

    def crews(self, station_code: str) -> int:
        return max(0, int(self.per_station.get(station_code, self.crews_per_station)))


class Constraint(_Model):
    """'Not before Friday' becomes earliest_day for that unit (the constraint binds the unit)."""
    unit_id: str
    earliest_day: int
    technician_id: int | None = None
    note: str = ""


class PlanParams(_Model):
    cost_breakdown: float = 200_000
    cost_service: float = 20_000
    window_days: int = 7
    book_watch: bool = Field(
        default=False,
        description="False (default): only at_risk units are booked; watch units with a positive saving are "
                    "returned in `deferred` (next in line). True: book them into free slots too.",
    )


class PlanItem(_Model):
    unit_id: str
    station_code: str
    planned_day: int
    crew: int = Field(description="0-based crew slot at the station that day; Ebube maps it to a technician")
    expected_saving: float
    reason: str
    state: PlanState = "planned"


class ManagerDecision(_Model):
    unit_id: str
    station_code: str
    reason: str


class PlanChange(_Model):
    kind: ChangeKind
    unit_id: str
    old_day: int | None = None
    new_day: int | None = None


class PlanResult(_Model):
    items: list[PlanItem]
    needs_manager_decision: list[str] = Field(default_factory=list, description="unit ids")
    decisions: list[ManagerDecision] = Field(default_factory=list, description="why each unit needs a decision")
    deferred: list[str] = Field(default_factory=list, description="watch units with positive saving but no free slot")
    changes: list[PlanChange] = Field(default_factory=list)

    @property
    def changed(self) -> bool:
        return any(c.kind != "unchanged" for c in self.changes)


# --- Feedback --------------------------------------------------------------------------------
class VerdictRecord(_Model):
    unit_id: str
    verdict: Verdict
    sim_day: int
    technician_id: int | None = None
    id: int | None = None


class FeedbackResult(_Model):
    threshold: float
    message: str | None = None
    urgency: dict[str, float] = Field(default_factory=dict, description="unit_id -> scheduler urgency multiplier")
    reset_units: list[str] = Field(default_factory=list, description="units with part_replaced (restart their life)")


# ---------------------------------------------------------------------------------------------
# 2. HTTP shapes (contract section 4.3). Ebube's API returns these; David's types mirror them.
# ---------------------------------------------------------------------------------------------
class Rul(_Model):
    low: float
    likely: float
    high: float


class FleetUnit(_Model):
    unit_id: str
    station_code: str
    station: str
    risk_status: RiskStatus
    sensor_issue: bool
    display_status: DisplayStatus
    rul: Rul
    p_fail: float
    confidence: Confidence
    reason: str
    top_sensors: list[str]
    next_service_day: int | None
    needs_manager_decision: bool
    failed: bool
    data_source: DataSource
    model_version: str


def display_status(risk_status: RiskStatus, sensor_issue: bool) -> DisplayStatus:
    """D1: a real risk is never hidden behind a sensor fault."""
    if sensor_issue and risk_status != "at_risk":
        return "sensor_issue"
    return risk_status


class EventMsg(_Model):
    event_id: int
    type: EventType
    sim_day: int
    unit_id: str | None
    title: str
    detail: str
    severity: Severity
    payload: dict = Field(default_factory=dict)


class EventDraft(_Model):
    """An event the engine wants written (the database assigns event_id)."""
    type: EventType
    sim_day: int
    unit_id: str | None
    title: str
    detail: str
    severity: Severity = "info"
    payload: dict = Field(default_factory=dict)


class SimulateRequest(_Model):
    crews_per_station: int = 2
    cost_breakdown: float = 200_000
    cost_service: float = 20_000
    threshold: float | None = None
    horizon_days: int | None = None


class PolicyResult(BaseModel):
    policy: Policy
    breakdowns: int
    planned_services: int
    wasted_services: int
    crew_days: int
    total_cost: float
    operating_days: int = 0
    cost_per_operating_day: float = 0.0


class TuneSetting(BaseModel):
    threshold: float
    horizon_days: int
    total_cost: float
    detected: int | None = Field(default=None, description="failures confirmed at risk >= 14 days early (headline frame)")
    actioned: int | None = None
    total: int | None = None
    meets_service_level: bool | None = None


class Headline(BaseModel):
    detected: int
    actioned: int
    total: int
    lead_days: int
    text: str
    false_alarms: int = 0
    false_alarm_days: int = 60
    lead_time_p10: float | None = None
    lead_time_median: float | None = None
    lead_time_p90: float | None = None
    definition: str = ""


class SimulateResponse(BaseModel):
    policies: list[PolicyResult]
    default: TuneSetting
    tuned: TuneSetting
    headline: Headline
    computed_ms: float
    assumptions: list[str] = Field(default_factory=list)


class RingEvent(_Model):
    type: Literal["ring"] = "ring"
    call_request_id: int
    unit_id: str
    station_name: str
    technician_id: int
    technician_name: str
    language: Language
    rul_low: float
    rul_high: float
    reason: str
    expires_at: str


class AnswerResponse(_Model):
    signed_url: str
    language: Language
    dynamic_variables: dict[str, str]
