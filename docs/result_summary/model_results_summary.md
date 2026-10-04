# PipeGuard model: accuracy and expected output

Model version **v1**, trained 2026-10-03 (git `fecb4e8`). Source of every number: `ml/artifacts/metadata.json`,
`ml/artifacts/demo_moments.json` and the tests in `ml/tests/` (55 passing). Rerun everything with
`python -m ml.run_all`.

Data: NASA C-MAPSS FD001 (Saxena et al., 2008). The demo fleet is the 100 NASA training engines,
relabelled as fictional Prairie Gas Transmission turbines. Costs are illustrative assumptions.

---

## 1. In one paragraph

PipeGuard predicts each turbine's remaining life as a range (low / likely / high, the 10th, 50th and 90th
percentiles) with three LightGBM quantile models. On the official NASA test set it is **2.4x more accurate
than the hackathon's linear baseline** (RMSE 14.3 vs 34.9 cycles) and its 80% range contains the true answer
82% of the time. Turned into decisions, it would have **caught 96 of 100 failures at least 14 days early with
no false alarms**, and over a simulated year it costs **$4.1M vs $6.7M for a fixed schedule and $36.2M for
running to failure**.

---

## 2. Prediction accuracy

### 2.1 Official benchmark (never used for training or tuning)

Last reading of each of the 100 `test_FD001` engines, scored against `RUL_FD001`. Errors are in cycles
(1 cycle = 1 simulated day). RMSE, MAE and NASA score use the true RUL capped at 125 (the standard for FD001);
"MAE raw" uses the uncapped value so it lines up with the starter's 27.5.

| Model                                     | RMSE      | MAE       | MAE raw   | NASA score (lower is better) | 80% range coverage | Failing engines caught            |
| ----------------------------------------- | --------- | --------- | --------- | ---------------------------- | ------------------ | --------------------------------- |
| Linear baseline (hackathon starter)       | 34.87     | 27.80     | 27.51     | 26,282                       | none               | 12 of 25                          |
| Quick LightGBM, defaults (reconstruction) | 17.67     | 13.18     | 14.25     | 603                          | none               | 19 of 25                          |
| **PipeGuard v1**                          | **14.30** | **10.35** | **11.42** | **397**                      | **0.82**           | **18 of 25** (1 extra inspection) |

- "Failing engine" = true remaining life below 30 cycles at its last reading (25 of 100 test engines).
  "Caught" = predicted remaining life below 30. This is the starter's own definition, unchanged.
- The 7 missed engines are mostly borderline: true life 26 to 29 cycles, predicted 30 to 36.
- **Acceptance checklist: all passed** (beats the baseline on RMSE, MAE and NASA score; coverage in 70-90%;
  at least 18 of 25 caught).

### 2.2 Cross-validation (the numbers that power the live demo)

5 folds grouped by engine; every engine is predicted by a model that never saw it.

| Metric                                     | Value                                      |
| ------------------------------------------ | ------------------------------------------ |
| RMSE (all 20,631 rows, capped RUL)         | 14.19                                      |
| MAE                                        | 8.98                                       |
| 80% range coverage before / after widening | 65.1% / 80.0% (one widening factor, 1.297) |

### 2.3 Are the risk numbers trustworthy? (calibration)

`p_fail` = probability of failing within the horizon, computed from the predicted range. Checked on the
cross-validated predictions (all 20,631 rows) with a **14-day horizon**. The shipped, self-tuned setting uses a 21-day horizon (section 3.3), which this table does not cover.

| Predicted p_fail | Rows   | Average predicted | Actually failed within 14 days | Gap (actual minus predicted) |
| ---------------- | ------ | ----------------- | ------------------------------ | ---------------------------- |
| 0.0 to 0.1       | 18,902 | 0.0%              | 0.3%                           | +0.3 points                  |
| 0.1 to 0.3       | 149    | 19.5%             | 30.2%                          | +10.7 points                 |
| 0.3 to 0.5       | 128    | 40.1%             | 43.8%                          | +3.7 points                  |
| 0.5 to 0.7       | 528    | 57.9%             | 84.5%                          | +26.6 points                 |
| 0.7 to 0.9       | 270    | 79.2%             | 94.4%                          | +15.2 points                 |
| 0.9 to 1.0       | 654    | 99.2%             | 98.5%                          | -0.7 points                  |

- **As an alarm it works.** When PipeGuard says "50% or more", **92.6%** of those rows really failed within 14 days, and it catches **89.7%** of all failing rows. This is a per-reading measure; "caught 14+ days early" in section 3 is a per-engine measure and is not comparable.
- **As a literal probability it runs low.** `p_fail` under-states risk in every band below 0.9, most in the
  0.5 to 0.7 band, where 58% predicted means 85% actual. Summed over all rows it expects about 1,250 failing rows and there were about 1,500, so it under-predicts failures by roughly 17%. This is the optimistic direction, not the safe one.
