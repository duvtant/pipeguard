"""Feature engineering. The SAME code for training and live inference.

Owner: Olise. Spec: docs/techstack.md section 6.1 step 4, Olise guide section 4 step 2.

Per unit, backward-looking only (features at cycle t use readings at cycles <= t):
  - raw value of each kept sensor
  - rolling mean over 5, 10, 20 readings (whatever is available when shorter, NaNs skipped)
  - rolling least-squares slope over 10 and 20 readings (needs >= 3 valid points, else NaN)
  - exponentially weighted mean, span 10 (infinite memory: needs the unit's full history)
  - cycle (age) and history_len (readings so far with at least one valid sensor)

How train/serve skew is prevented: there is one kernel. `build_features` (training, every row) and
`latest_features` (live, newest row per unit) both lay the histories out as a padded 3-D array
(units x time x sensors) and run the same element-wise arithmetic in the same order. Padding is NaN,
and NaN contributes exactly zero to every sum, so a unit's newest row is bitwise identical whichever
path computed it. The test suite checks this with exact equality.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from core.sensors import SENSORS

MEAN_WINDOWS: tuple[int, ...] = (5, 10, 20)
SLOPE_WINDOWS: tuple[int, ...] = (10, 20)
EWM_SPAN: int = 10
SLOPE_MIN_POINTS: int = 3
PER_SENSOR_SUFFIXES: tuple[str, ...] = (
    "", *(f"_m{w}" for w in MEAN_WINDOWS), *(f"_sl{w}" for w in SLOPE_WINDOWS), f"_ewm{EWM_SPAN}",
)


def feature_names(sensors: list[str] = SENSORS) -> list[str]:
    """Column order of the feature matrix. The models are trained on exactly this order."""
    return [f"{s}{suf}" for s in sensors for suf in PER_SENSOR_SUFFIXES] + ["cycle", "history_len"]


# ---------------------------------------------------------------------------------------------
# Kernel (shared by both paths)
# ---------------------------------------------------------------------------------------------
def _window_stats(P: np.ndarray, start: int, n_out: int, w: int, slope: bool):
    """Rolling mean (and slope) for output positions start .. start+n_out-1.

    P is (U, T + pad, S) with at least w-1 NaN rows in front of every unit's first reading, so the
    window ending at output position t covers P[:, t : t+w]. Sums are accumulated offset by offset
    in a fixed order, which makes the result independent of how many positions are computed.
    """
    shape = (P.shape[0], n_out, P.shape[2])
    n = np.zeros(shape)
    sy = np.zeros(shape)
    sx = np.zeros(shape)
    sxx = np.zeros(shape)
    sxy = np.zeros(shape)
    for k in range(w):
        wk = P[:, start + k:start + k + n_out, :]
        valid = ~np.isnan(wk)
        y = np.where(valid, wk, 0.0)
        v = valid.astype(np.float64)
        n += v
        sy += y
        if slope:
            sx += v * k
            sxx += v * (k * k)
            sxy += y * k
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = np.where(n >= 1, sy / n, np.nan)
        if not slope:
            return mean, None
        denom = n * sxx - sx * sx
        sl = np.where((n >= SLOPE_MIN_POINTS) & (denom > 0), (n * sxy - sx * sy) / denom, np.nan)
    return mean, sl


def _ewm(X: np.ndarray, record: bool) -> np.ndarray:
    """Adjusted EWM that skips NaNs (pandas `ewm(span, adjust=True, ignore_na=False)` semantics).

    num_t = (1-a) num_{t-1} + x_t ; den_t = (1-a) den_{t-1} + 1, both only where x_t is valid.
    Leading NaN padding leaves num = den = 0 exactly, so padding never changes the result.
    """
    alpha = 2.0 / (EWM_SPAN + 1.0)
    decay = 1.0 - alpha
    U, T, S = X.shape
    num = np.zeros((U, S))
    den = np.zeros((U, S))
    out = np.full((U, T, S), np.nan) if record else None
    for t in range(T):
        x = X[:, t, :]
        valid = ~np.isnan(x)
        num = decay * num + np.where(valid, x, 0.0)
        den = decay * den + valid
        if record:
            with np.errstate(invalid="ignore", divide="ignore"):
                out[:, t, :] = np.where(den > 0, num / den, np.nan)
    if record:
        return out
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(den > 0, num / den, np.nan)[:, None, :]


def _compute(X: np.ndarray, cycles: np.ndarray, last_only: bool) -> np.ndarray:
    """X: (U, T, S) sensor values with NaN padding. cycles: (U, T_out). Returns (U, T_out, F)."""
    U, T, S = X.shape
    pad = max(max(MEAN_WINDOWS), max(SLOPE_WINDOWS)) - 1
    P = np.concatenate([np.full((U, pad, S), np.nan), X], axis=1)
    n_out = 1 if last_only else T
    raw = X[:, -1:, :] if last_only else X
    blocks: dict[str, np.ndarray] = {"": raw}
    for w in sorted(set(MEAN_WINDOWS) | set(SLOPE_WINDOWS)):
        start = pad - (w - 1) + (T - 1 if last_only else 0)
        mean, sl = _window_stats(P, start, n_out, w, slope=w in SLOPE_WINDOWS)
        if w in MEAN_WINDOWS:
            blocks[f"_m{w}"] = mean
        if w in SLOPE_WINDOWS:
            blocks[f"_sl{w}"] = sl
    blocks[f"_ewm{EWM_SPAN}"] = _ewm(X, record=not last_only)

    any_valid = (~np.isnan(X)).any(axis=2).astype(np.int64)            # (U, T)
    hist = any_valid.sum(axis=1, keepdims=True) if last_only else np.cumsum(any_valid, axis=1)

    # Interleave per sensor: s, s_m5, ..., s_ewm10 for each sensor, then cycle, history_len.
    per_sensor = np.stack([blocks[suf] for suf in PER_SENSOR_SUFFIXES], axis=3)  # (U, n_out, S, k)
    per_sensor = per_sensor.reshape(U, n_out, S * len(PER_SENSOR_SUFFIXES))
    return np.concatenate(
        [per_sensor, cycles[:, :, None].astype(np.float64), hist[:, :, None].astype(np.float64)], axis=2
    )


# ---------------------------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------------------------
def build_features(readings: pd.DataFrame, sensors: list[str] = SENSORS, unit_col: str = "unit_id") -> pd.DataFrame:
    """Every row's features. Used by training, evaluation, explanation and the consistency tests.

    `readings`: one row per (unit, reading), with `unit_col`, `cycle` and the sensor columns, rows of
    each unit in time order and consecutive (one per day). NaN means missing or masked. Returns a
    frame with `unit_col`, `cycle` and `feature_names(sensors)`, in the same row order as the input.
    """
    df = readings.reset_index(drop=True)
    units = df[unit_col].to_numpy()
    codes, uniques = pd.factorize(units, sort=False)
    U = len(uniques)
    pos = df.groupby(codes, sort=False).cumcount().to_numpy()
    T = int(pos.max()) + 1 if len(df) else 0
    X = np.full((U, T, len(sensors)), np.nan)
    X[codes, pos, :] = df[sensors].to_numpy(dtype=np.float64)
    C = np.zeros((U, T))
    C[codes, pos] = df["cycle"].to_numpy(dtype=np.float64)
    F = _compute(X, C, last_only=False)
    out = pd.DataFrame(F[codes, pos, :], columns=feature_names(sensors))
    out.insert(0, unit_col, units)
    return out


def latest_features(histories: list[np.ndarray], cycles: list[int], sensors: list[str] = SENSORS) -> np.ndarray:
    """Newest feature row for each unit (the live path). Bitwise equal to `build_features`' last row.

    `histories[i]`: (T_i, S) array of the unit's full current-life history, oldest first, already
    masked by the quality checks. `cycles[i]`: the cycle of the newest row. Returns (U, F).
    """
    if not histories:
        return np.zeros((0, len(feature_names(sensors))))
    T = max(h.shape[0] for h in histories)
    U = len(histories)
    X = np.full((U, T, len(sensors)), np.nan)
    for i, h in enumerate(histories):
        if h.shape[0]:
            X[i, T - h.shape[0]:, :] = h
    C = np.asarray(cycles, dtype=np.float64).reshape(U, 1)
    return _compute(X, C, last_only=True)[:, 0, :]


def unit_series(values: np.ndarray) -> dict[str, np.ndarray]:
    """Full-history smoothed series for ONE unit (T, S): used by the explanation.

    Returns {"ewm": (T, S), "slope10": (T, S), "mean10": (T, S)}.
    """
    X = values[None, :, :].astype(np.float64)
    T = X.shape[1]
    pad = 9
    P = np.concatenate([np.full((1, pad, X.shape[2]), np.nan), X], axis=1)
    mean10, slope10 = _window_stats(P, 0, T, 10, slope=True)
    return {"ewm": _ewm(X, record=True)[0], "slope10": slope10[0], "mean10": mean10[0]}
