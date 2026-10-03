"""Range to probability of failure within the horizon; status classification with hysteresis.

Owner: Olise. Spec: Olise guide section 7, techstack sections 7.2 and 7.3, contract D2.

p_fail: the three predictions are read as the 10th, 50th and 90th percentiles of remaining life. The CDF
is linear between them, extrapolated below q10 along the q10->q50 slope and above q90 along the q50->q90
slope, then clipped to [0, 1]. P(remaining life <= horizon).

Status (D2): healthy below 0.10, watch from 0.10 to the threshold, at_risk once p_fail >= threshold on
CONFIRM_READINGS reliable readings in a row. Hysteresis: a unit leaves at_risk only after p_fail stays
below threshold - HYSTERESIS on CLEAR_READINGS reliable readings in a row. An unreliable reading (masked
sensor or low confidence) never confirms at_risk and never clears it.

The live engine (`classify`, one unit) and the simulation (`classify_step`, all units at once) run the
same array code, so the Impact tab and the live dashboard cannot disagree on status.
"""
from __future__ import annotations

import numpy as np

from core.contracts import RiskStatus, StatusState

WATCH_FLOOR: float = 0.10
CONFIRM_READINGS: int = 3
CLEAR_READINGS: int = 3
HYSTERESIS: float = 0.05
EPS: float = 1e-6

HEALTHY, WATCH, AT_RISK = 0, 1, 2
STATUS_NAMES: tuple[RiskStatus, ...] = ("healthy", "watch", "at_risk")
STATUS_CODES: dict[str, int] = {name: i for i, name in enumerate(STATUS_NAMES)}


def p_fail(rul_low, rul_likely, rul_high, horizon):
    """P(remaining life <= horizon). Accepts scalars or numpy arrays (broadcast)."""
    q = np.sort(np.stack(np.broadcast_arrays(np.asarray(rul_low, dtype=np.float64),
                                             np.asarray(rul_likely, dtype=np.float64),
                                             np.asarray(rul_high, dtype=np.float64))), axis=0)
    lo, mid, hi = q[0], q[1], q[2]       # guard against crossed quantiles
    h = np.asarray(horizon, dtype=np.float64)
    # Degenerate ranges (all three equal) use a tiny epsilon width instead of dividing by zero.
    d_lo = np.maximum(mid - lo, EPS)
    d_hi = np.maximum(hi - mid, EPS)
    below = 0.5 - 0.4 * (mid - h) / d_lo          # line through (lo, 0.1) and (mid, 0.5)
    above = 0.5 + 0.4 * (h - mid) / d_hi          # line through (mid, 0.5) and (hi, 0.9)
    p = np.where(h <= mid, below, above)
    p = np.clip(p, 0.0, 1.0)
    p = np.where(mid <= 0, 1.0, p)
    return float(p) if p.ndim == 0 else p


def base_status(p: np.ndarray, threshold: float) -> np.ndarray:
    """Status a unit shows when it is not (or no longer) confirmed at_risk: healthy or watch."""
    return np.where(np.asarray(p) < WATCH_FLOOR, HEALTHY, WATCH)


def classify_step(p: np.ndarray, threshold: float, status: np.ndarray, above: np.ndarray,
                  below: np.ndarray, reliable: np.ndarray):
    """One reading for many units. All arrays have the same shape. Returns (status, above, below)."""
    p = np.asarray(p, dtype=np.float64)
    reliable = np.asarray(reliable, dtype=bool)
    hot = reliable & (p >= threshold)
    above = np.where(hot, above + 1, 0)

    was_red = status == AT_RISK
    cool = reliable & (p < threshold - HYSTERESIS)
    # While at_risk, an unreliable reading neither counts toward clearing nor resets the count.
    below = np.where(was_red, np.where(cool, below + 1, np.where(reliable, 0, below)), 0)

    enter = ~was_red & (above >= CONFIRM_READINGS)
    leave = was_red & (below >= CLEAR_READINGS)
    stay_red = (was_red & ~leave) | enter
    new_status = np.where(stay_red, AT_RISK, base_status(p, threshold))
    below = np.where(stay_red, below, 0)
    return new_status, above, below


def classify(p: float, threshold: float, state: StatusState | None = None, reliable: bool = True) -> StatusState:
    """One reading for one unit (the live engine). Pass StatusState() for a unit whose life just reset."""
    state = state or StatusState()
    s, a, b = classify_step(np.array([p]), threshold, np.array([STATUS_CODES[state.status]]),
                            np.array([state.above_count]), np.array([state.below_count]), np.array([reliable]))
    return StatusState(status=STATUS_NAMES[int(s[0])], above_count=int(a[0]), below_count=int(b[0]))


def classify_series(p: np.ndarray, threshold: float, reliable: np.ndarray | None = None) -> np.ndarray:
    """Status codes over time. p: (U, T) or (T,), time on the last axis. Used by tests and analysis."""
    p = np.atleast_2d(np.asarray(p, dtype=np.float64))
    rel = np.ones_like(p, dtype=bool) if reliable is None else np.atleast_2d(reliable)
    U, T = p.shape
    status = np.zeros(U, dtype=np.int64)
    above = np.zeros(U, dtype=np.int64)
    below = np.zeros(U, dtype=np.int64)
    out = np.zeros((U, T), dtype=np.int64)
    for t in range(T):
        valid = ~np.isnan(p[:, t])
        status_n, above_n, below_n = classify_step(np.nan_to_num(p[:, t]), threshold, status, above, below, rel[:, t])
        status = np.where(valid, status_n, status)
        above = np.where(valid, above_n, above)
        below = np.where(valid, below_n, below)
        out[:, t] = status
    return out
