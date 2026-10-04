"""Policy comparison: run to failure, fixed schedule, PipeGuard. Under 1 second.

Owner: Olise. Spec: Olise guide section 10, techstack section 7.5, contract section 4.3 (shape) and D3.

Same logic as live: p_fail (core.risk.p_fail), status (core.risk.classify_step, the kernel behind the
live classify) and the scheduler kernel (core.scheduler.greedy_assign, the kernel behind build_plan; only
at_risk units are booked, as in build_plan's default), all on the cross-fitted predictions only.

Two frames, both stated in the response (`assumptions`) and in ml/README.md:

1. Cost comparison (the policy table, default vs tuned): ONE SIMULATED YEAR (365 days) of the 100-unit
   fleet. Units start at staggered ages (seeded), one reading per unit per day. A unit that is serviced or
   breaks down is renewed: it starts a new life from cycle 1 of the same engine the next day. So servicing
   too early costs extra services over the year and servicing too late costs breakdowns; the threshold
   trade-off is real. Crew capacity: crews_per_station service slots per station per day, shared by the
   station's 20 units. Fixed schedule: service at age N (120) days. Wasted service: more than 60 days of
   true life left.
2. Headline (D3): each of the 100 engines followed over its single run to failure (all start on day 0).
   Detected = confirmed at_risk at least 14 days before the real failure; actioned = detected and serviced
   before failure with the available crews; false alarm = first flagged with 60 or more days left.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np
import pandas as pd

from core.contracts import Headline, PolicyResult, SimulateRequest, SimulateResponse, TuneSetting, station_of, unit_id_for_engine
from core.predict import LOW_HISTORY
from core.risk import AT_RISK, classify_step, p_fail
from core.scheduler import SAVING_ROUND, greedy_assign

DEFAULT_THRESHOLD: float = 0.5
DEFAULT_HORIZON: int = 14
FIXED_INTERVAL: int = 120
WASTE_DAYS: int = 60
LEAD_DAYS: int = 14
FALSE_ALARM_DAYS: int = 60
SIM_DAYS: int = 365
START_SEED: int = 42
THRESHOLD_GRID: tuple[float, ...] = (0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8)
HORIZON_GRID: tuple[int, ...] = (7, 14, 21)
# Self-tuning keeps the D3 promise: at least this share of failures confirmed at risk >= LEAD_DAYS early.
# Cost alone favours flagging at the last moment (accurate predictions + spare crews prevent the breakdown
# anyway), which would leave too little notice to organise a service. See techstack section 19.
SERVICE_LEVEL: float = 0.90

ASSUMPTIONS: list[str] = [
    "Costs: one simulated year of the 100-unit demo fleet (the NASA FD001 training engines), units at staggered ages.",
    "A unit that is serviced or breaks down is renewed and starts a new life the next day.",
    "Predictions are cross-fitted: every engine is judged by a model that never saw it.",
    "Each station has crews_per_station service slots per day, shared by its 20 units; PipeGuard services confirmed at-risk units in order of expected saving.",
    "Fixed schedule services each unit at age 120 days.",
    "A wasted service is one done with more than 60 days of true life left.",
    "Headline: each of the 100 engines followed once to failure; 'caught' means confirmed at risk at least 14 days before failure and serviced in time.",
    "Costs are illustrative assumptions; the company is fictional.",
]


@dataclass
class SimData:
    """The cross-fitted predictions as (units x cycles) arrays. Build once per process."""
    engines: np.ndarray            # (U,) NASA engine ids
    unit_ids: list[str]
    station_idx: np.ndarray        # (U,)
    unit_rank: np.ndarray          # (U,) rank of unit_id in string order (the scheduler's tie-break)
    max_cycle: np.ndarray          # (U,)
    low: np.ndarray                # (U, C) column c-1 = cycle c; NaN after end of life
    likely: np.ndarray
    high: np.ndarray
    rul_true: np.ndarray           # (U, C) int, -1 after end of life
    start_age: np.ndarray          # (U,) cycle already completed at day 0 of the yearly simulation
    _p_cache: dict = field(default_factory=dict)
    _memo: dict = field(default_factory=dict)      # deterministic results, keyed by their inputs (full fleet only)

    @property
    def C(self) -> int:
        return self.low.shape[1]

    def p(self, horizon: int) -> np.ndarray:
        if horizon not in self._p_cache:
            with np.errstate(invalid="ignore"):
                self._p_cache[horizon] = p_fail(self.low, self.likely, self.high, horizon)
        return self._p_cache[horizon]


def build_sim_data(oof: pd.DataFrame, fleet: dict[int, str] | None = None, seed: int = START_SEED) -> SimData:
    """`fleet`: optional NASA engine -> station code (default: the contract mapping)."""
    df = oof.sort_values(["source_engine", "cycle"])
    engines = np.sort(df["source_engine"].unique())
    U, C = len(engines), int(df["cycle"].max())
    row = np.searchsorted(engines, df["source_engine"].to_numpy())
    col = df["cycle"].to_numpy() - 1
    arrs = {}
    for name in ("rul_low", "rul_likely", "rul_high"):
        a = np.full((U, C), np.nan)
        a[row, col] = df[name].to_numpy(dtype=np.float64)
        arrs[name] = a
    rul = np.full((U, C), -1, dtype=np.int64)
    rul[row, col] = df["rul_true"].to_numpy()
    unit_ids = [unit_id_for_engine(int(e)) for e in engines]
    stations = [(fleet or {}).get(int(e), station_of(uid)) for e, uid in zip(engines, unit_ids)]
    codes = sorted(set(stations))
    rank = np.empty(U, dtype=np.int64)
    rank[np.argsort(np.array(unit_ids), kind="stable")] = np.arange(U)
    max_cycle = df.groupby("source_engine")["cycle"].max().reindex(engines).to_numpy()
    start_age = np.floor(np.random.default_rng(seed).uniform(0, 0.9, U) * max_cycle).astype(np.int64)
    return SimData(engines=engines, unit_ids=unit_ids, station_idx=np.array([codes.index(s) for s in stations]),
                   unit_rank=rank, max_cycle=max_cycle, low=arrs["rul_low"], likely=arrs["rul_likely"],
                   high=arrs["rul_high"], rul_true=rul, start_age=start_age)


# ---------------------------------------------------------------------------------------------
# Shared step helpers
# ---------------------------------------------------------------------------------------------
def _service_today(cands: np.ndarray, data: SimData, crews: int, today: int) -> np.ndarray:
    """Fill today's crew slots with the scheduler kernel. cands: unit indices in priority order.
    With no constraints, these are exactly the units build_plan assigns to `today`."""
    if len(cands) == 0 or crews <= 0:
        return cands[:0]
    slots = greedy_assign([str(s) for s in data.station_idx[cands]], [today] * len(cands), today, 1, crews)
    return np.array([c for c, s in zip(cands, slots) if s is not None], dtype=np.int64)


def _priority(cand: np.ndarray, saving: np.ndarray, data: SimData) -> np.ndarray:
    """Scheduler order: expected saving rounded to $1,000 (descending), then unit id."""
    return cand[np.lexsort((data.unit_rank[cand], -np.round(saving[cand] / SAVING_ROUND)))]


@dataclass
class Tally:
    policy: str
    breakdowns: int = 0
    services: int = 0
    wasted: int = 0
    unit_days: int = 0

    def result(self, cb: float, cs: float) -> PolicyResult:
        total = self.breakdowns * cb + self.services * cs
        return PolicyResult(policy=self.policy, breakdowns=self.breakdowns, planned_services=self.services,
                            wasted_services=self.wasted, crew_days=self.services, total_cost=float(total),
                            operating_days=self.unit_days,
                            cost_per_operating_day=float(total / self.unit_days) if self.unit_days else 0.0)


# ---------------------------------------------------------------------------------------------
# Frame 1: one simulated year with renewal (cost comparison)
# ---------------------------------------------------------------------------------------------
def simulate_year(data: SimData, policy: str, crews: int, cb: float, cs: float, threshold: float = DEFAULT_THRESHOLD,
                  horizon: int = DEFAULT_HORIZON, mask: np.ndarray | None = None, days: int = SIM_DAYS,
                  interval: int = FIXED_INTERVAL) -> Tally:
    if mask is None:   # deterministic: memoise on the inputs that matter for this policy
        key = ("year", policy, days) + ((crews, interval) if policy == "fixed_schedule" else ()) + (
            (crews, float(cb), float(cs), float(threshold), int(horizon)) if policy == "pipeguard" else ())
        if key not in data._memo:
            data._memo[key] = _simulate_year(data, policy, crews, cb, cs, threshold, horizon, None, days, interval)
        return data._memo[key]
    return _simulate_year(data, policy, crews, cb, cs, threshold, horizon, mask, days, interval)


def _simulate_year(data: SimData, policy: str, crews: int, cb: float, cs: float, threshold: float, horizon: int,
                   mask: np.ndarray | None, days: int, interval: int) -> Tally:
    U = len(data.engines)
    mask = np.ones(U, bool) if mask is None else mask
    idx = np.arange(U)
    P = data.p(horizon) if policy == "pipeguard" else None
    age = data.start_age.copy()                 # cycles completed; today's reading is cycle age + 1
    status = np.zeros(U, dtype=np.int64)
    above = np.zeros(U, dtype=np.int64)
    below = np.zeros(U, dtype=np.int64)
    t = Tally(policy, unit_days=int(mask.sum()) * days)
    for d in range(days):
        age += 1
        col = age - 1
        rul = data.rul_true[idx, col]
        fail = mask & (rul == 0)
        t.breakdowns += int(fail.sum())
        renew = rul == 0          # units outside the mask are not in the fleet; renew them only to stay in range
        if policy == "fixed_schedule":
            due = np.flatnonzero(mask & ~fail & (age >= interval))
            if len(due):
                done = _service_today(due[np.argsort(data.unit_rank[due], kind="stable")], data, crews, d)
                t.services += len(done)
                t.wasted += int((rul[done] > WASTE_DAYS).sum())
                renew[done] = True
        elif policy == "pipeguard":
            p = np.nan_to_num(P[idx, col])
            s2, a2, b2 = classify_step(p, threshold, status, above, below, age >= LOW_HISTORY)
            status, above, below = s2, a2, b2
            saving = p * cb - cs
            cand = np.flatnonzero(mask & ~fail & (status == AT_RISK) & (saving > 0))
            if len(cand):
                done = _service_today(_priority(cand, saving, data), data, crews, d)
                t.services += len(done)
                t.wasted += int((rul[done] > WASTE_DAYS).sum())
                renew[done] = True
        if renew.any():
            age[renew] = 0
            status[renew] = 0
            above[renew] = 0
            below[renew] = 0
    return t


# ---------------------------------------------------------------------------------------------
# Frame 2: each engine once to failure (headline)
# ---------------------------------------------------------------------------------------------
def first_at_risk(data: SimData, threshold: float, horizon: int) -> np.ndarray:
    """Day (= cycle - 1) each engine is first confirmed at_risk over its single life, -1 if never."""
    key = ("first", float(threshold), int(horizon))
    if key in data._memo:
        return data._memo[key]
    P = data.p(horizon)
    U = len(data.engines)
    status = np.zeros(U, dtype=np.int64)
    above = np.zeros(U, dtype=np.int64)
    below = np.zeros(U, dtype=np.int64)
    first = np.full(U, -1)
    for c in range(data.C):
        alive = data.rul_true[:, c] >= 0
        s2, a2, b2 = classify_step(np.nan_to_num(P[:, c]), threshold, status, above, below, np.full(U, c + 1 >= LOW_HISTORY))
        status, above, below = np.where(alive, s2, status), np.where(alive, a2, above), np.where(alive, b2, below)
        new = alive & (status == AT_RISK) & (first < 0)
        first[new] = c
    data._memo[key] = first
    return first


def single_life_services(data: SimData, crews: int, cb: float, cs: float, threshold: float, horizon: int,
                         mask: np.ndarray) -> np.ndarray:
    """Day each engine is serviced under PipeGuard over its single life (-1 = broke down / never)."""
    U = len(data.engines)
    P = data.p(horizon)
    status = np.zeros(U, dtype=np.int64)
    above = np.zeros(U, dtype=np.int64)
    below = np.zeros(U, dtype=np.int64)
    active = mask.copy()
    served = np.full(U, -1)
    for c in range(data.C):
        rul = data.rul_true[:, c]
        active &= ~(rul == 0)
        if not active.any():
            break
        p = np.nan_to_num(P[:, c])
        s2, a2, b2 = classify_step(p, threshold, status, above, below, np.full(U, c + 1 >= LOW_HISTORY))
        status, above, below = np.where(active, s2, status), np.where(active, a2, above), np.where(active, b2, below)
        saving = p * cb - cs
        cand = np.flatnonzero(active & (status == AT_RISK) & (saving > 0))
        if len(cand):
            done = _service_today(_priority(cand, saving, data), data, crews, c)
            served[done] = c
            active[done] = False
    return served


def headline(data: SimData, crews: int, cb: float, cs: float, threshold: float, horizon: int,
             mask: np.ndarray | None = None, lead_days: int = LEAD_DAYS) -> Headline:
    m = np.ones(len(data.engines), bool) if mask is None else mask
    first = first_at_risk(data, threshold, horizon)
    lead = np.where(first >= 0, data.max_cycle - 1 - first, -1)    # true days left when first confirmed
    served = single_life_services(data, crews, cb, cs, threshold, horizon, m)
    detected = m & (lead >= lead_days)
    actioned = detected & (served >= 0)
    false_alarm = m & (lead >= FALSE_ALARM_DAYS)
    flagged = lead[m & (lead >= 0)]
    pct = (lambda q: float(np.percentile(flagged, q)) if len(flagged) else None)
    total = int(m.sum())
    return Headline(
        detected=int(detected.sum()), actioned=int(actioned.sum()), total=total, lead_days=lead_days,
        text=f"PipeGuard would have caught {int(actioned.sum())} of {total} failures at least {lead_days} days early.",
        false_alarms=int(false_alarm.sum()), false_alarm_days=FALSE_ALARM_DAYS,
        lead_time_p10=pct(10), lead_time_median=pct(50), lead_time_p90=pct(90),
        definition=(f"Each of the {total} NASA training engines followed once to failure, judged by cross-fitted "
                    f"predictions. Detected: confirmed at risk at least {lead_days} days before the real failure "
                    f"({int(detected.sum())}). Actioned: detected and serviced before failure with "
                    f"{crews} crew(s) per station ({int(actioned.sum())}). False alarm: first flagged with "
                    f"{FALSE_ALARM_DAYS} or more days left ({int(false_alarm.sum())})."),
    )


# ---------------------------------------------------------------------------------------------
# Tuning and the API entry point
# ---------------------------------------------------------------------------------------------
def pipeguard_cost(data: SimData, crews: int, cb: float, cs: float, threshold: float, horizon: int,
                   mask: np.ndarray | None = None) -> float:
    return simulate_year(data, "pipeguard", crews, cb, cs, threshold, horizon, mask).result(cb, cs).total_cost


def _headline_memo(data: SimData, crews: int, cb: float, cs: float, threshold: float, horizon: int,
                   mask: np.ndarray | None = None) -> Headline:
    if mask is not None:
        return headline(data, crews, cb, cs, threshold, horizon, mask)
    key = ("headline", crews, float(cb), float(cs), float(threshold), int(horizon))
    if key not in data._memo:
        data._memo[key] = headline(data, crews, cb, cs, threshold, horizon)
    return data._memo[key]


def evaluate_setting(data: SimData, crews: int, cb: float, cs: float, threshold: float, horizon: int,
                     mask: np.ndarray | None = None, service_level: float = 0.0) -> TuneSetting:
    """Yearly cost plus the headline counts for one (threshold, horizon)."""
    h = _headline_memo(data, crews, cb, cs, threshold, horizon, mask)
    return TuneSetting(threshold=float(threshold), horizon_days=int(horizon),
                       total_cost=pipeguard_cost(data, crews, cb, cs, threshold, horizon, mask),
                       detected=h.detected, actioned=h.actioned, total=h.total,
                       meets_service_level=h.detected >= service_level * h.total)


def tune_grid(data: SimData, crews: int, cb: float, cs: float, mask: np.ndarray | None = None,
              service_level: float = SERVICE_LEVEL, thresholds=THRESHOLD_GRID, horizons=HORIZON_GRID) -> list[TuneSetting]:
    """Every (threshold, horizon) on the grid, best first.

    Best = lowest yearly cost among the settings that keep the D3 promise (at least `service_level` of the
    failures detected >= 14 days early); if none does, the settings with the most detections come first.
    Ties: closer to the default (0.5, 14) wins, so a tie never moves the threshold for nothing.
    service_level=0 gives the pure lowest-cost choice.
    """
    out = [evaluate_setting(data, crews, cb, cs, th, h, mask, service_level) for h in horizons for th in thresholds]
    return sorted(out, key=lambda s: (not s.meets_service_level,
                                      s.total_cost if s.meets_service_level else -(s.detected or 0),
                                      s.total_cost, abs(s.threshold - DEFAULT_THRESHOLD),
                                      abs(s.horizon_days - DEFAULT_HORIZON)))


_DATA_CACHE: dict[int, SimData] = {}


def get_sim_data(oof: pd.DataFrame, fleet: dict[int, str] | None = None) -> SimData:
    """Build the arrays once per DataFrame object (pass the same `oof` object on every call)."""
    key = hash((id(oof), tuple(sorted((fleet or {}).items()))))
    if key not in _DATA_CACHE:
        _DATA_CACHE.clear()
        _tuned_cached.cache_clear()
        _DATA_CACHE[key] = build_sim_data(oof, fleet)
    return _DATA_CACHE[key]


@lru_cache(maxsize=128)
def _tuned_cached(data_key: int, crews: int, cb: float, cs: float) -> TuneSetting:
    return tune_grid(_DATA_CACHE[data_key], crews, cb, cs)[0]


def run_policies(oof: pd.DataFrame, fleet: dict[int, str] | None, sim_params: SimulateRequest | dict,
                 tuned: TuneSetting | dict | None = None) -> SimulateResponse:
    """The Impact tab (POST /api/simulate). Load `oof` once per process and pass the same object each call.

    `tuned`: the stored self-tuned setting (engine_params, from ml/tune.py). Pass it for the fast path
    (well under 1 s for a new slider position; repeated positions are memoised). If None, the grid search
    runs here once per (crews, costs) and is cached (several seconds the first time).
    `sim_params.threshold` / `horizon_days`: override for the PipeGuard row; None means the tuned setting.
    """
    t0 = time.perf_counter()
    req = sim_params if isinstance(sim_params, SimulateRequest) else SimulateRequest(**sim_params)
    data = get_sim_data(oof, fleet)
    key = next(iter(_DATA_CACHE))
    crews, cb, cs = int(req.crews_per_station), float(req.cost_breakdown), float(req.cost_service)

    if tuned is None:
        t_set = _tuned_cached(key, crews, cb, cs)
    else:
        t_in = tuned if isinstance(tuned, TuneSetting) else TuneSetting(**{"total_cost": 0.0, **dict(tuned)})
        t_set = evaluate_setting(data, crews, cb, cs, t_in.threshold, t_in.horizon_days, service_level=SERVICE_LEVEL)
    d_set = evaluate_setting(data, crews, cb, cs, DEFAULT_THRESHOLD, DEFAULT_HORIZON, service_level=SERVICE_LEVEL)
    thr = req.threshold if req.threshold is not None else t_set.threshold
    hor = req.horizon_days if req.horizon_days is not None else t_set.horizon_days

    policies = [
        simulate_year(data, "run_to_failure", crews, cb, cs).result(cb, cs),
        simulate_year(data, "fixed_schedule", crews, cb, cs).result(cb, cs),
        simulate_year(data, "pipeguard", crews, cb, cs, thr, hor).result(cb, cs),   # memoised: same run as `tuned`
    ]
    head = _headline_memo(data, crews, cb, cs, thr, hor)
    return SimulateResponse(policies=policies, default=d_set, tuned=t_set, headline=head,
                            computed_ms=round((time.perf_counter() - t0) * 1000, 1), assumptions=ASSUMPTIONS)


def warm_up(oof: pd.DataFrame, tuned: TuneSetting | dict | None, crews: tuple[int, ...] = (1, 2, 3)) -> None:
    """Call once at API startup (same `oof` object as later calls): builds the arrays and memoises the
    default slider positions, so the first real /api/simulate request is already fast."""
    for c in crews:
        run_policies(oof, None, SimulateRequest(crews_per_station=c), tuned)