- **It behaves like a switch.** 95% of rows sit below 0.1 or above 0.9, and only 1,075 rows fall in between.
  Those middle rows are consecutive days from the same 100 engines, so the middle bands are a rough guide, not a precise measurement.
- Brier score **0.012** (0 is perfect). Always guessing the base rate of 7.3% would score about 0.067, so PipeGuard is about 82% better than that reference.

**What this means in practice.** Read `p_fail` as a ranking and an alarm trigger, not as a percentage to quote to a manager. The headline results in section 3 are counted directly from the simulation and do not depend on `p_fail` being a literal probability. The scheduler does use it literally (`P(fail) x breakdown cost - service cost`), so it under-values servicing units in the middle bands.

**Next step.** Recalibrate `p_fail` inside the cross-validation folds (isotonic regression) and repeat this table at the 21-day horizon.

### 2.4 Robustness to a dead sensor

Each sensor killed on every test engine, from the first reading or from mid-life. Test MAE (clean: 10.35):

| Sensor                                           | Dead from day 0 | Dead from mid-life |
| ------------------------------------------------ | --------------- | ------------------ |
| Bypass ratio (s15), worst case                   | 13.67           | 13.30              |
| Core speed (s9)                                  | 12.90           | 12.92              |
| High-pressure compressor outlet temperature (s3) | 12.87           | 12.86              |
| Bleed enthalpy (s17)                             | 12.10           | 12.05              |
| Others (10 sensors)                              | 9.93 to 11.86   | 9.92 to 11.86      |

No crashes, and accuracy stays far better than the baseline (27.8) with any single sensor dead. Live, a
masked sensor also widens the range by 20% and marks the prediction `confidence: low`.

### 2.5 Data quality checks

- **Zero false flags** across the whole history of all 100 clean training engines.
- Every fault type (dead, stuck, spike, out of range) is detected on several sensors and engines; a spike
  masks only that reading; a stuck sensor is masked from the moment it is detected.
- Thresholds are fitted per sensor from the data. Example: bleed enthalpy (s17) is integer-valued and
  legitimately repeats up to 11 readings, so "stuck" needs 13 identical readings for that sensor.

### 2.6 Live engine = offline predictions

Replaying clean engines through the live code path (full history backfill, then day by day) reproduces the
cross-validated predictions to within **1e-9**. The Impact tab and the live dashboard therefore cannot disagree.

---

## 3. Decision quality (the Impact tab)

### 3.1 One simulated year, 100 units, 2 crews per station, $200k breakdown, $20k service

| Policy                          | Breakdowns | Planned services | Wasted services (60+ days of life left) | Total cost | Cost per unit-day |
| ------------------------------- | ---------- | ---------------- | --------------------------------------- | ---------- | ----------------- |
| Run to failure                  | 181        | 0                | 0                                       | $36.20M    | $992              |
| Fixed schedule (every 120 days) | 0          | 337              | 234                                     | $6.74M     | $185              |
| **PipeGuard (tuned)**           | **0**      | **206**          | **0**                                   | **$4.12M** | **$113**          |

PipeGuard saves **$2.6M a year (39%) vs a fixed schedule** and **$32M vs running to failure**, with no
breakdowns and no wasted services.

### 3.2 Headline

> **"PipeGuard would have caught 96 of 100 failures at least 14 days early."**

| Measure                                                           | Value             |
| ----------------------------------------------------------------- | ----------------- |
| Detected (confirmed at risk 14+ days before failure)              | 96 of 100         |
| Actioned (detected and serviced in time with the available crews) | 96 of 100         |
| False alarms (first flagged with 60+ days of life left)           | 0                 |
| Warning lead time, 10th / 50th / 90th percentile                  | 15 / 20 / 26 days |

Frame: each of the 100 engines followed once to failure, judged only by models that never saw it.

### 3.3 Improvement round: default vs self-tuned

| Setting                                                               | Threshold | Horizon     | Yearly cost | Caught 14+ days early |
| --------------------------------------------------------------------- | --------- | ----------- | ----------- | --------------------- |
| First result (default)                                                | 0.5       | 14 days     | $3.92M      | 22 of 100             |
| **Improved (self-tuned)**                                             | **0.3**   | **21 days** | **$4.12M**  | **96 of 100**         |
| Held-out check: default (tuned on 60 engines, scored on the other 40) | 0.5       | 14 days     | $1.50M      | 14 of 40              |
| Held-out check: tuned                                                 | 0.3       | 21 days     | $1.60M      | **40 of 40**          |

