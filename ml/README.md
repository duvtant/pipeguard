# PipeGuard ML engine

Owner: Olise. Data: NASA C-MAPSS FD001 (Saxena et al., 2008), bundled with the IEEE YP Industry Hackathon
repository (Case 4). The demo fleet *is* the 100 NASA training engines, relabelled as fictional
Prairie Gas Transmission turbines. All costs are illustrative assumptions.

## Rerun everything (one command)

```bash
python -m ml.run_all
```

That runs, in order: `ml.baseline` (tie-out), `ml.train` (about 7 minutes on a 4-core laptop),
`ml.evaluate` (official test set), `ml.tune` (threshold and horizon), `ml.make_scenario`
(`infra/scenario.json`, `ml/artifacts/fallback/`, `ml/artifacts/demo_moments.json`). Tests: `python -m pytest ml/tests -q`.
Versions are pinned in `requirements.txt` (LightGBM 4.7.0 must match between training and the Docker image).

## What is where

| File | Purpose |
|---|---|
| `core/features.py` | Backward-looking features. ONE kernel for training and live; the live newest-row path is bitwise equal to the full-history path (tested) |
| `core/quality.py` | Dead / stuck / spike / out-of-range checks, per-sensor thresholds fitted on the training data, one flag per episode |
| `core/predict.py` | Routes each unit to the fold model that never saw its engine; quantile ordering, coverage widening, mask widening, per-unit fallback |
| `core/risk.py` | `p_fail` from the q10/q50/q90 range; status with 3-reading confirmation and hysteresis |
| `core/explain.py` | Plain-English reason (wear direction learned from data) |
| `core/scheduler.py` | Greedy crew-limited weekly plan with diff, manager decisions, constraints |
| `core/simulate.py` | Impact tab: run to failure vs fixed schedule vs PipeGuard, headline number |
| `core/feedback.py` | Threshold adjustment from technician verdicts |
| `engine/pipeline.py` | The live code path for one day, in memory (used by the worker AND the scenario replay) |
| `engine/worker.py`, `engine/store.py`, `engine/pg_store.py` | The engine loop and its database access |
| `ml/train.py`, `ml/evaluate.py`, `ml/tune.py`, `ml/make_scenario.py`, `ml/baseline.py` | Offline pipeline |

## Results

All numbers from `ml/artifacts/metadata.json` (model `v1`). Regenerate with `python -m ml.run_all`.

**Official benchmark** (`test_FD001`, last row of each of the 100 test engines, final all-data models):

| Model | RMSE | MAE | MAE (raw RUL) | NASA score | [q10, q90] coverage | Caught (of 25) |
|---|---|---|---|---|---|---|
| Linear baseline (hackathon starter) | 34.87 | 27.80 | **27.51** | 26,282 | - | **12** |
| Quick model, LightGBM defaults (reconstruction) | 17.67 | 13.18 | 14.25 | 603 | - | 19 |
| **PipeGuard v1** (quantile LightGBM, 100 features) | **14.30** | **10.35** | 11.42 | **397** | **0.82** | **18** (1 extra) |

**Cross-validation** (5 folds by engine, every row of every engine, out-of-fold): RMSE 14.19, MAE 8.98.
Raw [q10, q90] coverage was 65%; one widening factor (1.297) brings it to 80%.
Training on the augmented rows plus a clean copy was chosen on cross-validation only (RMSE for RUL < 60:
11.25 vs 11.56 for augmented rows only).

**Calibration** (out-of-fold, horizon 14): of the rows with p_fail >= 0.5, 92.6% really failed within
14 days; recall 89.7%; Brier score 0.012.

**Dead sensor** (each sensor dead on every test engine): test MAE goes from 10.35 to at most 13.7 (s15),
typically 10.6-12.9; no crashes. Full table in `metadata.json["dead_sensor"]`.

**Impact (one simulated year, 2 crews per station, $200k breakdown, $20k service):**

| Policy | Breakdowns | Services | Wasted | Total cost |
|---|---|---|---|---|
| Run to failure | 181 | 0 | 0 | $36.2M |
| Fixed schedule (120 days) | 0 | 337 | 234 | $6.74M |
| PipeGuard, tuned (threshold 0.3, horizon 21) | 0 | 206 | 0 | $4.12M |

**Improvement round** (default vs self-tuned): default 0.5 / 14 days costs $3.92M but confirms only 22 of
100 failures 14+ days early (median warning ~11 days); tuned 0.3 / 21 days catches **96 of 100** 14+ days
early for $4.12M (+5%). Held out (tuned on folds 0-2, reported on folds 3-4): default 14 of 40, tuned
**40 of 40**, same choice as the full grid.

**Headline (D3):** "PipeGuard would have caught 96 of 100 failures at least 14 days early." Detected 96,
actioned 96, false alarms (first flagged with 60+ days left) 0; warning lead time p10 / median / p90 =
15 / 20 / 26 days. Same 100 engines as the demo fleet: say so.

