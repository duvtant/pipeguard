"""Official test-set benchmark on test_FD001 + RUL_FD001.

Owner: Olise. Spec: Olise guide section 4 step 4, techstack section 6.3.

- Predicts the LAST row of each test engine with the final all-data models (never used live).
- RMSE / MAE / NASA score against the CAPPED true RUL (min(RUL, 125), the standard for FD001), plus the
  raw-RUL MAE and the "caught of 25" count so the numbers line up with the starter's 27.5 / 12 of 25.
- Coverage of the [q10, q90] range.
- Calibration of p_fail on the cross-fitted predictions (fraction that really failed, Brier score).
- Dead-sensor robustness table: each sensor dead from cycle 1 or from mid-life on every test engine.
Writes the results into ml/artifacts/metadata.json.

Run:  python -m ml.evaluate
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from core.features import build_features
from core.predict import QTAGS, final_model_path, load_boosters, postprocess, predict_boosters
from core.risk import p_fail
from core.sensors import LABELS, SENSORS
from ml import baseline
from ml.data_io import ARTIFACTS, RUL_CAP, load_test, load_test_rul


def _load(model_dir: Path):
    cfg = json.loads((model_dir / "feature_config.json").read_text())
    boosters = load_boosters([final_model_path(model_dir, q) for q in QTAGS])
    return cfg, boosters


def predict_last(test: pd.DataFrame, cfg: dict, boosters) -> np.ndarray:
    feats = build_features(test, cfg["sensors"], unit_col="unit")
    last = feats.groupby("unit").tail(1).sort_values("unit")
    return postprocess(predict_boosters(boosters, last[cfg["feature_names"]].to_numpy(np.float64)), cfg["widen_factor"])


def test_metrics(r: np.ndarray, true_raw: np.ndarray) -> dict:
    capped = np.minimum(true_raw, RUL_CAP)
    s = baseline.score(r[:, 1], true_raw)
    s["coverage_80"] = float(np.mean((capped >= r[:, 0]) & (capped <= r[:, 2])))
    return s


def calibration(oof: pd.DataFrame, horizon: int = 14, threshold: float = 0.5) -> dict:
    """Among rows with p_fail >= threshold, the fraction whose true RUL is <= horizon; plus Brier score."""
    p = p_fail(oof["rul_low"].to_numpy(), oof["rul_likely"].to_numpy(), oof["rul_high"].to_numpy(), horizon)
    event = (oof["rul_true"].to_numpy() <= horizon).astype(float)
    sel = p >= threshold
    bins = []
    for a, b in [(0, .1), (.1, .3), (.3, .5), (.5, .7), (.7, .9), (.9, 1.01)]:
        m = (p >= a) & (p < b)
        if m.any():
            bins.append({"p_from": a, "p_to": min(b, 1.0), "rows": int(m.sum()),
                         "mean_p": float(p[m].mean()), "observed": float(event[m].mean())})
    return {"horizon": horizon, "threshold": threshold, "rows_flagged": int(sel.sum()),
            "precision_at_threshold": float(event[sel].mean()) if sel.any() else None,
            "recall_at_threshold": float(sel[event == 1].mean()) if event.any() else None,
            "brier": float(np.mean((p - event) ** 2)), "reliability": bins}


def dead_sensor_table(test: pd.DataFrame, true_raw: np.ndarray, cfg: dict, boosters) -> list[dict]:
    """MAE (capped) when one sensor is dead on every test engine, from cycle 1 or from mid-life."""
    capped = np.minimum(true_raw, RUL_CAP)
    clean_mae = float(np.mean(np.abs(predict_last(test, cfg, boosters)[:, 1] - capped)))
    mid = test.groupby("unit")["cycle"].transform("max") // 2
    rows = []
    for s in cfg["sensors"]:
        row = {"sensor": s, "label": LABELS[s], "clean_mae": clean_mae}
        for name, cond in (("dead_from_day0", np.ones(len(test), bool)), ("dead_from_midlife", (test["cycle"] > mid).to_numpy())):
            t = test.copy()
            t.loc[cond, s] = np.nan
            row[f"mae_{name}"] = float(np.mean(np.abs(predict_last(t, cfg, boosters)[:, 1] - capped)))
        rows.append(row)
    return rows


def evaluate(model_dir: Path = ARTIFACTS, write: bool = True) -> dict:
    cfg, boosters = _load(model_dir)
    test, true_raw = load_test(), load_test_rul()
    assert len(true_raw) == 100 and test["unit"].nunique() == 100
    r = predict_last(test, cfg, boosters)
    res = {
        "test": test_metrics(r, true_raw),
        "baseline_linear_test": baseline.linear_baseline(),
        "quick_untuned_test": baseline.quick_untuned_model(),
    }
    oof_path = model_dir / "oof_predictions.parquet"
    if oof_path.exists():
        res["calibration"] = calibration(pd.read_parquet(oof_path))
    res["dead_sensor"] = dead_sensor_table(test, true_raw, cfg, boosters)
    t, b = res["test"], res["baseline_linear_test"]
    res["acceptance"] = {
        "beats_baseline_rmse": t["rmse"] < b["rmse"], "beats_baseline_mae": t["mae"] < b["mae"],
        "beats_baseline_nasa": t["nasa_score"] < b["nasa_score"],
        "coverage_in_70_90": 0.70 <= t["coverage_80"] <= 0.90,
        "caught_at_least_18_of_25": t["caught"] >= 18,
    }
    if write:
        meta_path = model_dir / "metadata.json"
        meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        meta.update(res)
        meta_path.write_text(json.dumps(meta, indent=1))
    return res


def main() -> None:
    res = evaluate()
    t, b = res["test"], res["baseline_linear_test"]
    print(f"{'':28s}{'RMSE':>8s}{'MAE':>8s}{'MAE raw':>9s}{'NASA':>10s}{'cover':>7s}{'caught':>8s}")
    print(f"{'Linear baseline (starter)':28s}{b['rmse']:8.2f}{b['mae']:8.2f}{b['mae_raw']:9.2f}{b['nasa_score']:10.0f}{'-':>7s}{b['caught']:>5d}/25")
    print(f"{'PipeGuard (final models)':28s}{t['rmse']:8.2f}{t['mae']:8.2f}{t['mae_raw']:9.2f}{t['nasa_score']:10.0f}{t['coverage_80']:7.2f}{t['caught']:>5d}/25")
    if "calibration" in res:
        c = res["calibration"]
        print(f"\nCalibration (OOF, horizon {c['horizon']}): p_fail >= {c['threshold']} -> {c['precision_at_threshold']:.2f} really failed within "
              f"{c['horizon']} days; Brier {c['brier']:.4f}")
    print("\nDead sensor (test MAE, capped):")
    for row in res["dead_sensor"]:
        print(f"  {row['sensor']:4s} clean {row['clean_mae']:.2f}  dead from day 0 {row['mae_dead_from_day0']:.2f}  from mid-life {row['mae_dead_from_midlife']:.2f}")
    print("\nAcceptance:", json.dumps(res["acceptance"]))


if __name__ == "__main__":
    main()
