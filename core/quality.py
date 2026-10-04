"""Data quality checks: dead, stuck, spike, out of range (calibrated per sensor).

Owner: Olise. Spec: Olise guide section 6, techstack section 7.1.

Pure functions. `check_quality` takes each unit's current-life history (raw readings, oldest first) and
returns the masked history plus one QualityFlag per (unit, sensor, flag_type) episode. Running it on the
whole history every tick is cheap (vectorised over units and sensors) and makes the result idempotent:
the same history always gives the same masks and the same episodes, keyed by their start day.

Rules (thresholds per sensor, fitted on the 100 clean training engines by `fit_thresholds`):
  dead          value is null                                   -> sensor_offline (value stays missing)
  out of range  outside [train min - 3 std, train max + 3 std]  -> sensor_out_of_range, masked
  spike         |value - last good value| > spike_abs           -> sensor_spike, only that reading masked
  stuck         same value for stuck_n readings in a row        -> sensor_stuck, masked from detection on

Why these calibrations (learned from the data, see ml/README.md):
  - stuck_n is set above the longest natural repeat run in the training engines. Low-resolution sensors
    repeat legitimately: s17 is integer-valued and repeats up to 11 readings, s8/s13 up to 5.
  - spike_abs uses the first difference, not the level: max(6 x std(first difference), 1.25 x the largest
    natural reading-to-reading jump). For FD001 the first-difference std is close to the level std for most
    sensors (the noise dominates the slow wear), so the largest natural jump is the binding bound.
  - out-of-range bounds use min/max over ALL training rows including end of life, because wear moves
    sensors toward the edges legitimately.

Flags clear after 5 consecutive clean readings (resolved_day). Quality flags never create call requests.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from core.contracts import QualityFlag
from core.sensors import SENSORS

CLEAR_AFTER: int = 5          # clean readings needed to resolve a flag
SPIKE_REBASELINE: int = 3     # consecutive "spikes" after which the new level is accepted (a step change)
SPIKE_GAP_RESET: int = 5      # after this many missing readings, do not compare against the old value
FLAG_TYPES: tuple[str, ...] = ("sensor_offline", "sensor_stuck", "sensor_spike", "sensor_out_of_range")


def fit_thresholds(train: pd.DataFrame, sensors: list[str] = SENSORS, unit_col: str = "unit",
                   stuck_margin: int = 2, spike_k: float = 6.0, spike_margin: float = 1.25,
                   range_k: float = 3.0) -> dict[str, dict[str, float]]:
    """Per-sensor thresholds from clean training data. Stored in feature_config.json["quality"]."""
    out: dict[str, dict[str, float]] = {}
    g = train.groupby(unit_col, sort=False)
    for s in sensors:
        v = train[s].astype(float)
        d = g[s].diff()
        same = (d == 0)
        # longest run of identical consecutive values within a unit
        brk = (~same).astype(int).groupby(train[unit_col]).cumsum()
        max_run = int(same.groupby([train[unit_col], brk]).sum().max()) + 1
        lvl_std = float(v.std())
        diff_std = float(d.std())
        max_abs_diff = float(d.abs().max())
        out[s] = {
            "min": float(v.min()), "max": float(v.max()), "mean": float(v.mean()), "std": lvl_std,
            "diff_std": diff_std, "max_abs_diff": max_abs_diff, "max_natural_run": max_run,
            "stuck_n": int(max_run + stuck_margin),
            "spike_abs": float(max(spike_k * diff_std, spike_margin * max_abs_diff)),
            "lo": float(v.min() - range_k * lvl_std), "hi": float(v.max() + range_k * lvl_std),
        }
    return out


@dataclass
class QualityResult:
    masked: list[np.ndarray]                     # per unit (T_i, S), NaN where dead or masked
    flags: list[QualityFlag]                     # all episodes in the histories (open and resolved)
    masked_latest: dict[str, list[str]]          # unit_id -> sensors missing/masked on the newest reading
    flagged_latest: dict[str, list[str]] = field(default_factory=dict)  # unit_id -> sensors with an open flag

    def active_flags(self) -> list[QualityFlag]:
        return [f for f in self.flags if f.resolved_day is None]


def _threshold_arrays(cfg: dict, sensors: list[str]):
    q = cfg["quality"] if "quality" in cfg else cfg
    lo = np.array([q[s]["lo"] for s in sensors])
    hi = np.array([q[s]["hi"] for s in sensors])
    spike = np.array([q[s]["spike_abs"] for s in sensors])
    stuck_n = np.array([q[s]["stuck_n"] for s in sensors])
    return lo, hi, spike, stuck_n


def _scan(X: np.ndarray, exists: np.ndarray, cfg: dict, sensors: list[str]):
    """X (U, T, S) raw values, exists (U, T) True where a reading row exists. Returns flag cubes."""
    U, T, S = X.shape
    lo, hi, spike_abs, stuck_n = _threshold_arrays(cfg, sensors)
    ex = exists[:, :, None]
    isnan = np.isnan(X)
    dead = isnan & ex
    with np.errstate(invalid="ignore"):
        oor = ~isnan & ((X < lo) | (X > hi))

    # Stuck: run length of identical consecutive values (NaN breaks a run).
    eq = np.zeros_like(isnan)
    eq[:, 1:, :] = (X[:, 1:, :] == X[:, :-1, :])
    t_idx = np.broadcast_to(np.arange(T)[None, :, None], X.shape)
    last_break = np.maximum.accumulate(np.where(~eq, t_idx, 0), axis=1)
    runlen = t_idx - last_break + 1
    stuck = ~isnan & (runlen >= stuck_n)

    # Spike: compare with the last good value (causal scan over time, vectorised over units x sensors).
    spike = np.zeros_like(isnan)
    good = np.full((U, S), np.nan)
    since_good = np.zeros((U, S), dtype=np.int64)   # readings since the last good value
    streak = np.zeros((U, S), dtype=np.int64)       # consecutive spike flags
    for t in range(T):
        x = X[:, t, :]
        cand = ~isnan[:, t, :] & ~oor[:, t, :] & ~stuck[:, t, :]
        comparable = cand & ~np.isnan(good) & (since_good <= SPIKE_GAP_RESET)
        with np.errstate(invalid="ignore"):
            jump = comparable & (np.abs(x - good) > spike_abs)
        accept_step = jump & (streak + 1 >= SPIKE_REBASELINE)
        is_spike = jump & ~accept_step
        spike[:, t, :] = is_spike
        new_good = cand & ~is_spike
        good = np.where(new_good, x, good)
        since_good = np.where(new_good, 0, since_good + exists[:, t][:, None])
        streak = np.where(is_spike, streak + 1, np.where(new_good, 0, streak))
    return {"sensor_offline": dead, "sensor_stuck": stuck, "sensor_spike": spike, "sensor_out_of_range": oor}


def _episodes(fired: np.ndarray, exists: np.ndarray, days: np.ndarray, unit_ids: list[str],
              sensors: list[str], flag_type: str) -> list[QualityFlag]:
    """Collapse per-reading firings (U, T, S) into episodes that clear after CLEAR_AFTER clean readings."""
    out: list[QualityFlag] = []
    if not fired.any():
        return out
    U, T, S = fired.shape
    for u, s in zip(*np.nonzero(fired.any(axis=1))):
        start = None
        clean = 0
        for t in range(T):
            if not exists[u, t]:
                continue
            if fired[u, t, s]:
                if start is None:
                    start = t
                clean = 0
            elif start is not None:
                clean += 1
                if clean >= CLEAR_AFTER:
                    out.append(QualityFlag(unit_id=unit_ids[u], sensor=sensors[s], flag_type=flag_type,
                                           sim_day=int(days[u, start]), resolved_day=int(days[u, t])))
                    start, clean = None, 0
        if start is not None:
            out.append(QualityFlag(unit_id=unit_ids[u], sensor=sensors[s], flag_type=flag_type,
                                   sim_day=int(days[u, start]), resolved_day=None))
    return out


def check_quality_arrays(histories: list[np.ndarray], days: list[np.ndarray], unit_ids: list[str],
                         cfg: dict, sensors: list[str] = SENSORS) -> QualityResult:
    """Fast path for the engine. histories[i]: (T_i, S) raw values; days[i]: (T_i,) sim_days."""
    U = len(histories)
    if U == 0:
        return QualityResult([], [], {}, {})
    T = max(max(h.shape[0] for h in histories), 1)
    S = len(sensors)
    X = np.full((U, T, S), np.nan)
    exists = np.zeros((U, T), dtype=bool)
    D = np.zeros((U, T), dtype=np.int64)
    for i, (h, d) in enumerate(zip(histories, days)):
        n = h.shape[0]
        X[i, :n] = h
        exists[i, :n] = True
        D[i, :n] = d
    cubes = _scan(X, exists, cfg, sensors)
    mask = cubes["sensor_out_of_range"] | cubes["sensor_spike"] | cubes["sensor_stuck"]
    Xm = np.where(mask, np.nan, X)

    flags: list[QualityFlag] = []
    for ft in FLAG_TYPES:
        flags.extend(_episodes(cubes[ft], exists, D, unit_ids, sensors, ft))
    flags.sort(key=lambda f: (f.unit_id, f.sim_day, f.sensor, f.flag_type))

    masked_latest: dict[str, list[str]] = {}
    flagged_latest: dict[str, list[str]] = {}
    masked_out: list[np.ndarray] = []
    for i, h in enumerate(histories):
        n = h.shape[0]
        masked_out.append(Xm[i, :n].copy())
        if n:
            missing = np.isnan(Xm[i, n - 1])
            masked_latest[unit_ids[i]] = [sensors[s] for s in np.flatnonzero(missing)]
    for f in flags:
        if f.resolved_day is None:
            flagged_latest.setdefault(f.unit_id, [])
            if f.sensor not in flagged_latest[f.unit_id]:
                flagged_latest[f.unit_id].append(f.sensor)
    return QualityResult(masked_out, flags, masked_latest, flagged_latest)


def check_quality(history: pd.DataFrame, cfg: dict, sensors: list[str] = SENSORS,
                  unit_col: str = "unit_id", day_col: str = "sim_day") -> tuple[pd.DataFrame, QualityResult]:
    """DataFrame wrapper. `history`: rows of the current life per unit, time-ordered. Returns the masked
    frame (same rows and columns) and the QualityResult."""
    df = history.reset_index(drop=True)
    unit_ids: list[str] = []
    hs: list[np.ndarray] = []
    ds: list[np.ndarray] = []
    index_parts: list[np.ndarray] = []
    for uid, g in df.groupby(unit_col, sort=False):
        unit_ids.append(uid)
        hs.append(g[sensors].to_numpy(dtype=np.float64))
        ds.append(g[day_col].to_numpy())
        index_parts.append(g.index.to_numpy())
    res = check_quality_arrays(hs, ds, unit_ids, cfg, sensors)
    masked = df.copy()
    for idx, m in zip(index_parts, res.masked):
        masked.loc[idx, sensors] = m
    return masked, res
