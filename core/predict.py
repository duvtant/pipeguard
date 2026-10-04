"""Loads the 15 fold models and routes each unit to the fold that never saw it.

Owner: Olise. Spec: Olise guide section 5, techstack section 7.2.

The final all-data models (final_q*.txt) are for the official test-set benchmark ONLY. They have seen
every demo engine, so using them live would make "judged by a model that never saw it" false.

`postprocess` is the one place quantile ordering and the coverage widening factor are applied. Training
(out-of-fold predictions), evaluation and the live engine all call it, so they cannot drift apart.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable

import lightgbm as lgb
import numpy as np
import pandas as pd

from core.contracts import Prediction
from core.features import feature_names

log = logging.getLogger(__name__)

QUANTILES: tuple[float, ...] = (0.1, 0.5, 0.9)
QTAGS: tuple[str, ...] = ("q10", "q50", "q90")
MASK_WIDEN: float = 1.2        # masked sensors: widen the range by 20% around rul_likely
LOW_HISTORY: int = 20          # history_len below this -> confidence "low"
N_FOLDS: int = 5


def postprocess(raw: np.ndarray, widen: float = 1.0) -> np.ndarray:
    """(N, 3) raw quantile outputs -> (N, 3) low <= likely <= high, widened symmetrically, >= 0."""
    q = np.sort(np.asarray(raw, dtype=np.float64), axis=1)
    likely = q[:, 1]
    low = likely - (likely - q[:, 0]) * widen
    high = likely + (q[:, 2] - likely) * widen
    return np.clip(np.column_stack([low, likely, high]), 0.0, None)


def widen_for_mask(r: np.ndarray, factor: float = MASK_WIDEN) -> np.ndarray:
    """Widen (N, 3) ranges by `factor` around rul_likely (used when any sensor is masked)."""
    return postprocess(r, widen=factor)


def fold_model_path(model_dir: Path, fold: int, qtag: str) -> Path:
    return Path(model_dir) / f"fold_{fold}_{qtag}.txt"


def final_model_path(model_dir: Path, qtag: str) -> Path:
    return Path(model_dir) / f"final_{qtag}.txt"


def load_boosters(paths: list[Path]) -> list[lgb.Booster]:
    return [lgb.Booster(model_file=str(p)) for p in paths]


def predict_boosters(boosters: list[lgb.Booster], X: np.ndarray) -> np.ndarray:
    """Raw (N, 3) outputs of the q10, q50, q90 boosters."""
    if len(X) == 0:
        return np.zeros((0, 3))
    return np.column_stack([b.predict(X, num_threads=1) for b in boosters])


class Predictor:
    """Live predictor. Load once at worker start; call `predict` every tick."""

    def __init__(self, model_dir: str | Path, fallback: Callable[[int, int], tuple[float, float, float]] | None = None):
        self.model_dir = Path(model_dir)
        self.cfg = json.loads((self.model_dir / "feature_config.json").read_text())
        self.features = self.cfg.get("feature_names") or feature_names(self.cfg["sensors"])
        self.widen = float(self.cfg.get("widen_factor", 1.0))
        fold_map = json.loads((self.model_dir / "unit_fold_map.json").read_text())
        self.unit_fold_map: dict[int, int] = {int(k): int(v) for k, v in fold_map.items()}
        self.folds: dict[int, list[lgb.Booster]] = {
            k: load_boosters([fold_model_path(self.model_dir, k, q) for q in QTAGS]) for k in range(N_FOLDS)
        }
        meta_path = self.model_dir / "metadata.json"
        self.model_version = json.loads(meta_path.read_text()).get("model_version", "v0") if meta_path.exists() else "v0"
        self._fallback = fallback or OofFallback.from_dir(self.model_dir)

    def fold_for(self, source_engine: int) -> int:
        return self.unit_fold_map[int(source_engine)]

    def predict_array(self, X: np.ndarray, source_engines: np.ndarray) -> np.ndarray:
        """(N, F) features + engine ids -> (N, 3) ordered, widened ranges (no mask widening)."""
        out = np.full((len(X), 3), np.nan)
        folds = np.array([self.fold_for(e) for e in source_engines], dtype=int)
        for k in np.unique(folds):
            idx = np.flatnonzero(folds == k)
            out[idx] = postprocess(predict_boosters(self.folds[int(k)], X[idx]), self.widen)
        return out

    def predict(self, features: pd.DataFrame, masked_info: dict[str, list[str]] | None = None) -> list[Prediction]:
        """One Prediction per row of `features`.

        `features` columns: unit_id, source_engine, sim_day and the feature columns (incl. cycle,
        history_len). `masked_info`: unit_id -> sensors masked on the newest reading.
        Never raises for one bad unit: that unit gets data_source="fallback" and the fleet continues.
        """
        masked_info = masked_info or {}
        n = len(features)
        ranges = np.full((n, 3), np.nan)
        try:
            X = features[self.features].to_numpy(dtype=np.float64)
            ranges = self.predict_array(X, features["source_engine"].to_numpy())
        except Exception:  # noqa: BLE001 - isolate per unit below
            log.exception("batch prediction failed; retrying unit by unit")
            for i in range(n):
                try:
                    row = features.iloc[[i]]
                    ranges[i] = self.predict_array(row[self.features].to_numpy(dtype=np.float64),
                                                   row["source_engine"].to_numpy())[0]
                except Exception:  # noqa: BLE001
                    log.exception("prediction failed for %s", features.iloc[i].get("unit_id"))

        out: list[Prediction] = []
        for i, row in enumerate(features.itertuples(index=False)):
            masked = list(masked_info.get(row.unit_id, []))
            r = ranges[i]
            source = "live"
            if not np.all(np.isfinite(r)):
                r = np.asarray(self._fallback(int(row.source_engine), int(row.cycle)), dtype=np.float64)
                source = "fallback"
            if masked:
                r = widen_for_mask(r[None, :])[0]
            low_conf = bool(masked) or float(row.history_len) < LOW_HISTORY or source == "fallback"
            out.append(Prediction(
                unit_id=row.unit_id, sim_day=int(row.sim_day),
                rul_low=float(r[0]), rul_likely=float(r[1]), rul_high=float(r[2]),
                confidence="low" if low_conf else "normal", data_source=source,
                model_version=self.model_version, masked_sensors=masked,
            ))
        return out


class OofFallback:
    """Fallback range by (source_engine, cycle), from the precomputed cross-fitted predictions.

    Keyed by engine and cycle (not by sim_day) so it stays correct after a unit's life restarts.
    """

    def __init__(self, table: pd.DataFrame | None):
        self.lookup: dict[tuple[int, int], tuple[float, float, float]] = {}
        if table is not None and len(table):
            for e, c, lo, li, hi in table[["source_engine", "cycle", "rul_low", "rul_likely", "rul_high"]].itertuples(index=False):
                self.lookup[(int(e), int(c))] = (float(lo), float(li), float(hi))

    @classmethod
    def from_dir(cls, model_dir: Path) -> "OofFallback":
        for path in (Path(model_dir) / "fallback" / "fallback_predictions.parquet", Path(model_dir) / "oof_predictions.parquet"):
            if path.exists():
                try:
                    return cls(pd.read_parquet(path))
                except Exception:  # noqa: BLE001
                    log.exception("could not read fallback table %s", path)
        return cls(None)

    def __call__(self, source_engine: int, cycle: int) -> tuple[float, float, float]:
        hit = self.lookup.get((source_engine, cycle))
        if hit is not None:
            return hit
        # Unknown cycle: widest honest answer (the full capped range).
        return (0.0, 62.5, 125.0)
