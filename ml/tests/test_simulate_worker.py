"""Simulation (speed, determinism, costs, same scheduler as live), explanation, the engine worker, and the
demo scenario window."""
import json
import time

import numpy as np
import pandas as pd
import pytest

from core.contracts import Capacity, PlanParams, PlanUnit, SimulateRequest
from core.explain import NO_DRIFT, TOO_EARLY, explain
from core.risk import STATUS_NAMES
from core.scheduler import build_plan
from core.sensors import LABELS, SENSORS
from core.simulate import _priority, _service_today, build_sim_data, run_policies, simulate_year
from ml.data_io import ARTIFACTS, ROOT

REQ = SimulateRequest(crews_per_station=2, cost_breakdown=200_000, cost_service=20_000)


@pytest.fixture(scope="module")
def tuned():
    meta = json.loads((ARTIFACTS / "metadata.json").read_text())
    return meta.get("tuned", {"threshold": 0.5, "horizon_days": 14})


def test_simulation_under_one_second_and_deterministic(oof, tuned):
    run_policies(oof, None, REQ, tuned)                       # warm-up: builds the arrays once per process
    t0 = time.perf_counter()
    a = run_policies(oof, None, REQ, tuned)
    assert time.perf_counter() - t0 < 1.0
    b = run_policies(oof, None, REQ, tuned)
    assert a.model_dump(exclude={"computed_ms"}) == b.model_dump(exclude={"computed_ms"})
    assert [p.policy for p in a.policies] == ["run_to_failure", "fixed_schedule", "pipeguard"]


def test_costs_add_up(oof, tuned):
    r = run_policies(oof, None, REQ, tuned)
    for p in r.policies:
        assert p.total_cost == p.breakdowns * REQ.cost_breakdown + p.planned_services * REQ.cost_service
        assert p.crew_days == p.planned_services and p.wasted_services <= p.planned_services
    rtf = r.policies[0]
    assert rtf.planned_services == 0 and rtf.breakdowns > 0
    assert r.headline.actioned <= r.headline.detected <= r.headline.total == 100
    assert str(r.headline.actioned) in r.headline.text


def test_sliders_move_the_result(oof, tuned):
    none = run_policies(oof, None, {**REQ.model_dump(), "crews_per_station": 0}, tuned)
    assert none.policies[2].planned_services == 0 and none.policies[2].breakdowns == none.policies[0].breakdowns
    cheap = run_policies(oof, None, {**REQ.model_dump(), "cost_breakdown": 100_000}, tuned)
    assert cheap.policies[0].total_cost < run_policies(oof, None, REQ, tuned).policies[0].total_cost


def test_same_scheduler_as_live(oof):
    """The simulation's 'serviced today' equals what build_plan books for today."""
    data = build_sim_data(oof)
    rng = np.random.default_rng(3)
    for _ in range(20):
        cand = rng.choice(100, size=12, replace=False)
        p = rng.uniform(0.3, 1.0, 100)
        saving = p * 200_000 - 20_000
        sim = set(_service_today(_priority(cand, saving, data), data, 1, 50).tolist())
        units = [PlanUnit(unit_id=data.unit_ids[i], station_code=data.unit_ids[i][:3], p_fail=float(p[i]),
                          risk_status="at_risk", rul_low=30.0) for i in cand]
        plan = build_plan(units, Capacity(crews_per_station=1), [], PlanParams(), today=50)
        live = {data.unit_ids.index(it.unit_id) for it in plan.items if it.planned_day == 50}
        assert sim == live


def test_held_out_tuning_recorded():
    meta = json.loads((ARTIFACTS / "metadata.json").read_text())
    if "tuning" not in meta:
        pytest.skip("run python -m ml.tune first")
    h = meta["tuning"]["held_out"]
    assert h["tuned_on_held_out"]["total"] == 40 and h["default_on_held_out"]["total"] == 40


# ---- explanation ------------------------------------------------------------------------------
def test_explanation_rules(cfg, train_df):
    g = train_df[train_df["unit"] == 20][SENSORS].to_numpy(dtype=float)
    late = explain(g, cfg)
    assert late.reason != NO_DRIFT and late.reason == explain(g, cfg).reason          # deterministic
    assert not any(s in late.reason.split() for s in SENSORS)                        # no raw column names
    assert any(late.reason.startswith(LABELS[s]) for s in SENSORS)
    assert explain(g[:5], cfg).reason == TOO_EARLY
    assert explain(g[:40], cfg).reason in (NO_DRIFT,) or "rising" in explain(g[:40], cfg).reason or "falling" in explain(g[:40], cfg).reason
    top = late.top_sensors[0]
    masked = explain(g, cfg, masked_sensors=[top])
    assert top not in masked.top_sensors                                               # masked sensors excluded


def test_wear_direction_learned_from_data(cfg):
    wd = cfg["wear_direction"]
    assert all(wd[s] == 1 for s in ("s3", "s4", "s11")) and all(wd[s] == -1 for s in ("s7", "s12", "s20", "s21"))


