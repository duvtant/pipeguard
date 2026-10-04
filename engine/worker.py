"""Engine worker. Owner: Olise. Spec: techstack section 4.3, Olise guide section 12 (engine worker).

Listens for `new_day`, then for the NEWEST sim_day: quality checks, features, prediction, risk, status,
explanation (engine/pipeline.py), then the plan (core/scheduler.py), events, and the alert hook.

Guarantees
  - Idempotent: predictions upsert on (unit_id, sim_day); flag episodes upsert on (unit, sensor, type,
    start day) and only NEW episodes produce an event; status is restored from stored predictions, so
    re-processing a day writes no duplicate status event; an unchanged plan writes no plan event.
  - Never falls behind: always processes the latest day and skips the middle (coalescing).
  - Isolated failures: the predictor isolates each unit; if the whole live path fails, the tick switches
    to the precomputed fallback (data_source = "fallback") and logs one event.
  - Epoch: a changed sim_state.epoch (demo reset) drops all in-memory per-unit state.
  - Catch-up: after a (re)connect it reads every reading newer than what it holds.
  - Unit life: a new life_start_day resets that unit's history, status and hysteresis.

Run:  python -m engine.worker    (DATABASE_URL, MODEL_DIR, SCENARIO_PATH from the environment)
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from core.contracts import EventDraft, PlanParams, StatusState
from core.explain import explain_batch
from core.feedback import urgency_multipliers
from core.predict import OofFallback, Predictor
from core.risk import classify, p_fail
from core.scheduler import build_plan, plan_units_from_rows
from core.sensors import SENSORS
from engine.pipeline import DayResult, FleetPipeline, UnitDayResult, plan_event
from engine.store import PredictionRow, Store

log = logging.getLogger("engine")

COST_BREAKDOWN = float(os.environ.get("COST_BREAKDOWN", 200_000))
COST_SERVICE = float(os.environ.get("COST_SERVICE", 20_000))


def day_namer(scenario_path: str | os.PathLike | None):
    """sim_day -> 'Friday (day 35)' on the simulated calendar (calendar_start = sim_day 0)."""
    start = None
    try:
        if scenario_path and Path(scenario_path).exists():
            start = date.fromisoformat(json.loads(Path(scenario_path).read_text())["calendar_start"])
    except Exception:  # noqa: BLE001
        start = None

    def name(d: int) -> str:
        return f"{(start + timedelta(days=int(d))).strftime('%A')} (day {d})" if start else f"day {d}"
    return name


class Engine:
    def __init__(self, store: Store, predictor: Predictor, day_name=lambda d: f"day {d}"):
        self.store = store
        self.predictor = predictor
        self.pipeline = FleetPipeline(predictor)
        self.fallback = OofFallback.from_dir(predictor.model_dir)
        self.day_name = day_name
        self.epoch: int | None = None
        self.last_done: int | None = None
        self.held_until: int | None = None        # newest sim_day of readings already loaded
        self.fallback_announced = False

    # ---- state ---------------------------------------------------------------------------------
    def _reset(self, epoch: int) -> None:
        log.info("epoch %s: clearing in-memory state", epoch)
        self.pipeline.reset()
        self.epoch, self.last_done, self.held_until = epoch, None, None
        self.fallback_announced = False

    def _load_readings(self, units, upto_day: int) -> None:
        """Catch up: load every reading newer than what is held (all history on a fresh start)."""
        by_id = {u.unit_id: u for u in units}
        restarted = [u for u in units if self.pipeline.units.get(u.unit_id) is None
                     or self.pipeline.units[u.unit_id].life_start_day != u.life_start_day]
        after = (min(u.life_start_day for u in units) - 1) if (self.held_until is None or restarted) else self.held_until
        if restarted and self.held_until is not None:
            after = min([self.held_until] + [u.life_start_day - 1 for u in restarted])
        rows = self.store.get_readings(after, upto_day)
        for uid, g in rows.groupby("unit_id", sort=False):
            u = by_id.get(uid)
            if u is None:
                continue
            g = g[g["sim_day"] >= u.life_start_day].sort_values("sim_day")
            self.pipeline.add_readings(uid, u.life_start_day, g["sim_day"].to_numpy(), g[SENSORS].to_numpy(dtype=np.float64))
        for u in restarted:
            self._restore_status(u, upto_day)
        self.held_until = upto_day

    def _restore_status(self, u, before_day: int) -> None:
        """Rebuild status + hysteresis counters from this life's stored predictions (restart safety)."""
        thr, _ = self.store.get_engine_params()
        st = StatusState()
        for p in self.store.get_prediction_history(u.unit_id, u.life_start_day, before_day):
            st = classify(p.p_fail_h, thr, st, reliable=p.confidence == "normal")
        self.pipeline.set_status(u.unit_id, st)

    # ---- one tick ------------------------------------------------------------------------------
    def poll(self) -> int | None:
        """Process the newest day if there is one. Returns the processed day or None."""
        state = self.store.get_sim_state()
        if self.epoch != state.epoch:
            self._reset(state.epoch)
        if self.last_done is not None and state.sim_day <= self.last_done:
            return None
        self.tick(state.sim_day)
        return state.sim_day

    def tick(self, sim_day: int) -> DayResult:
        t0 = time.perf_counter()
        units = self.store.get_units()
        threshold, horizon = self.store.get_engine_params()
        self._load_readings(units, sim_day)
        try:
            res = self.pipeline.process_day(sim_day, units, threshold, horizon)
        except Exception:  # noqa: BLE001 - live path failed as a whole: fall back, keep the fleet going
            log.exception("live inference failed on day %s; using fallback predictions", sim_day)
            res = self._fallback_day(sim_day, units, threshold, horizon)

        rows = [self._row(r) for r in res.units]
        self.store.upsert_predictions(rows)
        created, resolved = self.store.upsert_quality_flags(res.flags)
        keys = lambda fs: {(f.unit_id, f.sensor, f.flag_type, f.sim_day) for f in fs}  # noqa: E731
        new_flags, new_resolved = keys(created), keys(resolved)
        events = [e for e in res.events if e.type != "sensor_issue" or self._is_new_flag_event(e, new_flags, new_resolved)]
        if any(r.prediction.data_source == "fallback" for r in res.units) and not self.fallback_announced:
            self.fallback_announced = True
            events.append(EventDraft(type="manager_alert", sim_day=sim_day, unit_id=None, title="Backup predictions in use",
                                     detail="The live model could not score some units; their numbers come from the "
                                            "precomputed backup until it recovers.", severity="warning"))

        plan = self._replan(sim_day, units, res, horizon)
        ev = plan_event(plan.changes, sim_day, self.day_name) if plan.changed else None
        if ev:
            events.append(ev)
        if events:
            self.store.write_events(events)
        self.store.after_tick(sim_day)
        self.last_done = sim_day
        log.info("tick day=%s units=%d events=%d model=%s took=%.0fms", sim_day, len(res.units), len(events),
                 self.predictor.model_version, (time.perf_counter() - t0) * 1000)
        return res

    @staticmethod
    def _is_new_flag_event(e: EventDraft, new_flags: set, new_resolved: set) -> bool:
        """Only episodes the database had not seen (or not seen resolved) produce an event: idempotent."""
        key = (e.unit_id, e.payload.get("sensor"), e.payload.get("flag_type"), e.payload.get("start_day"))
        return key in (new_resolved if "resolved_day" in e.payload else new_flags)

    def _row(self, r: UnitDayResult) -> PredictionRow:
        p = r.prediction
        return PredictionRow(unit_id=r.unit_id, sim_day=r.sim_day, rul_low=p.rul_low, rul_likely=p.rul_likely,
                             rul_high=p.rul_high, p_fail_h=r.p_fail, confidence=p.confidence, status=r.status,
                             reason=r.explanation.reason, model_version=p.model_version, data_source=p.data_source,
                             top_sensors=r.explanation.top_sensors, sensor_issue=r.sensor_issue,
                             display_status=r.display_status)

    def _replan(self, sim_day: int, units, res: DayResult, horizon: int):
        urgency = urgency_multipliers(self.store.get_verdicts(), sim_day)
        rows = [{"unit_id": r.unit_id, "p_fail_h": r.p_fail, "status": r.status, "rul_low": r.prediction.rul_low}
                for r in res.units]
        plan_units = plan_units_from_rows(rows, {u.unit_id for u in units if u.failed}, urgency)
        capacity = self.store.get_capacity()
        constraints = self.store.get_constraints(sim_day)
        params = PlanParams(cost_breakdown=COST_BREAKDOWN, cost_service=COST_SERVICE)
        return self.store.replan(lambda previous: build_plan(plan_units, capacity, constraints, params, sim_day,
                                                             previous, horizon_days=horizon), sim_day)

    def _fallback_day(self, sim_day: int, units, threshold: float, horizon: int) -> DayResult:
        """Whole-fleet fallback: precomputed cross-fitted ranges by (engine, cycle), same risk and status."""
        from core.contracts import Explanation, Prediction, display_status
        out = []
        live = [(u, self.pipeline.units.get(u.unit_id)) for u in units if not u.failed]
        live = [(u, m) for u, m in live if m and m.days and m.days[-1] == sim_day]
        try:
            exps = explain_batch([m.history()[0] for _, m in live], self.predictor.cfg)
        except Exception:  # noqa: BLE001
            exps = [Explanation(reason="Backup prediction in use", top_sensors=[]) for _ in live]
        for (u, mem), ex in zip(live, exps):
            cyc = sim_day - u.life_start_day + 1
            lo, li, hi = self.fallback(u.source_engine, cyc)
            pred = Prediction(unit_id=u.unit_id, sim_day=sim_day, rul_low=lo, rul_likely=li, rul_high=hi, confidence="low",
                              data_source="fallback", model_version=self.predictor.model_version)
            pf = float(p_fail(lo, li, hi, horizon))
            prev = mem.status
            mem.status = classify(pf, threshold, prev, reliable=False)
            out.append(UnitDayResult(unit_id=u.unit_id, station_code=u.station_code, sim_day=sim_day, prediction=pred,
                                     p_fail=pf, status=mem.status.status, previous_status=prev.status, explanation=ex,
                                     sensor_issue=False, display_status=display_status(mem.status.status, False), cycle=cyc))
        return DayResult(sim_day, out, [], [])


# ---------------------------------------------------------------------------------------------
def main() -> None:  # pragma: no cover - needs PostgreSQL
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    from engine.pg_store import PgStore  # imported here so tests do not need psycopg

    model_dir = os.environ.get("MODEL_DIR", str(Path(__file__).resolve().parents[1] / "ml" / "artifacts"))
    predictor = Predictor(model_dir)
    store = PgStore(os.environ["DATABASE_URL"])
    engine = Engine(store, predictor, day_namer(os.environ.get("SCENARIO_PATH")))
    log.info("engine started, model %s", predictor.model_version)
    backoff = 1.0
    while True:
        try:
            with store.listener("new_day") as wait:
                backoff = 1.0
                engine.poll()                          # catch up on (re)connect
                while True:
                    wait(timeout=1.0)                  # a notification or a 1 s poll, whichever first
                    engine.poll()                      # always the newest day: coalesces a backlog
        except Exception:  # noqa: BLE001
            log.exception("engine loop error; reconnecting in %.0fs", backoff)
            time.sleep(backoff)
            backoff = min(backoff * 2, 30.0)


if __name__ == "__main__":
    main()