**Demo moments** (`ml/artifacts/demo_moments.json`): first red unit **HIN-02 (Hinton)** on day 29 at every
threshold 0.30-0.60 (22 true days left); later reds WHT-19 (day 52), HIN-03 (64), GPR-20 (78), EDS-19 (92),
HIN-15 (108), WHT-02 (124), HIN-09 (142), WHT-13 (160); planted fault: EDS-02 low-pressure turbine outlet
temperature (s4) stuck from day 33, flagged day 35, never red. Validated with the live code path.

## Definitions and assumptions (say these out loud if asked)

**Target.** `RUL = last cycle - cycle`, capped at 125 (standard for FD001: early life shows no wear).
Test metrics are against the **capped** true RUL; `MAE raw` is against the uncapped value, to line up
with the starter's 27.5.

**Baseline and "caught".** The baseline is the hackathon starter (`ml/legacy/agent_starter.py`, verbatim):
a straight line on s4, s7, s11, s12, s15. A *failing* test engine has true RUL < 30 at its last row
(25 engines); it is *caught* when the predicted RUL is < 30. Same definition for every model; never changed.
The "quick untuned model (14.8, 18 of 25)" in the older docs cannot be re-run because its script is not in
the repo; `ml/baseline.py` contains the closest simple reconstruction (see techstack section 19, item 10).

**Leakage controls.** Folds are by engine (GroupKFold, 20 engines per fold). Missing-data augmentation is
applied after the split, to training rows only. Hyper-parameters are the techstack 6.1 defaults; nothing is
tuned on the official test set. The demo fleet is predicted by the fold model that never saw that engine;
the final all-data models are used only for the official benchmark. Threshold tuning and the Impact numbers
use the same 100 engines, so `ml/tune.py` also tunes on folds 0-2 and reports on folds 3-4.

**Augmentation (training rows only).** About 5% random single blanks; on average 2 runs of 5-15 blanks
per engine; 10% of engines get one sensor dead from a random day to end of life (so the model has seen
fully-NaN windows, as in a dead-sensor demo).

**Coverage.** If the out-of-fold [q10, q90] coverage is outside 70-90%, one symmetric widening factor
(stored in `feature_config.json`) brings it to 80%; training, evaluation and live inference all apply it
through `core.predict.postprocess`.

**Live prediction.** `confidence = low` when `history_len < 20` or any sensor is masked; masked readings
widen the range by 20% around `rul_likely`. A unit whose model call fails gets the precomputed
cross-fitted range (`data_source = fallback`); the fleet keeps going.

**Quality thresholds** (fitted per sensor in `train.py`, stored in `feature_config.json`):
stuck = longest natural repeat run in the training engines + 2 (s17 is integer-valued and repeats up to
11 readings); spike = jump from the last good value above max(6 x first-difference std, 1.25 x largest
natural jump); out of range = beyond the training min/max (including end of life) by 3 x std. Result: zero
flags on all 100 clean engines; every injected fault type caught (tests).

**Status.** healthy < 0.10 <= watch < threshold; at_risk after 3 reliable readings at or above the
threshold; leaves at_risk after 3 reliable readings below threshold - 0.05. Masked / low-confidence
readings never confirm and never clear.

**Scheduler.** Expected saving = p_fail x C_breakdown - C_service. At-risk units are booked greedily (by
saving rounded to $1,000, then unit id) on the earliest free crew slot in the next 7 days, respecting
"not before" constraints (latest wins). Watch units with a positive saving are returned as "next in
line" (`deferred`), not booked: with the contract costs every watch unit has a positive saving, and
booking them made the alert threshold meaningless (techstack section 19, item 12). No slot for an
at-risk unit, or a crew free only after `today + rul_low`, means `needs_manager_decision` with a reason.

**Impact simulation.** Costs: one simulated year of the 100-unit fleet, staggered starting ages (seed 42),
one reading per unit per day, the same p_fail / status / scheduler kernels as live, crews shared per
station per day; a serviced or broken-down unit is renewed and starts a new life the next day (so early
servicing costs more services; a single run to failure cannot price that). Fixed schedule: service at
age 120. Wasted service: more than 60 days of true life left. Headline: each of the 100 engines followed
once to failure; *detected* = confirmed at risk at least 14 days before failure, *actioned* = detected and
serviced before failure with the available crews, *false alarm* = first flagged with 60+ days left.

**Self-tuning.** Grid threshold 0.2-0.8 x horizon 7/14/21. Choice = lowest yearly cost among settings that
detect at least 90% of failures 14+ days early (the D3 promise). Without that constraint, the cheapest
setting confirms units only ~9 days ahead: accurate predictions and spare crews still prevent breakdowns
in simulation, but a real crew needs notice (techstack section 19, item 14).

**Demo scenario (D4).** Only start offsets are chosen; sensor values are never edited or invented. The
first red unit is validated with the real live code path replayed day by day, at thresholds 0.30-0.60.
