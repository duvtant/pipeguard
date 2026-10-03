"""Plain-English reason per unit.

Owner: Olise. Spec: Olise guide section 7 (explain), techstack section 5.2 for labels.

Method, per kept sensor:
  drift = (recent smoothed value - the unit's own early-life baseline) / reading noise, signed so that
          positive means "moving in the direction of wear".
The wear direction is learned from the data (sign of the sensor's correlation with RUL over the training
set, stored in feature_config.json), not hard-coded. The reason names the sensor with the largest drift
and how many consecutive days its 20-reading least-squares slope has kept the wear direction.

Rules: masked sensors are excluded; no meaningful drift -> "No significant drift"; same input -> same
string; no causal claims; raw column names never appear in the text (top_sensors ids are for charts).
Vectorised over units so the engine explains the whole fleet in one pass per tick.
"""
from __future__ import annotations

import numpy as np

from core.contracts import Explanation
from core.features import SLOPE_MIN_POINTS, _ewm
from core.sensors import SENSORS, label

BASELINE_READINGS: int = 20     # early-life readings that define the unit's own baseline
MIN_READINGS: int = 10          # fewer valid readings than this: too early to describe a trend
DRIFT_SIGNIFICANT: float = 1.5  # drift (in units of reading noise) below this is "no significant drift"
SLOPE_WINDOW: int = 20          # trend window for "rising for n days" (10 flips sign with the noise)
TOP_N: int = 3


def _rolling_slope(X: np.ndarray, w: int) -> np.ndarray:
    """Least-squares slope over the last w readings at every position, via cumulative sums (O(T)).
    X: (U, T, S) with NaNs. Needs SLOPE_MIN_POINTS valid points, else NaN."""
    U, T, S = X.shape
    valid = ~np.isnan(X)
    x = np.arange(T, dtype=np.float64)[None, :, None]
    v = valid.astype(np.float64)
    y = np.where(valid, X, 0.0)

    def wsum(a):
        c = np.cumsum(a, axis=1)
        out = c.copy()
        out[:, w:] = c[:, w:] - c[:, :-w]
        return out
    n, sx, sy = wsum(v), wsum(v * x), wsum(y)
    sxx, sxy = wsum(v * x * x), wsum(y * x)
    denom = n * sxx - sx * sx
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where((n >= SLOPE_MIN_POINTS) & (denom > 0), (n * sxy - sx * sy) / denom, np.nan)

NO_DRIFT = "No significant drift"
TOO_EARLY = "Not enough history yet to see a trend"


def _days_word(n: int) -> str:
    return "1 day" if n == 1 else f"{n} days"


def drift_scores(histories: list[np.ndarray], cfg: dict, sensors: list[str] = SENSORS):
    """Drift per sensor (U, S) and the right-aligned history cube X (U, T, S)."""
    U, S = len(histories), len(sensors)
    T = max(max((h.shape[0] for h in histories), default=1), 1)
    wear = np.array([cfg["wear_direction"][s] for s in sensors], dtype=float)
    noise = np.array([max(cfg["explain"][s]["noise_std"], 1e-9) for s in sensors])
    X = np.full((U, T, S), np.nan)       # right-aligned: newest reading at T-1
    base = np.full((U, S), np.nan)
    for i, h in enumerate(histories):
        n = h.shape[0]
        if n:
            X[i, T - n:] = h
            early = h[:BASELINE_READINGS]
            ok = np.isfinite(early).any(axis=0)
            with np.errstate(invalid="ignore"):
                base[i, ok] = np.nanmean(early[:, ok], axis=0)
    recent = _ewm(X, record=False)[:, 0, :]
    return (recent - base) / noise * wear, X


def trend_days(X: np.ndarray, cols: np.ndarray, wear: np.ndarray) -> np.ndarray:
    """For unit i, consecutive days (ending today) the slope of sensor cols[i] kept direction wear[i]."""
    Xi = X[np.arange(X.shape[0]), :, cols][:, :, None]                     # (U, T, 1)
    slope = _rolling_slope(Xi, SLOPE_WINDOW)[:, :, 0]
    with_wear = (np.sign(np.nan_to_num(slope)) * wear[:, None]) > 0
    return np.cumprod(with_wear[:, ::-1], axis=1).sum(axis=1)               # trailing run length


def explain_batch(histories: list[np.ndarray], cfg: dict, masked: list[list[str]] | None = None,
                  sensors: list[str] = SENSORS) -> list[Explanation]:
    """histories[i]: (T_i, S) current-life history of unit i after quality masking, oldest first.
    masked[i]: sensors masked on unit i's newest reading (excluded from the reason)."""
    if not histories:
        return []
    masked = masked or [[] for _ in histories]
    drift, X = drift_scores(histories, cfg, sensors)
    picks: list[tuple[str, list[str]] | tuple[int, list[str]]] = []
    for i, h in enumerate(histories):
        valid_rows = int(np.isfinite(h).any(axis=1).sum()) if len(h) else 0
        if valid_rows < MIN_READINGS:
            picks.append((TOO_EARLY, []))
            continue
        skip = set(masked[i])
        cand = [j for j in range(len(sensors)) if sensors[j] not in skip and np.isfinite(drift[i, j])]
        cand.sort(key=lambda j: (-drift[i, j], j))
        top = [sensors[j] for j in cand[:TOP_N]]
        if not cand or drift[i, cand[0]] < DRIFT_SIGNIFICANT:
            picks.append((NO_DRIFT, top))
        else:
            picks.append((cand[0], top))
    named = [i for i, (k, _) in enumerate(picks) if isinstance(k, int)]
    days = np.zeros(len(histories), dtype=int)
    if named:
        cols = np.array([picks[i][0] for i in named])
        wear = np.array([cfg["wear_direction"][sensors[j]] for j in cols], dtype=float)
        days[named] = trend_days(X[named], cols, wear)
    out: list[Explanation] = []
    for i, (k, top) in enumerate(picks):
        if not isinstance(k, int):
            out.append(Explanation(reason=k, top_sensors=top))
            continue
        rising = cfg["wear_direction"][sensors[k]] > 0
        n = int(days[i])
        if n >= 2:
            reason = f"{label(sensors[k])} has been {'rising' if rising else 'falling'} for {_days_word(n)}"
        else:
            reason = f"{label(sensors[k])} is {'above' if rising else 'below'} its early-life level"
        out.append(Explanation(reason=reason, top_sensors=top))
    return out


def explain(values: np.ndarray, cfg: dict, masked_sensors: list[str] | None = None,
            sensors: list[str] = SENSORS) -> Explanation:
    """One unit. values: (T, S) current-life history after quality masking, oldest first."""
    return explain_batch([values], cfg, [list(masked_sensors or [])], sensors)[0]