Self-tuning searches 21 settings and picks the cheapest one that keeps the 14-day promise (at least 90% of
failures detected 14+ days early). Result: **4x more early warnings for about 5% more service cost**, and the
held-out engines confirm it is not overfitted.

---

## 4. Expected output

### 4.1 Per unit, every simulated day (what the dashboard and voice agent receive)

| Field                            | Meaning                                                                    | Example (HIN-02, demo day 29)                                          |
| -------------------------------- | -------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| `rul.low / likely / high`        | Remaining life range, days (floats; round in the UI)                       | 12.7 / 16.2 / 18.9                                                     |
| `p_fail`                         | Chance of failure within the horizon (21 days)                             | 1.00                                                                   |
| `confidence`                     | `low` if under 20 readings of history or a sensor is masked                | normal                                                                 |
| `risk_status`                    | `healthy` (< 0.10), `watch`, or `at_risk` (above threshold for 3 readings) | at_risk                                                                |
| `sensor_issue`, `display_status` | Grey + wrench for instrument problems; a real risk stays red               | false, at_risk                                                         |
| `reason`                         | Plain-English explanation, no raw sensor codes                             | "High-pressure compressor static pressure has been rising for 12 days" |
| `top_sensors`                    | Sensor ids for the chart only                                              | s11, s7, s8                                                            |
| `data_source`                    | `live`, or `fallback` if the model could not score the unit                | live                                                                   |

### 4.2 Events (written for a maintenance manager, shown as is)

- `status_change`, critical: **"HIN-02 is at risk"**: "100% chance of failure within 21 days; likely 16 days
  left (range 13 to 19). High-pressure compressor static pressure has been rising for 12 days."
- `sensor_issue`, warning: **"Instrument check: EDS-02"**: "The low-pressure turbine outlet temperature sensor
  is stuck on one value (since day 35). Its bad readings are ignored and the prediction continues with lower
  confidence. Recommended action: instrument check, not a crew call."
- `plan_changed`, info: "HIN-02 scheduled for Tuesday (day 29)." (day names come from the simulated
  calendar, day 0 = Monday 2026-10-05; with a free crew the unit is booked the same day).

### 4.3 The demo run (default speed, 1 simulated day per second)

| Moment             | What happens                                                                                                                                                             |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Day 0              | All 100 units healthy, at mixed ages                                                                                                                                     |
| **Day 29 (~29 s)** | **HIN-02 (Hinton) turns red**, with 22 true days of life left. Same day at every threshold from 0.30 to 0.60 (verified with the live code path)                          |
| Day 33 / 35        | Planted fault: EDS-02 low-pressure turbine outlet temperature sensor stuck from day 33, flagged day 35, shown grey + wrench; it never goes red and never triggers a call |
| Day 45 to 50       | Next units start turning red (GPR-05, WHT-17)                                                                                                                            |
| Days 52 to 160     | Staggered reds keep the dashboard moving: WHT-19 (52), HIN-03 (64), GPR-20 (78), EDS-19 (92), HIN-15 (108), WHT-02 (124), HIN-09 (142), WHT-13 (160)                     |

Only each unit's starting point was chosen; no sensor value was edited or invented.

### 4.4 Speed

| Operation                                            | Time                               |
| ---------------------------------------------------- | ---------------------------------- |
| Engine tick, explanations for all 100 units          | about 40 to 50 ms                  |
| `/api/simulate`, new slider position (after warm-up) | about 0.2 to 0.7 s                 |
| `/api/simulate`, repeated slider position            | under 1 ms (memoised)              |
| Full retrain (`python -m ml.train`)                  | about 7 minutes on a 4-core laptop |

---

## 5. Limits to say out loud

1. **Same engines.** The demo fleet, the Impact numbers and the tuning all use the 100 NASA training engines
   (cross-validated, so each engine is judged by a model that never saw it). Only the section 2.1 benchmark
   uses unseen test engines.
2. **The range narrows near the end of life**, so `p_fail` can move from 0 to 1 within a few days. HIN-02
   shows "healthy" on day 25 and "at risk" on day 29, with little time in "watch". At that moment the model
   says 13 to 19 days left while the truth is 22: earlier than reality, which is the safe direction.
3. **"14.8 cycles, 18 of 25"** from the earlier docs cannot be re-run (its script is not in the repo).
   Quote the numbers in this file instead.
4. **The simulation assumes renewal**: a serviced unit starts a new life the next day, and crews need no
   notice beyond the plan. The 14-day promise in tuning stands in for real-world lead time.
5. **Costs are illustrative** ($200k breakdown, $20k service) and the company is fictional.
