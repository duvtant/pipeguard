# Olise: ML Engine

**You own the brain of PipeGuard:** train the models, predict remaining life as a range, turn it into risk and a weekly service plan, simulate the outcome against two baselines, tune the alert threshold, and learn from technician feedback.

This is 30% of the score (Autonomous Reasoning + Data-Driven Decisions). Judges want to see data in, a decision out, and one visible improvement round against a named baseline.

**Read first:** `00_TEAM_CONTRACT.md`, then this file, then `docs/techstack.md` sections 5, 6, 7 and 10.
Repo: https://github.com/duvtant/pipeguard. Branches: `olise/...`.

---

## 1. What you deliver

| # | Deliverable | Needed by | Who is waiting |
|---|---|---|---|
| 1 | `core/contracts.py` v0 (Pydantic types for everything in the contract) | first hour | Ebube, David |
| 2 | **v0 model + `oof_predictions.parquet` + `infra/scenario.json` v0** | about 90 minutes in | Ebube (simulator), David (dashboard data) |
| 3 | Final models, fold models, `unit_fold_map.json`, `feature_config.json`, `metadata.json` | Sat 12 PM | Engine, David's deck |
| 4 | `engine/worker.py` predicting live with the fold models | Sat 12 PM checkpoint | Everyone |
| 5 | `core/quality.py`, `risk.py`, `explain.py`, `scheduler.py` | Sat afternoon | Ebube (API calls the scheduler on re-plan) |
| 6 | `core/simulate.py`, `ml/tune.py` (Impact tab) | Sat afternoon | David (Impact tab), Ebube (`/api/simulate`) |
| 7 | `core/feedback.py` | Sat afternoon | Ebube |
| 8 | Final scenario (`ml/make_scenario.py`), fallback predictions, headline number | As early as possible (no freeze; the real deadline is Sun 11 AM) | Everyone |

**v0 first.** A rough model and a rough scenario in 90 minutes beat a perfect one at 5 PM. The other two are blocked on your files.

---

## 2. Files you own

```
ml/
  data/                      NASA FD001 (copied from the hackathon repo, cited)
  legacy/                    case4_vs_case10_check.py, output.txt (the baseline run)
  train.py                   Cross-fitted training, saves artifacts
  evaluate.py                Official test-set benchmark
  tune.py                    Threshold and horizon search on cross-fitted predictions
  make_scenario.py           Writes infra/scenario.json
  baseline.py                The starter-style linear model (reproduces 27.5)
  tests/
  artifacts/                 Committed (small): models, parquet, config, fallback/
core/
  contracts.py  features.py  quality.py  predict.py  risk.py
  explain.py    scheduler.py simulate.py feedback.py sensors.py
engine/worker.py
```
Do not edit `core/models.py`, `core/db.py`, `core/alerts.py`, `api/`, `simulator/`, `infra/` (except `infra/scenario.json`), or `web/`. Ask the owner.

**Rule:** everything in `core/` that you own is a **pure function**: data in, data out. No database, no network, no clock. The engine worker (also yours) is the only place that touches the database, and only through Ebube's helpers in `core/db.py`. Pure functions are what let the API call your scheduler directly and let you test everything without Docker.

---

## 3. Setup