# ---- engine worker (in-memory store) --------------------------------------------------------------
def _fleet(train_df, engines_offsets, days):
    from core.contracts import unit_id_for_engine, station_of
    from engine.pipeline import UnitInfo
    units, rows = [], []
    for e, o in engines_offsets:
        uid = unit_id_for_engine(e)
        units.append(UnitInfo(unit_id=uid, station_code=station_of(uid), source_engine=e, life_start_day=1 - o))
        g = train_df[train_df["unit"] == e]
        for c, v in zip(g["cycle"], g[SENSORS].to_numpy(dtype=float)):
            d = int(c) - o
            if d <= days:
                rows.append({"unit_id": uid, "sim_day": d, **dict(zip(SENSORS, v))})
    return units, pd.DataFrame(rows)


def test_worker_idempotent_coalescing_and_epoch(predictor, train_df):
    from engine.store import MemoryStore
    from engine.worker import Engine
    units, readings = _fleet(train_df, [(81, 190), (5, 60), (12, 30)], days=40)
    store = MemoryStore(units, readings, threshold=0.5, horizon=14, sim_day=0)
    eng = Engine(store, predictor)
    for d in range(0, 31):
        store.state.sim_day = d
        assert eng.poll() == d
    n_pred, n_events = len(store.predictions), len(store.events)
    assert eng.poll() is None                                   # nothing new
    eng.tick(30)                                                # re-process the same day
    assert len(store.predictions) == n_pred and len(store.events) == n_events
    store.state.sim_day = 36                                    # behind: jump straight to the newest day
    assert eng.poll() == 36 and (units[0].unit_id, 33) not in store.predictions
    statuses = {e.payload.get("to") for e in store.events if e.type == "status_change" and e.unit_id == "DRH-01"}
    assert "at_risk" in statuses                                 # the demo's first red unit turns red
    assert any(e.type == "plan_changed" for e in store.events)
    # restart: a fresh engine on the same store restores status and writes no duplicate events
    eng2 = Engine(store, predictor)
    eng2.tick(36)
    assert len(store.events) == len([e for e in store.events])  # sanity
    dup = [e for e in store.events if e.type == "status_change" and e.sim_day == 36]
    assert len(dup) == len({(e.unit_id, e.payload["to"]) for e in dup})
    # epoch change clears memory
    store.state.epoch += 1
    store.state.sim_day = 37
    eng.poll()
    assert eng.epoch == store.state.epoch


def test_worker_sensor_issue_no_duplicate_events(predictor, train_df):
    from engine.store import MemoryStore
    from engine.worker import Engine
    units, readings = _fleet(train_df, [(7, 40)], days=20)
    readings.loc[readings["sim_day"] >= 5, "s9"] = np.nan        # sensor dies on day 5
    store = MemoryStore(units, readings, sim_day=0)
    eng = Engine(store, predictor)
    for d in range(0, 21):
        store.state.sim_day = d
        eng.poll()
    issues = [e for e in store.events if e.type == "sensor_issue"]
    assert len(issues) == 1 and "core speed" in issues[0].detail.lower()
    assert len(store.flags) == 1
    last = store.predictions[(units[0].unit_id, 20)]
    assert last.sensor_issue and last.confidence == "low" and last.display_status in ("sensor_issue", "at_risk")


def test_worker_whole_fleet_fallback(predictor, train_df, monkeypatch):
    from engine.store import MemoryStore
    from engine.worker import Engine
    units, readings = _fleet(train_df, [(5, 60), (12, 30)], days=5)
    store = MemoryStore(units, readings, sim_day=3)
    eng = Engine(store, predictor)
    monkeypatch.setattr(eng.pipeline, "process_day", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    eng.poll()
    rows = [p for (u, d), p in store.predictions.items() if d == 3]
    assert len(rows) == 2 and all(r.data_source == "fallback" for r in rows)
    assert sum(e.type == "manager_alert" for e in store.events) == 1


# ---- scenario ---------------------------------------------------------------------------------------
def test_scenario_red_unit_in_window_across_thresholds(predictor):
    from ml.make_scenario import MAX_DAY, MIN_DAY, replay
    scen = json.loads((ROOT / "infra" / "scenario.json").read_text())
    moments = json.loads((ARTIFACTS / "demo_moments.json").read_text())
    horizon = moments["horizon_days"]
    assert len(scen["units"]) == 100 and len({u["source_engine"] for u in scen["units"]}) == 100
    for thr in (0.3, 0.45, 0.6):
        first, _ = replay(scen, predictor, thr, horizon, days=MAX_DAY + 1)
        day = min(first.values())
        assert MIN_DAY <= day <= MAX_DAY, (thr, first)
        assert moments["first_red"]["unit_id"] in [u for u, d in first.items() if d == day]
