"""Writes infra/scenario.json so a unit turns red between 20 and 40 s at default speed.

Owner: Olise. Spec: Olise guide section 12, techstack sections 5.4 and 8, contract D4.

D4: the scenario only chooses WHERE each unit's replay starts (start_offset). Sensor values are never
edited or invented. On sim_day d a unit reads NASA cycle start_offset + d of its source engine; cycles
1..start_offset are backfilled at sim_day <= 0 (life_start_day = 1 - start_offset).

Steps
  1. Fast search on the cross-fitted predictions: for every unit and candidate offset, the day the unit
     would first be confirmed at_risk if the engine started watching it on day 0 (fresh status), for
     thresholds 0.30 .. 0.60.
  2. First red unit: crosses inside [MIN_DAY, MAX_DAY] at every threshold, with about 20 to 35 days of
     true life left at the crossing.
  3. A handful of units turn red later at staggered days; the rest start younger so they stay quiet for
     the first minutes; never more than MAX_PER_DAY crossings on one day.
  4. A planted stuck sensor on a different, healthy unit shortly after the first red day.
  5. Validation with the REAL live code path (engine.pipeline.FleetPipeline: quality checks, features,
     fold models, p_fail, status) replayed day by day with no wall clock, at every threshold.
Also writes ml/artifacts/fallback/ (precomputed predictions for every unit and scenario day) and
ml/artifacts/demo_moments.json.

Run:  python -m ml.make_scenario
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from core.contracts import STATIONS, station_of, unit_id_for_engine
from core.predict import LOW_HISTORY, Predictor
from core.risk import AT_RISK, HEALTHY, classify_step, p_fail
from core.sensors import SENSORS, label
from engine.pipeline import FleetPipeline, UnitInfo
from ml.data_io import ARTIFACTS, ROOT, load_train

SEED = 42
SCENARIO_ID = "demo_v1"
CALENDAR_START = "2026-10-05"           # a Monday
SPEED = 1.0
THRESHOLDS = (0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60)
MIN_DAY, MAX_DAY = 20, 40               # requirement window (replay seconds at 1 s/day)
TARGET_DAY = 29                         # aim the first crossing here so all thresholds fit the window
FIRST_RUL = (20, 35)                    # true days left when the first unit goes red (threshold 0.5)
QUIET_UNTIL = 45                        # no other unit goes red before this day, at any threshold
LATER_RED_DAYS = (52, 64, 78, 92, 108, 124, 142, 160)   # the handful that keeps the dashboard moving
REST_QUIET_UNTIL = 175
MIN_ALIVE = 60                          # every unit keeps running at least this many days into the demo
MAX_PER_DAY = 2
SEARCH_DAYS = 220
FAULT = {"sensor": "s4", "type": "stuck", "delay": 4}   # planted fault, days after the first red day
SCENARIO_PATH = ROOT / "infra" / "scenario.json"


# ---------------------------------------------------------------------------------------------
def crossing_days(P: np.ndarray, max_cycle: np.ndarray, thr: float, days: int = SEARCH_DAYS) -> np.ndarray:
    """(U, C) first day each (unit, offset) is confirmed at_risk, starting fresh on day 0. -1 = never.

    P: (U, T) p_fail by cycle (column c-1 = cycle c). Offset o means day d reads cycle o + d.
    """
    U, T = P.shape
    offsets = np.arange(1, T + 1)
    out = np.full((U, T), -1)
    status = np.zeros((U, T), dtype=np.int64)
    above = np.zeros((U, T), dtype=np.int64)
    below = np.zeros((U, T), dtype=np.int64)
    for d in range(days):
        cyc = offsets[None, :] + d                                   # (1, C)
        alive = cyc <= max_cycle[:, None]
        col = np.minimum(cyc - 1, T - 1)
        p = np.nan_to_num(np.take_along_axis(P, np.broadcast_to(col, (U, T)), axis=1))
        rel = np.broadcast_to(cyc >= LOW_HISTORY, (U, T))
        s2, a2, b2 = classify_step(p, thr, status, above, below, rel)
        status, above, below = np.where(alive, s2, status), np.where(alive, a2, above), np.where(alive, b2, below)
        new = alive & (status == AT_RISK) & (out < 0)
        out[new] = d
    return out


def healthy_days(P: np.ndarray, u: int, o: int, days: int) -> bool:
    """True if unit u started at offset o stays below the watch floor for `days` days."""
    seg = P[u, o - 1:o - 1 + days]
    return bool(np.all(np.nan_to_num(seg, nan=0.0) < 0.10))


def choose_offsets(oof: pd.DataFrame, horizon: int, seed: int = SEED):
    rng = np.random.default_rng(seed)
    df = oof.sort_values(["source_engine", "cycle"])
    engines = np.sort(df["source_engine"].unique())
    U, T = len(engines), int(df["cycle"].max())
    lo = np.full((U, T), np.nan); mid = lo.copy(); hi = lo.copy()
    r = np.searchsorted(engines, df["source_engine"].to_numpy()); c = df["cycle"].to_numpy() - 1
    lo[r, c], mid[r, c], hi[r, c] = df["rul_low"], df["rul_likely"], df["rul_high"]
    max_cycle = df.groupby("source_engine")["cycle"].max().reindex(engines).to_numpy()
    with np.errstate(invalid="ignore"):
        P = p_fail(lo, mid, hi, horizon)
    X = {thr: crossing_days(P, max_cycle, thr) for thr in THRESHOLDS}   # (U, C) per threshold
    Xs = np.stack([X[t] for t in THRESHOLDS])                          # (K, U, C)
    never = np.where(Xs < 0, 10_000, Xs)
    earliest = never.min(axis=0)                                       # earliest crossing over thresholds
    latest = Xs.max(axis=0)
    all_cross = (Xs >= 0).all(axis=0)
    x50 = X[0.50]
    offs = np.arange(1, T + 1)

    # ---- first red unit -------------------------------------------------------------------------
    best = None
    for u in range(U):
        for ci in range(T):
            o = offs[ci]
            if not all_cross[u, ci] or earliest[u, ci] < MIN_DAY + 2 or latest[u, ci] > MAX_DAY - 2:
                continue
            rul_at = max_cycle[u] - (o + x50[u, ci])
            if not FIRST_RUL[0] <= rul_at <= FIRST_RUL[1]:
                continue
            score = (abs(x50[u, ci] - TARGET_DAY) + (latest[u, ci] - earliest[u, ci]), abs(rul_at - 27), u)
            if best is None or score < best[0]:
                best = (score, u, ci)
    if best is None:
        raise RuntimeError("no unit fits the 20-40 s window at every threshold; widen the search")
    _, ue, ce = best
    offsets = {ue: int(offs[ce])}
    cross50 = {ue: int(x50[ue, ce])}

    # ---- later red units (staggered) and the quiet rest ----------------------------------------------
    per_day: dict[int, int] = {cross50[ue]: 1}
    order = list(rng.permutation([u for u in range(U) if u != ue]))
    later: list[int] = []
    for target in LATER_RED_DAYS:
        pick = None
        for u in order:
            if u in offsets:
                continue
            ok = np.flatnonzero((earliest[u] >= QUIET_UNTIL) & (np.abs(x50[u] - target) <= 1) & (x50[u] >= 0))
            if len(ok):
                ci = int(ok[np.argmin(np.abs(x50[u, ok] - target))])
                pick = (u, ci)
                break
        if pick:
            u, ci = pick
            offsets[u] = int(offs[ci]); cross50[u] = int(x50[u, ci]); later.append(u)
            per_day[cross50[u]] = per_day.get(cross50[u], 0) + 1

    for u in order:
        if u in offsets:
            continue
        ok = np.flatnonzero((earliest[u] >= REST_QUIET_UNTIL) & (offs <= max_cycle[u] - REST_QUIET_UNTIL))
        if not len(ok):   # short-lived engine: quiet for the first minute and alive for MIN_ALIVE days
            ok = np.flatnonzero((earliest[u] >= QUIET_UNTIL) & (offs <= max_cycle[u] - MIN_ALIVE))
        if not len(ok):
            ok = np.array([0])
        rng.shuffle(ok)
        for ci in ok:
            d = int(x50[u, ci])
            if d < 0 or per_day.get(d, 0) < MAX_PER_DAY:
                offsets[u] = int(offs[ci]); cross50[u] = d
                if d >= 0:
                    per_day[d] = per_day.get(d, 0) + 1
                break
        else:
            offsets[u] = int(offs[ok[0]])
            cross50[u] = int(x50[u, offsets[u] - 1])

    # ---- planted fault on a healthy unit at another station if possible ---------------------------
    fault_day = cross50[ue] + FAULT["delay"]
    fault_u = None
    for u in sorted(range(U), key=lambda u: (station_of(unit_id_for_engine(engines[u])) == station_of(unit_id_for_engine(engines[ue])), u)):
        if u == ue or u in later:
            continue
        if healthy_days(P, u, offsets[u], fault_day + 30):
            fault_u = u
            break
    return dict(engines=engines, max_cycle=max_cycle, offsets=offsets, first=ue, later=later, fault_unit=fault_u,
                fault_day=fault_day, cross50=cross50, crossings={t: {u: int(X[t][u, offsets[u] - 1]) for u in range(U)} for t in THRESHOLDS})


# ---------------------------------------------------------------------------------------------
def scenario_from(choice: dict) -> dict:
    engines = choice["engines"]
    units = [{"unit_id": unit_id_for_engine(int(engines[u])), "source_engine": int(engines[u]),
              "start_offset": int(choice["offsets"][u])} for u in range(len(engines))]
    faults = []
    if choice["fault_unit"] is not None:
        faults.append({"unit_id": unit_id_for_engine(int(engines[choice["fault_unit"]])), "sensor": FAULT["sensor"],
                       "type": FAULT["type"], "start_day": int(choice["fault_day"])})
    return {"scenario_id": SCENARIO_ID, "seed": SEED, "calendar_start": CALENDAR_START,
            "units": units, "planted_faults": faults, "speed_seconds_per_day": SPEED}


def replay(scenario: dict, predictor: Predictor, threshold: float, horizon: int, days: int,
           train: pd.DataFrame | None = None, with_explain: bool = False):
    """Fast replay of the live code path (no database, no clock). Emulates the simulator's readings:
    backfill cycles 1..start_offset, then cycle start_offset + d on day d, planted faults applied.
    Returns (first_at_risk_day per unit, per-day results)."""
    train = load_train() if train is None else train
    by_engine = {e: g[SENSORS].to_numpy(dtype=np.float64) for e, g in train.groupby("unit")}
    faults = {(f["unit_id"]): f for f in scenario.get("planted_faults", [])}
    pipe = FleetPipeline(predictor)
    infos: list[UnitInfo] = []
    for u in scenario["units"]:
        o = u["start_offset"]
        info = UnitInfo(unit_id=u["unit_id"], station_code=station_of(u["unit_id"]), source_engine=u["source_engine"],
                        life_start_day=1 - o)
        infos.append(info)
        rows = by_engine[u["source_engine"]][:o]
        pipe.add_readings(info.unit_id, info.life_start_day, np.arange(1 - o, 1), rows)
    first: dict[str, int] = {}
    results = []
    last_good: dict[str, float] = {}
    for d in range(0, days + 1):
        for info, u in zip(infos, scenario["units"]):
            cyc = u["start_offset"] + d
            data = by_engine[u["source_engine"]]
            if d == 0:
                continue                       # day 0 is the last backfilled reading
            if cyc > len(data):
                info.failed = True
                continue
            row = data[cyc - 1].copy()
            f = faults.get(info.unit_id)
            if f and d >= f["start_day"]:     # techstack section 8 fault behaviours
                j = SENSORS.index(f["sensor"])
                q = predictor.cfg["quality"][f["sensor"]]
                if f["type"] == "dead":
                    row[j] = np.nan
                elif f["type"] == "stuck":
                    row[j] = last_good.setdefault(info.unit_id, data[cyc - 2, j])   # repeats the last good value
                elif f["type"] == "spike" and d == f["start_day"]:
                    row[j] += 10 * q["std"]
                elif f["type"] == "out_of_range":
                    row[j] = q["hi"] + 10 * q["std"]
            pipe.add_readings(info.unit_id, info.life_start_day, [d], row[None, :])
        res = pipe.process_day(d, infos, threshold, horizon, with_explain=with_explain)
        results.append(res)
        for r in res.units:
            if r.status == "at_risk" and r.unit_id not in first:
                first[r.unit_id] = d
    return first, results


def validate(scenario: dict, predictor: Predictor, horizon: int, days: int = 60) -> dict:
    train = load_train()
    report = {}
    for thr in THRESHOLDS:
        first, results = replay(scenario, predictor, thr, horizon, days, train)
        ordered = sorted(first.items(), key=lambda kv: (kv[1], kv[0]))
        first_day = ordered[0][1] if ordered else None
        report[f"{thr:.2f}"] = {"first_red": ordered[:3], "first_day": first_day,
                                "in_window": first_day is not None and MIN_DAY <= first_day <= MAX_DAY,
                                "red_by_day_60": len(first)}
        fault = scenario["planted_faults"][0] if scenario["planted_faults"] else None
        if fault:
            fu = fault["unit_id"]
            flagged = [r.sim_day for res in results for r in res.units if r.unit_id == fu and r.sensor_issue]
            report[f"{thr:.2f}"]["fault_flagged_day"] = flagged[0] if flagged else None
            report[f"{thr:.2f}"]["fault_unit_red"] = fu in first
    return report


def fallback_table(scenario: dict, oof: pd.DataFrame) -> pd.DataFrame:
    """Precomputed prediction for every unit and every scenario day (from the cross-fitted predictions)."""
    o = oof.set_index(["source_engine", "cycle"])
    rows = []
    for u in scenario["units"]:
        e, s = u["source_engine"], u["start_offset"]
        g = o.loc[e]
        for cyc in range(s, int(g.index.max()) + 1):
            p = g.loc[cyc]
            rows.append((u["unit_id"], e, cyc - s, cyc, float(p["rul_low"]), float(p["rul_likely"]), float(p["rul_high"]),
                         "low" if cyc < LOW_HISTORY else "normal"))
    return pd.DataFrame(rows, columns=["unit_id", "source_engine", "sim_day", "cycle", "rul_low", "rul_likely", "rul_high", "confidence"])


def tuned_horizon(model_dir: Path) -> tuple[float, int]:
    meta = json.loads((model_dir / "metadata.json").read_text()) if (model_dir / "metadata.json").exists() else {}
    t = meta.get("tuned") or {}
    return float(t.get("threshold", 0.5)), int(t.get("horizon_days", 14))


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate and validate infra/scenario.json")
    ap.add_argument("--horizon", type=int, default=None)
    ap.add_argument("--no-validate", action="store_true")
    args = ap.parse_args()
    oof = pd.read_parquet(ARTIFACTS / "oof_predictions.parquet")
    thr_t, hor_t = tuned_horizon(ARTIFACTS)
    horizon = args.horizon or hor_t
    choice = choose_offsets(oof, horizon)
    scen = scenario_from(choice)
    SCENARIO_PATH.write_text(json.dumps(scen, indent=1))
    (ARTIFACTS / "fallback").mkdir(exist_ok=True)
    fallback_table(scen, oof).to_parquet(ARTIFACTS / "fallback" / "fallback_predictions.parquet", index=False)

    e = choice["engines"]
    first_uid = unit_id_for_engine(int(e[choice["first"]]))
    ue = choice["first"]
    moments = {
        "scenario_id": SCENARIO_ID, "horizon_days": horizon, "tuned_threshold": thr_t,
        "first_red": {"unit_id": first_uid, "station_code": station_of(first_uid), "station": STATIONS[station_of(first_uid)],
                      "source_engine": int(e[ue]), "start_offset": choice["offsets"][ue],
                      "day_by_threshold": {f"{t:.2f}": choice["crossings"][t][ue] for t in THRESHOLDS},
                      "true_days_left_at_threshold_0.50": int(choice["max_cycle"][ue] - (choice["offsets"][ue] + choice["cross50"][ue]))},
        "later_red": [{"unit_id": unit_id_for_engine(int(e[u])), "day_at_threshold_0.50": choice["cross50"][u]} for u in choice["later"]],
        "planted_fault": scen["planted_faults"][0] if scen["planted_faults"] else None,
    }
    if moments["planted_fault"]:
        moments["planted_fault"]["sensor_label"] = label(FAULT["sensor"])
    if not args.no_validate:
        pred = Predictor(ARTIFACTS)
        rep = validate(scen, pred, horizon)
        moments["validation_live_replay"] = rep
        bad = [t for t, r in rep.items() if not r["in_window"]]
        print(json.dumps(rep, indent=1))
        if bad:
            raise SystemExit(f"first red unit outside {MIN_DAY}-{MAX_DAY} s at thresholds {bad}")
    (ARTIFACTS / "demo_moments.json").write_text(json.dumps(moments, indent=1))
    print(json.dumps({k: v for k, v in moments.items() if k != "validation_live_replay"}, indent=1))


if __name__ == "__main__":
    main()