- Python 3.11. One `requirements.txt` for `ml/`, `core/`, `engine/` (Ebube's image installs it). **Pin exact versions**, especially `lightgbm`: a model saved by one version must load in the Docker image.
- Libraries: `lightgbm`, `scikit-learn`, `pandas`, `numpy`, `pyarrow` (parquet), `pydantic`, `pytest`.
- Read the data with `pd.read_csv(path, sep=r"\s+", header=None)` and name the 26 columns `unit, cycle, setting1..3, s1..s21`. Check there are no stray all-NaN trailing columns.
- Facts to confirm on load (assert them in a test): 100 train engines, 20,631 rows, lifetimes 128 to 362 (median 199); 100 test engines, 13,096 rows; 100 RUL values.
- Drop settings `setting1..3` and flat sensors `s1, s5, s10, s16, s18, s19`. `s6` is near-constant: drop it unless validation improves. That leaves 14 sensors: `s2, s3, s4, s7, s8, s9, s11, s12, s13, s14, s15, s17, s20, s21`.

---

## 4. Build order

### Step 1: baseline and tie-out (30 min)
- Get `case4_vs_case10_check.py` and `output.txt` from the repo (`ml/legacy/`). Reproduce **MAE 27.5 cycles and 12 of 25 caught** exactly in `ml/baseline.py`.
- Read how "caught" and "failing engine" were defined in that script (the 25 engines, the cut-off in cycles) and **reuse the same definition**. Do not change it to flatter the new model. The product docs quote "27.5 to 14.8" and "18 of 25 vs 12 of 25", so those must be reproducible from the repo.
- Reproduce the quick untuned model result (14.8, 18 of 25). If you cannot, find out why before building on it.

### Step 2: features (`core/features.py`)
Backward-looking only, per unit:
- raw value of each kept sensor
- rolling mean over windows 5, 10, 20 (use what is available when shorter)
- rolling least-squares slope over windows 10 and 20
- exponentially weighted mean (span 10)
- `cycle` (age) and `history_len`

Rules and edge cases:
- **Training and live call the same function.** One function, one place. A separate "fast live version" is how silent train/serve skew starts.
- **Never look ahead.** Features at day t use readings at days <= t only. Add a test that changing a future reading does not change today's features.
- **Per unit.** A rolling window must never cross from one unit into the next (group by unit before rolling).
- **Missing values:** rolling stats skip NaNs and need a minimum number of valid points (for example 3 for a slope), otherwise return NaN. LightGBM takes NaN natively.
- **Age and history:** `cycle = sim_day - life_start_day + 1`, and only readings with `sim_day >= life_start_day` count (see section 9). With full backfill, `history_len == cycle` unless readings are masked.
- **The EWM has infinite memory.** The live engine must hold the unit's **full history** (at most about 360 rows), not a truncated window, or live values drift from training values.
- **Performance:** the engine can compute the newest feature row incrementally, but the result must be numerically identical to the full-history computation. Test it.

### Step 3: training (`ml/train.py`)
1. **Target:** `RUL = max_cycle(unit) - cycle`, capped at 125.
2. **Cross-fitting:** 5-fold `GroupKFold` grouped by engine (20 engines per fold). For each fold train q10, q50, q90 on the other four folds. Save all **15 fold models**, `unit_fold_map.json` (engine to held-out fold) and the out-of-fold predictions.
3. **Final models:** retrain on all 100 engines for the official benchmark **only**.
4. **Missing-data augmentation, training rows only, never validation:**
   - about 5% random single blanks;
   - runs of 5 to 15 consecutive blanks on one sensor;
   - **long and permanent outages**: for about 10% of training engines, one sensor goes dead from a random day to the end of life. This matters: a dead sensor in the demo stays dead, so the model must have seen rolling windows that are entirely NaN. Short runs alone are a distribution shift.
5. **Models:** three `LightGBMRegressor`s with `objective="quantile"`, `alpha` 0.1, 0.5, 0.9. Starting parameters from `techstack.md` section 6.1. For reproducibility set `random_state=42`, `deterministic=True`, `force_row_wise=True`, `verbose=-1`. Tune lightly on cross-validation only.
6. **Quantile crossing:** sort the three outputs per row (`low <= likely <= high`).
7. **Coverage:** measure how often the true capped RUL falls inside [q10, q90] on the out-of-fold predictions. Target 70 to 90% (nominal 80%). If it is outside, apply one symmetric widening factor and store it in `feature_config.json` so training, evaluation and the live engine use it identically.
8. **Artifacts:** see `techstack.md` section 3. `metadata.json` gets the metrics, model version, git commit and the baseline numbers.

**Leakage checklist (judges and teammates will ask):**
- Folds are by engine, never by row.
- Augmentation is applied after the split and only to the training part.
- Hyperparameters are tuned on cross-validation, never on the official test set.
- The demo fleet is judged only by fold models that never saw that engine (section 5 below).
- Say plainly in the pitch that the tuned threshold and the Impact numbers are computed on the same 100 engines (see section 7 for how to reduce that).

### Step 4: official benchmark (`ml/evaluate.py`)
- Predict the **last row** of each test engine with the final models, compare with `RUL_FD001.txt`.
- Report RMSE and MAE against the **capped** true RUL (the standard approach), the NASA score, and coverage. Say in the README which RUL you capped. Put the same numbers for the linear baseline next to them.
- **Acceptance:** beat the linear baseline on RMSE, MAE and NASA score; coverage between 70 and 90%.
- Edge: a test engine with fewer than 30 rows has partial windows. Do not special-case it; it is a valid case and the confidence flag handles it live.

### Step 5: **v0 handoff**
Run steps 2 to 3 quickly with defaults, write `oof_predictions.parquet` and a first `scenario.json`, push, and tell the others. Then improve.

---

## 5. Live inference without cheating (`core/predict.py`)

`Predictor` loads all 15 fold models and `unit_fold_map.json` once. For each unit it uses the models of the fold that **did not train on that unit's source engine**. The final all-data models are for the official benchmark only, because they have seen every demo engine and would make "judged by a model that never saw it" false.

**Required test (open question 9 in `techstack.md`):** replay a clean, fault-free unit through the live code path (backfill, then day by day) and compare each day's prediction with the matching row of `oof_predictions.parquet`. They must match within floating-point tolerance. If they do not, the Impact tab and the live dashboard disagree, and one of them is wrong.

Output per unit per day: `rul_low, rul_likely, rul_high, confidence`.
- `confidence = "low"` when `history_len < 20` or any sensor is masked.
- When values are masked, widen the range by 20% (the widening applies to the width around `rul_likely`) and set `confidence = "low"`.
- Predictions are floats. Round only in the UI.
- Always return something for every live unit. If the model raises for one unit, catch it, mark that unit `data_source = "fallback"` and keep the rest of the fleet going.

---

## 6. Data quality (`core/quality.py`)

Run on every new reading before features. Rules from `techstack.md` section 7.1, with these corrections learned from the data:

| Check | Rule | Trap |
|---|---|---|
| Dead | Value is null | Easy |
| Stuck | Same value for N consecutive readings | **Several C-MAPSS sensors are low-resolution** (for example `s17` is integer-valued) and legitimately repeat for several readings. A flat "5 in a row" will flag healthy turbines. Set N **per sensor** above the longest natural run in the 100 training engines |
| Spike | Jump from the previous reading above k x std | Use the std of the sensor's **first difference**, not of its level. The level std is much larger than the reading-to-reading noise, so level std makes spikes invisible |
| Out of range | Outside training min/max by more than 3 x std | Wear legitimately moves sensors toward the edges, so use the min and max over **all** training rows including end of life |

Store the per-sensor thresholds in `feature_config.json` (computed by `train.py`, not hard-coded).

**Acceptance tests:**
1. **Zero flags** on all 100 clean training engines (run the checker over every unit's whole history). Fix thresholds, not the test.
2. Every injected fault type (`dead`, `stuck`, `spike`, `out_of_range`) is detected within a few readings, on several sensors and several units.
3. A spike masks only that reading, and a stuck sensor is masked from the point it is detected.
4. Flags have a lifecycle: a flag clears after the sensor has been clean for 5 consecutive readings (return `resolved_day`). A permanently dead sensor stays flagged and is not re-created every day (return one flag per `(unit, sensor, flag_type)` episode, not one per day).
5. A fault that starts on day 0 of a life is handled (nothing to compare against yet; dead and out-of-range still work).

Never create a call request from a quality flag. Return the flags; Ebube's `alerts.py` and the engine write the "instrument check" events.

---

## 7. Risk, status, explanation

### `core/risk.py`
- `p_fail(rul_low, rul_likely, rul_high, horizon)`: treat the three values as the 10th, 50th and 90th percentiles of remaining life and interpolate linearly to get P(remaining life <= horizon). Below q10, extrapolate along the q10 to q50 slope; above q90, along the q50 to q90 slope; clip to [0, 1].
- Edge cases to test: all three equal (degenerate range: add a tiny epsilon, avoid divide-by-zero); `rul_likely <= 0` (probability 1); very large ranges; horizon 0; `p_fail` must **rise as the horizon rises** and **fall as the whole range shifts later**.
- **Check calibration:** on the out-of-fold data, among units with `p_fail >= 0.5` at horizon 14, what fraction actually fail within 14 days? Report it (and a Brier score). This is your answer to "how do you know the numbers mean anything".

### Status (`classify`)
Per `techstack.md` 7.3: `healthy` below 0.10, `watch` from 0.10 to the threshold, `at_risk` when `p_fail >= threshold` for `CONFIRM_READINGS` (3) readings in a row.
- Add **hysteresis** so a unit does not flicker: it leaves `at_risk` only when `p_fail` falls below `threshold - 0.05` for 3 readings.
- A masked or low-confidence reading counts as "not confirmed" for entering `at_risk`, but it does not clear an existing `at_risk`.
- A unit whose life just reset (new `life_start_day`) starts `healthy` with no history.

### `core/explain.py`
Return `reason` (one plain sentence) and `top_sensors`.
- Method: for each kept sensor, compare the recent smoothed value with the unit's own early-life baseline (z-score) and look at the sign of its recent slope. Pick the sensor with the largest drift **in the direction of wear**.
- **Learn the wear direction from the data**, do not hard-code it: the sign of each sensor's correlation with RUL over the training set. Some sensors rise with wear (for example `s3`, `s4`, `s11`), some fall (for example `s7`, `s12`, `s20`, `s21`). Confirm against the data.
- Text: "<plain label> <rising|falling> for <n> days", with labels from `techstack.md` section 5.2 (that table is marked VERIFY: check it against Saxena et al., 2008). `n` is the number of consecutive days the smoothed slope kept the same sign.
- Edge cases: masked sensors are excluded; no meaningful drift returns "No significant drift"; deterministic output (same input, same string); no causal claims ("may indicate", not "is caused by"); never expose raw column names to the manager UI (`top_sensors` ids are for the chart only).

---

## 8. Scheduler (`core/scheduler.py`)

`build_plan(units, capacity, constraints, params, today) -> PlanResult`

- **Value:** `expected_saving = p_fail * C_breakdown - C_service`. Skip units with a non-positive saving.
- **Greedy v1:** sort by expected saving (tie-break by `unit_id` so the result is deterministic), assign each unit the earliest feasible day in the next 7 days where its station has a free crew slot and the day is `>= max(today, earliest_day)`.
- **Capacity:** `crews_per_station` slots per station per day (configurable). Ebube passes capacity in; you do not read settings.
- **Constraints:** a voice answer ("not before Friday") becomes `earliest_day` for that **unit** (decision for the demo: the constraint binds the unit, so the plan visibly changes; technician-level availability is a stretch). Multiple constraints for one unit: keep the latest `earliest_day`.
- **Return the diff.** `PlanResult` must contain `items`, `needs_manager_decision` (unit ids) and `changes` (a list of `added | moved | removed | unchanged` against the previous plan, with old and new days). Ebube turns `changes` into the spoken `say` sentence ("Unit 14 moves to Friday, and Unit 9 takes Thursday's slot") and the "Plan changed" event. Without the diff the voice reply and the decision log cannot be written.
- **No feasible slot** for an `at_risk` unit within the window: mark it `needs_manager_decision`. Also when its `earliest_day` is later than `today + rul_low` (the technician is free only after the unit may already have failed): `needs_manager_decision` with a clear reason. Never fail silently.
- **Stability:** re-planning must be deterministic and should not shuffle everyone for a small change. Rebuild from scratch with stable ordering so the diff is minimal and explainable.
- **Idempotent:** the same input gives the same plan. The API and the engine can both call it. Tell Ebube the plan write needs a database lock (an advisory lock) so two callers do not interleave.
- **Units already done, failed or at `watch`:** done and failed units are excluded; `watch` units are included only if their saving is positive.
- Test: crews 0 (everything needs a manager decision), crews huge (everything scheduled day 0), a constraint beyond the 7-day window, two units at one station and one crew.
- **Optimizer (stretch):** an integer program (PuLP or OR-Tools) only after the "never cut" list works.

---

## 9. Unit life, service and reset

- Each unit has `life_start_day`. `cycle = sim_day - life_start_day + 1`. Features and history use only readings from `life_start_day` onward.
- A **failed** unit (the source engine ran out of rows) has no new readings: the engine does not predict it and drops it from the plan. Ebube's simulator writes the `failure` event.
- A **serviced** unit (`part_replaced` verdict or a completed service) restarts: the simulator replays the source engine from cycle 1 and sets a new `life_start_day`. Your worker resets that unit's history, status and hysteresis. For its first readings `history_len` is small, so `confidence` is `low` and `p_fail` is near zero. That is correct.

---

## 10. Simulation and self-tuning (`core/simulate.py`, `ml/tune.py`)

This feeds the **Impact tab, the most important screen for scoring**.

**Requirements**
- **Same logic as live.** Use the same `p_fail`, `classify` and `build_plan` the engine uses. Do not write a second scheduler for the simulator.
- **Fast:** well under 1 second per call (the sliders call it repeatedly). Load `oof_predictions.parquet` once at process start, vectorize with numpy, and avoid a Python loop per unit per day where you can. Measure it.
- **Deterministic.** Same input, same output.
- **Inputs:** `crews_per_station`, `cost_breakdown`, `cost_service`, optional `threshold` and `horizon_days`. **Outputs:** per policy `breakdowns`, `planned_services`, `wasted_services`, `crew_days`, `total_cost`; `default` vs `tuned` settings; `headline`; `computed_ms`. Exact shape in the contract section 4.3.
- **Policies:** `run_to_failure` (never service early), `fixed_schedule` (every N days, default 120), `pipeguard`.
- **Wasted service:** serviced with more than 60 days of true life left.
- **Be explicit about assumptions** and write them in `ml/README.md`: what horizon the simulation covers, what happens to a unit after service (we assume it is renewed and does not fail again within the window), and how crew capacity is shared. If you evaluate each engine over its single run to failure, also report **cost per day of useful life**, because otherwise a policy that services early looks artificially cheap or expensive.
- **Headline number (D3 in the contract):** "PipeGuard would have caught X of Y failures at least 14 days early." Compute **detected** (the unit was `at_risk` 14 or more days before failure) and **actioned** (also serviced before failure given crew capacity). Use the cross-fitted predictions only. Report the lead-time distribution and the false-alarm count (units flagged far too early, for example 60 or more days before failure) so the claim survives a hard question.

**Self-tuning (`tune.py`)**
- Grid-search `threshold` over 0.2 to 0.8 (step 0.1) and `horizon_days` over 7, 14, 21 using the simulation on cross-fitted predictions only. Pick the lowest total cost. Return it so Ebube can store it in `engine_params`.
- The Impact tab shows "first result vs improved result" (default threshold vs tuned). That is the rubric's improvement round, so make the difference real and the table reproducible.
- **Honesty:** tuning and reporting on the same 100 engines flatters the result. Cheap fix: tune on engines from folds 0 to 2 and report the Impact numbers on folds 3 and 4 as well, or at least run both and quote the held-out one if the gap is large. Either way, say in the pitch that the demo fleet is the NASA training set.
- Make it callable (`tune.run(...)`) so the API can re-run it.

---

## 11. Feedback (`core/feedback.py`)

`adjust_threshold(verdicts, current) -> (new_threshold, message | None)`.
- Keep a rolling window of the last 10 verdicts. Hit rate below 60%: raise the threshold by 0.05 (max 0.9). Above 85%: lower it by 0.05 (min 0.2). Otherwise no change.
- Return a message such as "Feedback received, threshold adjusted from 0.50 to 0.55" so Ebube can write the `threshold_adjusted` event.
- `looks_fine` counts as a false alarm and lowers that unit's urgency for 7 days (return a per-unit urgency multiplier for the scheduler). `part_replaced` triggers the reset in section 9.
- Edge cases: fewer than 10 verdicts (do nothing, or use what exists but never move more than once per verdict); a burst of identical verdicts from one unit should not swing the global threshold twice; the threshold never leaves its bounds; a threshold change must be visible to the demo scenario check (section 12).

---

## 12. The demo scenario (`ml/make_scenario.py`) and the engine worker

### Scenario
`infra/scenario.json` is generated by you, because it depends on the predictions. The simulator replays it.
- **Requirement:** at default speed (1 simulated day per second), at least one unit becomes confirmed `at_risk` between replay seconds 20 and 40. A planted sensor fault (if used) appears shortly after, **on a different, healthy unit** than the one being called.
- Choose start offsets so the **first red unit has about 20 to 35 days of remaining life** at that moment (the voice script says "about 20 to 35 days left"), and the rest of the fleet has mixed ages, with a handful turning red later so the dashboard keeps moving. Do not let 20 units turn red in the same second.
- This only chooses where each replay starts. Never edit or invent sensor values, and say so openly if asked (D4).
- **Robust to the threshold:** the feedback loop and self-tuning move the threshold. Validate that the first crossing still falls in the 20 to 40 second window across the plausible threshold range (about 0.3 to 0.6), not only at one value.
- Validate with a **fast replay function** that runs the real live code path day by day with no wall clock, and report the crossing days. Re-run it whenever the model or threshold changes. Commit the scenario and its seed.
- Give Ebube and David a short list of "demo moments": the day the first unit goes red, which unit, which station (so Ebube can make sure a technician, including the French speaker, is on shift there), and the planted fault unit and day.

### Engine worker (`engine/worker.py`)
Per `techstack.md` section 4.3. Listens for `new_day`, then for the newest `sim_day`: quality checks, features, prediction, risk, explanation, plan, alerts, events.
- **Idempotent:** processing the same `sim_day` twice must not duplicate predictions or events. Write with upserts keyed on `(unit_id, sim_day)`.
- **Never fall behind:** at the fastest speed (0.25 s per day) a tick must finish in under that time. If the worker is behind, **coalesce**: process the latest day and skip the middle, never queue unbounded work.
- **Isolate failures:** wrap each unit in try/except so one bad unit cannot stall the fleet.
- **Epoch:** if `sim_state.epoch` changed (a reset), discard in-flight work and clear in-memory per-unit state.
- **Catch up** after a reconnect by reading rows newer than the last processed day, since notifications are lost while the listener is disconnected.
- **Fallback:** if live inference fails, switch to `ml/artifacts/fallback/` (a precomputed prediction for every unit and every scenario day), set `data_source = "fallback"` on those rows, and log one event.
- **Events:** write `status_change`, `sensor_issue`, `plan_changed`, `failure` handling, and `threshold_adjusted` with `unit_id`, a short `title`, a readable `detail`, and a `severity`. David displays these strings as is, so write them for a maintenance manager.
- **Two callers re-plan:** the engine on each tick and the API after a voice constraint. Coordinate with Ebube on one advisory lock around "read state, build plan, write plan".
- **Log** the tick time, the number of units processed, and the model version.

---

## 13. Tests you must have (`ml/tests/`, run with `pytest`)

| Area | Test |
|---|---|
| Data | Loader asserts row counts and lifetimes |
| Features | No lookahead; no cross-unit leakage; incremental equals full-history; NaN handling |
| Training | Folds are grouped by engine (no engine in two folds); fold models never see their held-out engine |
| Predictor | Live replay of a clean unit equals `oof_predictions.parquet`; quantiles ordered; masked input widens the range by 20% and sets `low` |
| Dead sensor | Each single sensor dead from day 0 and from mid-life: no crash, a bounded accuracy drop (report the table) |
| Quality | Zero flags on all clean training engines; all four fault types detected; one flag per episode |
| Risk | Monotone in horizon; monotone in range shift; degenerate range; `rul <= 0` |
| Status | 3-reading confirmation; hysteresis; masked readings do not clear `at_risk` |
| Scheduler | Deterministic; crews 0; capacity 1; constraint past the window; diff output correct |
| Simulation | Under 1 second; deterministic; costs add up; same scheduler as live |
| Feedback | Bounds; window; single-unit bursts |
| Scenario | A unit goes red in the 20 to 40 second window across thresholds 0.3 to 0.6 |

---

## 14. Acceptance checklist (before you call it done)

- [ ] Baseline reproduced (27.5 cycles, 12 of 25) and new model beats it (14.8 or better, 18 of 25 or better)
- [ ] Beats the baseline on RMSE, MAE and NASA score on the official test set; coverage 70 to 90%
- [ ] 15 fold models, `unit_fold_map.json`, `feature_config.json`, `metadata.json`, `oof_predictions.parquet` committed
- [ ] Live engine reproduces the cross-fitted predictions on clean data
- [ ] Zero quality flags on clean data; all fault types caught
- [ ] Scheduler returns a diff; `needs_manager_decision` works; deterministic
- [ ] Simulation under 1 second; tuned vs default table; headline number with its definition
- [ ] Scenario puts a unit red in the 20 to 40 second window, robust to the threshold
- [ ] Fallback predictions exist and the switch is tested
- [ ] `ml/README.md` states every assumption, the metrics, and how to rerun training in one command
- [ ] No secrets, no large files, versions pinned

## 15. Mistakes to avoid
- Using the final all-data models for the demo fleet.
- Tuning anything on the official test set.
- A second implementation of the scheduler or features "just for the simulator".
- A stuck-sensor rule that flags healthy low-resolution sensors.
- Quoting a headline number without saying what "caught" means.
- Writing event text only you can understand.
- Waiting for a perfect model before handing over v0.

When you are blocked or something in the docs looks wrong, add it to `techstack.md` section 19 and tell the group.
