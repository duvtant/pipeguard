"""Threshold and horizon search on cross-fitted predictions only.

Owner: Olise. Spec: Olise guide section 10 (self-tuning), techstack section 7.6.

Grid: threshold 0.2 .. 0.8 (step 0.1) x horizon 7, 14, 21 days, each scored by core.simulate (the same
p_fail, status and scheduler logic as the live engine) on the cross-fitted predictions. The choice is the
lowest yearly cost among settings that keep the D3 promise (>= 90% of failures confirmed at risk at least
14 days early); see core.simulate.tune_grid.

Honesty: tuning and reporting on the same 100 engines flatters the result. So this also tunes on the
engines of folds 0-2 only and reports default vs tuned on the unseen engines of folds 3-4. Both are
written to metadata.json; quote the held-out one if the gap is large. The demo fleet IS the NASA
training set: say so in the pitch.

Callable from the API:  ml.tune.run(...) -> dict with "threshold" and "horizon_days" for engine_params.
CLI:                    python -m ml.tune
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from core.contracts import SimulateRequest
from core.simulate import (DEFAULT_HORIZON, DEFAULT_THRESHOLD, SERVICE_LEVEL, build_sim_data, evaluate_setting, run_policies,
                           tune_grid)
from ml.data_io import ARTIFACTS

DEFAULTS = {"crews_per_station": 2, "cost_breakdown": 200_000.0, "cost_service": 20_000.0}


def run(oof: pd.DataFrame | None = None, crews_per_station: int = 2, cost_breakdown: float = 200_000.0,
        cost_service: float = 20_000.0, service_level: float = SERVICE_LEVEL, model_dir: Path = ARTIFACTS,
        write: bool = True) -> dict:
    oof = pd.read_parquet(model_dir / "oof_predictions.parquet") if oof is None else oof
    data = build_sim_data(oof)
    args = (crews_per_station, float(cost_breakdown), float(cost_service))

    grid = tune_grid(data, *args, service_level=service_level)
    best = grid[0]
    default = next(s for s in grid if s.threshold == DEFAULT_THRESHOLD and s.horizon_days == DEFAULT_HORIZON)

    # Held-out check: tune on folds 0-2, report on folds 3-4.
    folds = oof.groupby("source_engine")["fold"].first().reindex(data.engines).to_numpy()
    tune_mask, report_mask = np.isin(folds, [0, 1, 2]), np.isin(folds, [3, 4])
    best_in = tune_grid(data, *args, mask=tune_mask, service_level=service_level)[0]
    held_out = {
        "tuned_on": "folds 0-2 (60 engines)", "reported_on": "folds 3-4 (40 engines)",
        "tuned_setting": {"threshold": best_in.threshold, "horizon_days": best_in.horizon_days},
        "default_on_held_out": evaluate_setting(data, *args, DEFAULT_THRESHOLD, DEFAULT_HORIZON, report_mask, service_level).model_dump(),
        "tuned_on_held_out": evaluate_setting(data, *args, best_in.threshold, best_in.horizon_days, report_mask, service_level).model_dump(),
        "same_choice_as_full_grid": (best_in.threshold, best_in.horizon_days) == (best.threshold, best.horizon_days),
    }
    result = {
        "threshold": best.threshold, "horizon_days": best.horizon_days, "total_cost": best.total_cost,
        "tuned_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "inputs": {"crews_per_station": crews_per_station, "cost_breakdown": cost_breakdown,
                   "cost_service": cost_service, "service_level": service_level},
        "default": default.model_dump(), "tuned": best.model_dump(),
        "lowest_cost_ignoring_service_level": min(grid, key=lambda s: (s.total_cost, abs(s.threshold - 0.5))).model_dump(),
        "grid": [s.model_dump() for s in sorted(grid, key=lambda s: (s.horizon_days, s.threshold))],
        "held_out": held_out,
    }
    impact = run_policies(oof, None, SimulateRequest(crews_per_station=crews_per_station, cost_breakdown=cost_breakdown,
                                                     cost_service=cost_service), best)
    result["impact"] = impact.model_dump(exclude={"computed_ms"})
    if write:
        meta_path = model_dir / "metadata.json"
        meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        meta["tuned"] = {"threshold": best.threshold, "horizon_days": best.horizon_days, "tuned_at": result["tuned_at"]}
        meta["tuning"] = result
        meta["headline"] = impact.headline.model_dump()
        meta_path.write_text(json.dumps(meta, indent=1))
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description="Self-tune threshold and horizon on cross-fitted predictions")
    ap.add_argument("--crews", type=int, default=2)
    ap.add_argument("--cost-breakdown", type=float, default=200_000)
    ap.add_argument("--cost-service", type=float, default=20_000)
    ap.add_argument("--service-level", type=float, default=SERVICE_LEVEL)
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args()
    r = run(None, a.crews, a.cost_breakdown, a.cost_service, a.service_level, write=not a.no_write)
    print(f"{'threshold':>9s} {'horizon':>7s} {'year cost':>11s} {'caught 14d+':>11s}  ok")
    for s in r["grid"]:
        mark = " <- tuned" if (s["threshold"], s["horizon_days"]) == (r["threshold"], r["horizon_days"]) else (
            " <- default" if (s["threshold"], s["horizon_days"]) == (DEFAULT_THRESHOLD, DEFAULT_HORIZON) else "")
        print(f"{s['threshold']:9.1f} {s['horizon_days']:7d} {s['total_cost'] / 1e6:10.2f}M {s['detected']:6d}/{s['total']:<4d}  "
              f"{'yes' if s['meets_service_level'] else 'no ':3s}{mark}")
    d, t, h = r["default"], r["tuned"], r["held_out"]
    print(f"\nDefault {d['threshold']}/{d['horizon_days']}d: ${d['total_cost']:,.0f}, caught {d['detected']}/{d['total']} 14+ days early")
    print(f"Tuned   {t['threshold']}/{t['horizon_days']}d: ${t['total_cost']:,.0f}, caught {t['detected']}/{t['total']} 14+ days early")
    hd, ht = h["default_on_held_out"], h["tuned_on_held_out"]
    print(f"Held out (tuned on folds 0-2 -> {h['tuned_setting']}, reported on folds 3-4): "
          f"default caught {hd['detected']}/{hd['total']} at ${hd['total_cost']:,.0f}; tuned caught {ht['detected']}/{ht['total']} at ${ht['total_cost']:,.0f}")


if __name__ == "__main__":
    main()
