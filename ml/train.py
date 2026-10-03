"""Cross-fitted training. Saves 15 fold models, final models, oof_predictions.parquet, metadata.

Owner: Olise. Spec: Olise guide section 4 step 3, techstack section 6.

Run:  python -m ml.train            (about 2 minutes on a laptop; then python -m ml.evaluate)

Leakage checklist (enforced here, tested in ml/tests):
  - folds are by engine (GroupKFold on the engine id), never by row;
  - missing-data augmentation happens after the split and only on the training part of each fold;
  - hyper-parameters come from techstack 6.1 and cross-validation, never from the official test set;
  - out-of-fold predictions are produced by the SAVED fold models, reloaded through core.predict, so the
    live engine (same files, same code) reproduces them exactly.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold

from core.contracts import unit_id_for_engine
from core.features import EWM_SPAN, MEAN_WINDOWS, SLOPE_WINDOWS, build_features, feature_names
from core.predict import (LOW_HISTORY, MASK_WIDEN, N_FOLDS, QTAGS, QUANTILES, final_model_path, fold_model_path,
                          load_boosters, postprocess, predict_boosters)
from core.quality import fit_thresholds
from core.sensors import SENSORS
from ml.data_io import ARTIFACTS, ROOT, RUL_CAP, load_train

SEED = 42
LGB_PARAMS = dict(
    objective="quantile", n_estimators=600, learning_rate=0.03, num_leaves=31, min_child_samples=40,
    subsample=0.8, subsample_freq=1, colsample_bytree=0.8, random_state=SEED, deterministic=True,
    force_row_wise=True, verbose=-1, n_jobs=4,
)
# Missing-data augmentation (training rows only).
AUG_SINGLE_RATE = 0.05          # random single blanks
AUG_RUNS_PER_ENGINE = 2         # mean number of 5-15 reading outages per engine
AUG_DEAD_ENGINE_FRAC = 0.10     # engines that get one sensor dead from a random day to end of life
AUG_PLUS_CLEAN = True           # train on the augmented rows AND a clean copy (better on clean data, CV-chosen)
COVERAGE_TARGET = (0.70, 0.90)


# ---------------------------------------------------------------------------------------------
def augment(df: pd.DataFrame, rng: np.random.Generator, sensors: list[str] = SENSORS) -> pd.DataFrame:
    """Blank sensor values in TRAINING rows: single blanks, short runs, and permanent outages."""
    out = df.copy()
    vals = out[sensors].to_numpy(dtype=np.float64)
    vals[rng.random(vals.shape) < AUG_SINGLE_RATE] = np.nan
    units = out["unit"].to_numpy()
    starts = np.flatnonzero(np.r_[True, units[1:] != units[:-1]])
    ends = np.r_[starts[1:], len(units)]
    engines = np.unique(units)
    dead_engines = set(rng.choice(engines, size=max(1, int(round(AUG_DEAD_ENGINE_FRAC * len(engines)))), replace=False))
    for a, b in zip(starts, ends):
        n = b - a
        for _ in range(rng.poisson(AUG_RUNS_PER_ENGINE)):
            s = rng.integers(len(sensors))
            length = int(rng.integers(5, 16))
            st = int(rng.integers(0, max(1, n - length)))
            vals[a + st:a + st + length, s] = np.nan
        if units[a] in dead_engines:
            s = rng.integers(len(sensors))
            st = int(rng.integers(0, n))
            vals[a + st:b, s] = np.nan
    out[sensors] = vals
    return out


def make_folds(engines: np.ndarray) -> dict[int, int]:
    """engine id -> held-out fold. GroupKFold by engine, 20 engines per fold."""
    engines = np.asarray(sorted(engines))
    fold_of: dict[int, int] = {}
    for k, (_, te) in enumerate(GroupKFold(n_splits=N_FOLDS).split(engines, groups=engines)):
        for e in engines[te]:
            fold_of[int(e)] = k
    return fold_of


def training_matrix(df: pd.DataFrame, y: np.ndarray, X_clean: np.ndarray, rng: np.random.Generator,
                    fnames: list[str]) -> tuple[np.ndarray, np.ndarray]:
    """Features of the augmented training rows (plus a clean copy when AUG_PLUS_CLEAN)."""
    Xa = build_features(augment(df, rng), SENSORS, unit_col="unit")[fnames].to_numpy(dtype=np.float64)
    if AUG_PLUS_CLEAN:
        return np.vstack([Xa, X_clean]), np.concatenate([y, y])
    return Xa, y


def fit_quantiles(X: np.ndarray, y: np.ndarray) -> list[lgb.LGBMRegressor]:
    models = []
    for alpha in QUANTILES:
        m = lgb.LGBMRegressor(alpha=alpha, **LGB_PARAMS)
        m.fit(X, y)
        models.append(m)
    return models


def coverage(r: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((y >= r[:, 0]) & (y <= r[:, 2])))


def choose_widen(raw: np.ndarray, y: np.ndarray) -> float:
    """1.0 if coverage is already in 70-90%; otherwise one symmetric factor that brings it to 80%."""
    if COVERAGE_TARGET[0] <= coverage(postprocess(raw, 1.0), y) <= COVERAGE_TARGET[1]:
        return 1.0
    lo, hi = 0.2, 5.0
    for _ in range(40):
        mid = (lo + hi) / 2
        if coverage(postprocess(raw, mid), y) < 0.80:
            lo = mid
        else:
            hi = mid
    return round(hi, 4)


def nasa_score(pred: np.ndarray, true: np.ndarray) -> float:
    d = np.asarray(pred) - np.asarray(true)
    return float(np.sum(np.where(d < 0, np.exp(-d / 13.0) - 1, np.exp(d / 10.0) - 1)))


def regression_metrics(r: np.ndarray, y: np.ndarray) -> dict[str, float]:
    err = r[:, 1] - y
    return {"rmse": float(np.sqrt(np.mean(err ** 2))), "mae": float(np.mean(np.abs(err))),
            "nasa_score": nasa_score(r[:, 1], y), "coverage_80": coverage(r, y)}


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def wear_direction(train: pd.DataFrame, sensors: list[str] = SENSORS) -> dict[str, int]:
    """+1 if the sensor rises as the engine wears (negative correlation with RUL), else -1. From data."""
    return {s: (1 if train[s].corr(train["rul_capped"]) < 0 else -1) for s in sensors}


def explain_stats(train: pd.DataFrame, sensors: list[str] = SENSORS, early: int = 30) -> dict[str, dict[str, float]]:
    """Reading-to-reading noise per sensor in early life (pooled within-engine std, first 30 cycles)."""
    e = train[train["cycle"] <= early]
    out = {}
    for s in sensors:
        resid = e[s] - e.groupby("unit")[s].transform("mean")
        out[s] = {"noise_std": float(resid.std()), "corr_rul": float(train[s].corr(train["rul_capped"]))}
    return out


# ---------------------------------------------------------------------------------------------
def train(out_dir: Path = ARTIFACTS, version: str = "v1") -> dict:
    t0 = time.time()
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    tr = load_train()
    fnames = feature_names(SENSORS)
    fold_of = make_folds(tr["unit"].unique())
    tr["fold"] = tr["unit"].map(fold_of)

    clean_feats = build_features(tr, SENSORS, unit_col="unit")
    X_clean = clean_feats[fnames].to_numpy(dtype=np.float64)
    y = tr["rul_capped"].to_numpy(dtype=np.float64)

    # ---- cross-fitting -----------------------------------------------------------------------
    raw_oof = np.full((len(tr), 3), np.nan)
    for k in range(N_FOLDS):
        is_tr = (tr["fold"] != k).to_numpy()
        # augmentation after the split, training part only
        Xa, ya = training_matrix(tr[is_tr], y[is_tr], X_clean[is_tr], rng, fnames)
        models = fit_quantiles(Xa, ya)
        paths = [fold_model_path(out_dir, k, q) for q in QTAGS]
        for m, p in zip(models, paths):
            m.booster_.save_model(str(p))
        boosters = load_boosters(paths)                  # predict with the saved files, like the engine
        raw_oof[~is_tr] = predict_boosters(boosters, X_clean[~is_tr])
        print(f"fold {k}: trained on {is_tr.sum()} rows, held out {(~is_tr).sum()} rows ({time.time() - t0:.0f}s)", flush=True)

    widen = choose_widen(raw_oof, y)
    oof_r = postprocess(raw_oof, widen)
    cv = {"folds": N_FOLDS, **regression_metrics(oof_r, y), "coverage_80_before_widening": coverage(postprocess(raw_oof, 1.0), y)}

    oof = pd.DataFrame({
        "source_engine": tr["unit"].astype(int), "unit_id": tr["unit"].map(unit_id_for_engine),
        "cycle": tr["cycle"].astype(int), "max_cycle": tr["max_cycle"].astype(int),
        "rul_true": tr["rul_true"].astype(int), "rul_capped": tr["rul_capped"].astype(int),
        "fold": tr["fold"].astype(int),
        "rul_low": oof_r[:, 0], "rul_likely": oof_r[:, 1], "rul_high": oof_r[:, 2],
    })
    oof.to_parquet(out_dir / "oof_predictions.parquet", index=False)

    # ---- final models (official benchmark only) ------------------------------------------------
    Xa, ya = training_matrix(tr, y, X_clean, rng, fnames)
    for m, q in zip(fit_quantiles(Xa, ya), QTAGS):
        m.booster_.save_model(str(final_model_path(out_dir, q)))
    print(f"final models trained ({time.time() - t0:.0f}s)", flush=True)

    # ---- config and metadata -------------------------------------------------------------------
    (out_dir / "unit_fold_map.json").write_text(json.dumps({str(e): f for e, f in sorted(fold_of.items())}, indent=1))
    cfg = {
        "sensors": SENSORS, "feature_names": fnames, "mean_windows": list(MEAN_WINDOWS),
        "slope_windows": list(SLOPE_WINDOWS), "ewm_span": EWM_SPAN, "rul_cap": RUL_CAP,
        "quantiles": list(QUANTILES), "widen_factor": widen, "mask_widen": MASK_WIDEN, "low_history": LOW_HISTORY,
        "quality": fit_thresholds(tr, SENSORS, unit_col="unit"),
        "wear_direction": wear_direction(tr), "explain": explain_stats(tr),
    }
    (out_dir / "feature_config.json").write_text(json.dumps(cfg, indent=1))

    meta_path = out_dir / "metadata.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    meta.update({
        "model_version": version,
        "trained_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "git_commit": git_commit(), "rul_cap": RUL_CAP, "quantiles": list(QUANTILES),
        "lightgbm": lgb.__version__, "params": {k: v for k, v in LGB_PARAMS.items()},
        "augmentation": {"single_rate": AUG_SINGLE_RATE, "runs_per_engine": AUG_RUNS_PER_ENGINE,
                         "dead_engine_frac": AUG_DEAD_ENGINE_FRAC, "plus_clean_copy": AUG_PLUS_CLEAN},
        "widen_factor": widen, "cv": cv, "train_seconds": round(time.time() - t0, 1),
    })
    meta_path.write_text(json.dumps(meta, indent=1))
    print(json.dumps({"cv": cv, "widen_factor": widen}, indent=1))
    return meta


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--version", default="v1")
    ap.add_argument("--out", type=Path, default=ARTIFACTS)
    args = ap.parse_args()
    train(args.out, args.version)


if __name__ == "__main__":
    main()
