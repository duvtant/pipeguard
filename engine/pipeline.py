"""The live code path for one simulated day, without a database or a clock.

Owner: Olise. Spec: techstack section 4.3 steps 3-6, Olise guide sections 5, 7, 9, 12.

`FleetPipeline` keeps each unit's FULL current-life history in memory (the EWM has infinite memory, so a
truncated window would drift from training) and runs, for the newest day:
    quality checks -> features -> fold-model prediction -> p_fail -> status (with hysteresis) -> reason
It returns plain results plus the events to write. The DB worker (engine/worker.py) feeds it readings and
persists what it returns; ml/make_scenario.py and the tests drive it directly (fast replay). Same code.

Unit life: a unit's cycle on day d is d - life_start_day + 1, and only readings with
sim_day >= life_start_day count. When life_start_day changes (service / part_replaced), the unit's
history, status and hysteresis are reset.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from core.contracts import EventDraft, Explanation, Prediction, QualityFlag, StatusState, display_status
from core.explain import explain_batch
from core.features import feature_names, latest_features
from core.predict import Predictor
from core.quality import check_quality_arrays
from core.risk import classify, p_fail
from core.sensors import SENSORS, label

log = logging.getLogger(__name__)

FLAG_WORDS = {
    "sensor_offline": "stopped reporting",
    "sensor_stuck": "is stuck on one value",
    "sensor_spike": "sent an implausible jump",
    "sensor_out_of_range": "is reading outside its physical range",
}
STATUS_WORDS = {"healthy": "healthy", "watch": "on watch", "at_risk": "at risk"}


@dataclass
class UnitInfo:
    unit_id: str
    station_code: str
    source_engine: int
    life_start_day: int
    failed: bool = False


@dataclass
class UnitMemory:
    life_start_day: int
    days: list[int] = field(default_factory=list)
    values: list[np.ndarray] = field(default_factory=list)
    status: StatusState = field(default_factory=StatusState)
    announced_flags: set = field(default_factory=set)

    def history(self) -> tuple[np.ndarray, np.ndarray]:
        if not self.values:
            return np.zeros((0, len(SENSORS))), np.zeros(0, dtype=np.int64)
        return np.vstack(self.values), np.asarray(self.days, dtype=np.int64)


@dataclass
class UnitDayResult:
    unit_id: str
    station_code: str
    sim_day: int
    prediction: Prediction
    p_fail: float
    status: str
    previous_status: str
    explanation: Explanation
    sensor_issue: bool
    display_status: str
    cycle: int


@dataclass
class DayResult:
    sim_day: int
    units: list[UnitDayResult]
    flags: list[QualityFlag]
    events: list[EventDraft]


class FleetPipeline:
    def __init__(self, predictor: Predictor, sensors: list[str] = SENSORS):
        self.predictor = predictor
        self.cfg = predictor.cfg
        self.sensors = sensors
        self.fnames = predictor.features
        self.units: dict[str, UnitMemory] = {}

    # ---- state -------------------------------------------------------------------------------
    def reset(self) -> None:
        """Epoch change (demo reset): drop all per-unit state."""
        self.units.clear()

    def reset_unit(self, unit_id: str, life_start_day: int) -> None:
        self.units[unit_id] = UnitMemory(life_start_day=life_start_day)

    def _memory(self, unit_id: str, life_start_day: int) -> UnitMemory:
        mem = self.units.get(unit_id)
        if mem is None or mem.life_start_day != life_start_day:
            mem = UnitMemory(life_start_day=life_start_day)
            self.units[unit_id] = mem
        return mem

    def add_readings(self, unit_id: str, life_start_day: int, days, values) -> None:
        """Append raw readings (sim_day ascending). Days before life_start_day or already held are ignored."""
        mem = self._memory(unit_id, life_start_day)
        last = mem.days[-1] if mem.days else None
        vals = np.asarray(values, dtype=np.float64).reshape(-1, len(self.sensors))
        for d, v in zip(days, vals):
            d = int(d)
            if d < life_start_day or (last is not None and d <= last):
                continue
            mem.days.append(d)
            mem.values.append(v)
            last = d

    def last_day(self, unit_id: str) -> int | None:
        mem = self.units.get(unit_id)
        return mem.days[-1] if mem and mem.days else None

    def set_status(self, unit_id: str, state: StatusState) -> None:
        if unit_id in self.units:
            self.units[unit_id].status = state

    # ---- one day -----------------------------------------------------------------------------
    def process_day(self, sim_day: int, units: list[UnitInfo], threshold: float, horizon: int,
                    with_explain: bool = True) -> DayResult:
        live = []
        for u in units:
            mem = self._memory(u.unit_id, u.life_start_day)
            if not u.failed and mem.days and mem.days[-1] == sim_day:
                live.append((u, mem))
        if not live:
            return DayResult(sim_day, [], [], [])

        raws, days = zip(*(m.history() for _, m in live))
        ids = [u.unit_id for u, _ in live]
        q = check_quality_arrays(list(raws), list(days), ids, self.cfg, self.sensors)
        cycles = [int(sim_day - u.life_start_day + 1) for u, _ in live]
        F = latest_features(q.masked, cycles, self.sensors)
        feats = pd.DataFrame(F, columns=feature_names(self.sensors))
        feats.insert(0, "unit_id", ids)
        feats.insert(1, "source_engine", [u.source_engine for u, _ in live])
        feats.insert(2, "sim_day", sim_day)
        preds = self.predictor.predict(feats, q.masked_latest)
        lows = np.array([p.rul_low for p in preds])
        mids = np.array([p.rul_likely for p in preds])
        highs = np.array([p.rul_high for p in preds])
        pf = np.atleast_1d(p_fail(lows, mids, highs, horizon))
        if with_explain:
            exps = explain_batch(q.masked, self.cfg, [q.masked_latest.get(i, []) for i in ids], self.sensors)
        else:
            exps = [Explanation(reason="", top_sensors=[]) for _ in ids]

        events: list[EventDraft] = []
        results: list[UnitDayResult] = []
        flags_by_unit: dict[str, list[QualityFlag]] = {}
        for f in q.flags:
            flags_by_unit.setdefault(f.unit_id, []).append(f)
        for k, (u, mem) in enumerate(live):
            pred = preds[k]
            prev = mem.status
            new = classify(float(pf[k]), threshold, prev, reliable=pred.confidence == "normal")
            mem.status = new
            issue = bool(q.flagged_latest.get(u.unit_id))
            res = UnitDayResult(unit_id=u.unit_id, station_code=u.station_code, sim_day=sim_day, prediction=pred,
                                p_fail=float(pf[k]), status=new.status, previous_status=prev.status,
                                explanation=exps[k], sensor_issue=issue,
                                display_status=display_status(new.status, issue), cycle=cycles[k])
            results.append(res)
            if new.status != prev.status:
                events.append(status_event(res, horizon))
            for f in flags_by_unit.get(u.unit_id, []):
                key = (f.sensor, f.flag_type, f.sim_day)
                if key not in mem.announced_flags:
                    mem.announced_flags.add(key)
                    events.append(sensor_event(f, sim_day))
                if f.resolved_day is not None and (key + ("resolved",)) not in mem.announced_flags:
                    mem.announced_flags.add(key + ("resolved",))
                    events.append(sensor_resolved_event(f))
        return DayResult(sim_day, results, q.flags, events)


# ---- event text (written for a maintenance manager; David shows it as is) -----------------------
def _range_text(p: Prediction) -> str:
    return f"likely {p.rul_likely:.0f} days left (range {p.rul_low:.0f} to {p.rul_high:.0f})"


def status_event(r: UnitDayResult, horizon: int) -> EventDraft:
    sev = "critical" if r.status == "at_risk" else ("warning" if r.status == "watch" and r.previous_status == "healthy" else "info")
    if r.status == "at_risk":
        title = f"{r.unit_id} is at risk"
    elif r.previous_status == "at_risk":
        title = f"{r.unit_id} is no longer at risk"
    else:
        title = f"{r.unit_id} is now {STATUS_WORDS[r.status]}"
    detail = (f"{r.p_fail:.0%} chance of failure within {horizon} days; {_range_text(r.prediction)}. "
              f"{r.explanation.reason}.")
    if r.prediction.confidence == "low":
        detail += " Confidence is low (short history or a masked sensor)."
    return EventDraft(type="status_change", sim_day=r.sim_day, unit_id=r.unit_id, title=title, detail=detail,
                      severity=sev, payload={"from": r.previous_status, "to": r.status, "p_fail": round(r.p_fail, 4),
                                             "rul_low": r.prediction.rul_low, "rul_likely": r.prediction.rul_likely,
                                             "rul_high": r.prediction.rul_high})


def sensor_event(f: QualityFlag, sim_day: int) -> EventDraft:
    title = f"Instrument check: {f.unit_id}"
    detail = (f"The {label(f.sensor).lower()} sensor {FLAG_WORDS[f.flag_type]} (since day {f.sim_day}). "
              f"Its bad readings are ignored and the prediction continues with lower confidence. "
              f"Recommended action: instrument check, not a crew call.")
    return EventDraft(type="sensor_issue", sim_day=sim_day, unit_id=f.unit_id, title=title, detail=detail,
                      severity="warning", payload={"sensor": f.sensor, "flag_type": f.flag_type, "start_day": f.sim_day})


def sensor_resolved_event(f: QualityFlag) -> EventDraft:
    return EventDraft(type="sensor_issue", sim_day=int(f.resolved_day), unit_id=f.unit_id,
                      title=f"Sensor back to normal: {f.unit_id}",
                      detail=f"The {label(f.sensor).lower()} sensor has given 5 clean readings in a row; its flag is cleared.",
                      severity="info", payload={"sensor": f.sensor, "flag_type": f.flag_type, "start_day": f.sim_day,
                                                "resolved_day": f.resolved_day})


def plan_event(changes, sim_day: int, day_name=lambda d: f"day {d}") -> EventDraft | None:
    """One plan_changed event summarising a non-trivial diff (None if nothing changed)."""
    parts = []
    for c in changes:
        if c.kind == "added":
            parts.append(f"{c.unit_id} scheduled for {day_name(c.new_day)}")
        elif c.kind == "moved":
            parts.append(f"{c.unit_id} moved from {day_name(c.old_day)} to {day_name(c.new_day)}")
        elif c.kind == "removed":
            parts.append(f"{c.unit_id} removed from the plan")
    if not parts:
        return None
    return EventDraft(type="plan_changed", sim_day=sim_day, unit_id=None, title="Plan changed",
                      detail="; ".join(parts) + ".", severity="info",
                      payload={"changes": [c.model_dump() for c in changes if c.kind != "unchanged"]})
