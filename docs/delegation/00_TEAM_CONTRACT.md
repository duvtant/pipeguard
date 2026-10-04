# PipeGuard: Team Contract

**Read this first, then your own guide.** Everyone (and every coding agent) works from three documents:

1. `docs/PipeGuard_Overview.md`: what we are building and why.
2. `docs/techstack.md`: how it is built. The source of truth for architecture, schema, API and ElevenLabs.
3. This file: who owns what, the shapes the three parts exchange, and the schedule.

| Person | Role | Guide |
|---|---|---|
| **Olise** | ML engine: training, prediction, risk, scheduler, simulation, tuning, feedback | `01_OLISE_ml-engine.md` |
| **Ebube** | Backend: database, simulator, API, SSE, voice endpoints, guardrails, Docker, Caddy, deployment | `02_EBUBE_backend-api.md` |
| **David** | Dashboard, technician phone page, ElevenLabs agent, LLM test, pitch deck, submission | `03_DAVID_dashboard-voice-pitch.md` |

> **Rule for coding agents:** do not invent architecture. If the docs do not answer something, write the question in `docs/techstack.md` section 19 (Open questions) and use the stated default. If this contract and `techstack.md` disagree, `techstack.md` wins and the contract gets fixed.

---

## 1. Ground rules

1. **Major on the major.** Never cut: the model before/after, the live replay and Impact tab, one voice call that changes the plan. Polish is last.
2. **No feature freeze.** We keep building until the real deadlines: **Sunday 11:00 AM MT internal submission target, 12:00 PM hard stop**. Re-test (evals, tests) after any change to the agent, scenario or model.
3. **Submit by Sunday 11:00 AM MT.** The hard cut-off is 12:00 PM. No exceptions.
4. **One repo, three lanes.** You only edit files in your own lane. If you need a change in someone else's lane, message them, do not edit it.
5. **Shared files need an ack.** These files are shared: `core/contracts.py`, `core/models.py`, `infra/docker-compose.yml`, `.env.example`, and this folder. A change to them needs a thumbs-up from the other two before merge.
6. **No secrets in the repo.** `.env` is git-ignored. The submission is public. `VITE_` variables are public too, so no secrets there either.
7. **Everything stays labelled as simulated.** The company (Prairie Gas Transmission), the costs and the technicians are fictional. The NASA data is turbofan data used as a stand-in. Say so in the UI footer, the README and the pitch.
8. **Humans decide.** PipeGuard recommends and never controls machines. Do not build anything that writes to control systems.
9. **Do not break the build for others.** `main` always runs with `docker compose up`. Work on short branches, merge small and often (at least hourly).
10. **When blocked for more than 15 minutes, say so in the group chat.** A silent block on Saturday costs the whole team.

### Git first
**Shared repo: https://github.com/duvtant/pipeguard** (all three are collaborators). The local `pipeguard/` folder on David's machine is **not yet a git repository**, so before anyone writes code:
1. David runs `git init`, adds the remote (`git remote add origin https://github.com/duvtant/pipeguard.git`) and pushes `docs/` to `main`. If the GitHub repo already has a commit (README or license), pull it first (`git pull origin main --allow-unrelated-histories`) instead of force-pushing. The repo must end up **public** for the submission, so make sure nothing private lands in it.
2. Ebube then pushes the skeleton: the folder layout from `techstack.md` section 3, `.gitignore` (`.env`, `node_modules`, `__pycache__`, `*.pyc`, `.venv`, `web/dist`), `.env.example`, empty packages with `__init__.py`, and the `docs/` folder. Do **not** ignore `ml/artifacts/`: the models and `oof_predictions.parquet` are small and are committed so every machine runs the same model.
3. Copy the three NASA files into `ml/data/` (cite NASA C-MAPSS in the README). Also copy the baseline script and output the 27.5 and 14.8 numbers came from (`case4_vs_case10_check.py`, `output.txt`) into `ml/legacy/`. Olise needs them to reproduce the baseline exactly, and they are not in the project folder today.
4. Everyone clones `https://github.com/duvtant/pipeguard.git`. Branch names: `olise/...`, `ebube/...`, `david/...`. Merge to `main` through short pull requests.

---

## 2. Names and IDs everyone must use

| Thing | Value |
|---|---|
| Company | Prairie Gas Transmission (fictional) |
| Stations (code: name) | `EDS`: Edson, `HIN`: Hinton, `WHT`: Whitecourt, `GPR`: Grande Prairie, `DRH`: Drumheller |
| Unit ID | `<station code>-<two digits>`, `EDS-01` to `EDS-20`, 100 units total |
| Unit to NASA engine | Sorted by NASA engine id: engines 1 to 20 are `EDS-01..20`, 21 to 40 are `HIN-01..20`, and so on. The mapping lives in `infra/scenario.json` (`source_engine`) |
| Technician `field_page_id` | Short random slug, for example `t-9f3k2`. The phone page is `/field/<field_page_id>` |
| Language codes | `en`, `fr` |
| `sim_day` | Integer. Negative values are backfilled warm-up history. 1 simulated day = 1 NASA cycle |
| Simulated calendar | `sim_day` 0 is the Monday given by `calendar_start` in `scenario.json`. "Friday" always means a simulated Friday |
| Public URL | `https://pipeguard.blunelabs.com` (`A` record at Porkbun to the Hetzner server, HTTPS by Caddy) |
| Model version string | `v1`, `v2`, ... written to `metadata.json` and stored on every prediction |

### Enums (exact spellings)
| Enum | Values |
|---|---|
| `risk_status` | `healthy`, `watch`, `at_risk` |
| `display_status` | `healthy`, `watch`, `at_risk`, `sensor_issue` |
| `confidence` | `normal`, `low` |
| Fault `type` | `dead`, `stuck`, `spike`, `out_of_range` |
| Quality `flag_type` | `sensor_offline`, `sensor_stuck`, `sensor_spike`, `sensor_out_of_range` |
| Verdict | `confirmed_wear`, `looks_fine`, `part_replaced` |
| Plan item `state` | `planned`, `done`, `blocked`, `needs_manager_decision` |
| Call request `state` | `ringing`, `answered`, `missed`, `escalated`, `done` |
| Plan item `approval` | `proposed`, `approved` (optional; if absent the dashboard hides the approval step) |
| Event `type` | `status_change`, `sensor_issue`, `call_requested`, `call_answered`, `constraint_added`, `plan_changed`, `call_summary`, `plan_approved`, `manager_decision`, `feedback_received`, `threshold_adjusted`, `failure`, `manager_alert` |
| Policy | `run_to_failure`, `fixed_schedule`, `pipeguard` |

### Decisions this contract makes (flag if you disagree, the default stands)
- **D1: sensor issue vs risk.** A unit has both a `risk_status` and a `sensor_issue` boolean. The UI shows grey + wrench when `sensor_issue` is true and `risk_status` is not `at_risk`. A unit that is already `at_risk` **stays red with a wrench badge**, so a real risk is never hidden behind a sensor fault. `display_status` is computed on the server so the UI never re-derives it. Sensor issues never create call requests.
- **D2: status thresholds.** `healthy` below 0.10 `p_fail`, `watch` from 0.10 to the threshold, `at_risk` at or above the threshold for 3 readings in a row (`CONFIRM_READINGS`).
- **D3: "caught early" has two numbers.** *Detected*: the unit was `at_risk` at least 14 days before it failed. *Actioned*: it was also serviced before failure given crew capacity. The pitch uses the honest one (actioned) and can quote both.
- **D4: the demo scenario is a start-point choice.** We choose where each unit's replay starts. We never invent failures or alter values. Say so if asked.

---

## 3. Who owns which files

| Path | Owner | Notes |
|---|---|---|
| `ml/` (all), `ml/make_scenario.py` | Olise | |
| `core/contracts.py` | Olise writes v0 in the first hour, Ebube and David review | Pydantic models for everything below. The single source of truth for types |
| `core/features.py`, `quality.py`, `predict.py`, `risk.py`, `explain.py`, `scheduler.py`, `simulate.py`, `feedback.py`, `sensors.py` | Olise | Pure functions. No database or network calls inside |
| `engine/worker.py` | Olise | The loop. Calls Ebube's DB helpers |
| `core/config.py`, `db.py`, `models.py`, `alerts.py` | Ebube | `alerts.py` is guardrail logic that needs the database and timers |
| `api/`, `simulator/`, `infra/` | Ebube | `infra/scenario.json` is generated by Olise's script and committed by Olise |
| `web/` | David | |
| `infra/elevenlabs/`, `infra/recorded_call.json` | David | |
| `docs/pitch/`, `README.md`, submission | David | |
| `docs/` specs | Shared | Update `techstack.md` when a decision changes |

---

## 4. The interfaces between us

### 4.1 Olise gives Ebube (Python, in `core/`)
Exact signatures are fixed in `core/contracts.py` by Olise in the first hour. The shape is:

| Function | In | Out |
|---|---|---|
| `check_quality(history, cfg)` | Recent readings per unit | Masked readings + list of quality flags |
| `build_features(readings, cfg)` | Readings (backward-looking) | One feature row per `(unit_id, sim_day)` |
| `Predictor.predict(features, masked_info)` | Features | `rul_low`, `rul_likely`, `rul_high`, `confidence` per unit |
| `p_fail(rul_low, rul_likely, rul_high, horizon_days)` | Range | Probability 0 to 1 |
| `classify(p_fail, threshold, history_of_status)` | | `risk_status` |
| `explain(unit_history, cfg)` | | `reason` (plain English), `top_sensors` |
| `build_plan(units, capacity, constraints, params, today)` | Unit states, crew capacity, constraints | Plan items + units needing a manager decision |
| `run_policies(oof, fleet, sim_params)` | Cross-fitted predictions, costs, crews | Per-policy metrics, tuned vs default, headline |
| `adjust_threshold(verdicts, current)` | Last verdicts | New threshold + an optional message |

### 4.2 Olise gives Ebube and David (files, early and v0 first)
| File | Used by |
|---|---|
| `ml/artifacts/oof_predictions.parquet` | Ebube's simulator and API (`/api/simulate`), David (via the API) |
| `ml/artifacts/fold_*_q*.txt`, `unit_fold_map.json`, `feature_config.json`, `metadata.json` | Engine worker |
| `infra/scenario.json` | Ebube's simulator and seed |
| `ml/artifacts/fallback/` | Engine fallback |
| Metrics (`metadata.json`: test RMSE/MAE/NASA score, coverage, headline) | David's pitch deck and Impact tab |

**v0 first:** a rough model and a rough scenario by about 90 minutes in beats a perfect one at 5 PM. Everyone else is blocked on it.

### 4.3 Ebube gives David (HTTP, base path `/api`)
FastAPI publishes OpenAPI at `/docs` and `/openapi.json`. David generates the typed client from it (`openapi-typescript`) so types never drift. Until the real API exists, Ebube commits **fixture JSON** for every endpoint in `api/fixtures/` and serves it when `MOCK_API=1`. David builds against the fixtures from the start.

Endpoints are listed in `techstack.md` section 11. The JSON shapes below are the contract.

**Fleet unit** (`GET /api/fleet` returns `{"sim_day": 31, "clock": {...}, "units": [FleetUnit]}`)
```json
{
  "unit_id": "EDS-07",
  "station_code": "EDS",
  "station": "Edson",
  "risk_status": "at_risk",
  "sensor_issue": false,
  "display_status": "at_risk",
  "rul": {"low": 14, "likely": 22, "high": 35},
  "p_fail": 0.62,
  "confidence": "normal",
  "reason": "High-pressure compressor outlet temperature has been rising for 6 days",
  "top_sensors": ["s3", "s4", "s11"],
  "next_service_day": 35,
  "needs_manager_decision": false,
  "failed": false,
  "data_source": "live",
  "model_version": "v1"
}
```
`data_source` is `live` or `fallback` (when the engine switched to the precomputed predictions).

**Unit detail** (`GET /api/units/{unit_id}`): the fleet unit fields plus `history` (one point per day: `sim_day`, `rul_low`, `rul_likely`, `rul_high`, `p_fail`), `sensors` (last 60 days for the top 3 drifting sensors: `{sensor, label, points: [{sim_day, value}]}`), `events`, `calls`, `quality_flags`.

**Call record** (each item in `calls`): `{id, call_request_id, unit_id, technician_id, technician_name, conversation_id, language, transcript, summary, summary_en, duration_secs, received_via, data_collection, evaluation}`. `transcript` is the ElevenLabs `data.transcript[]` **stored unmodified** (each turn may carry `tool_calls`, `tool_results`, `triggered_guardrails`). `evaluation` is `[{criteria_id, result: success|failure|unknown, rationale}]` or `null`. Consumers must ignore unknown fields. Shapes: `web/src/lib/types.ts`.

**Plan item** (`GET /api/plan`): `{id, unit_id, station_code, planned_day, planned_date, technician_id, technician_name, expected_saving, reason, state, approval}`. `POST /api/plan/{id}/approve` (idempotent, returns the item) and `POST /api/plan/approve-all` (returns `{approved: n}`) set `approval` to `approved`; `submit_availability` sets it to `proposed` only when the day actually changes. Each approval writes one `plan_approved` event. For `state = needs_manager_decision` items, `POST /api/plan/{id}/decide` with `{choice: overtime|defer}` (422/404/409 on bad input; idempotent) sets the optional `decision` field (`overtime` books it tomorrow, approved; `deferred` accepts the risk, stays off the schedule and CSV), clears the unit's `needs_manager_decision` flag, and writes one `manager_decision` event. Work-orders CSV contains approved items only.

**Event / SSE message** (`GET /api/stream`, `GET /api/events`)
```json
{"event_id": 812, "type": "plan_changed", "sim_day": 31, "unit_id": "EDS-07",
 "title": "Plan changed", "detail": "EDS-07 moved to day 35 (technician unavailable before Friday).",
 "severity": "info", "payload": {}}
```
`severity` is `info`, `warning` or `critical`. The SSE `id` field is the `event_id`, so a reconnect with `Last-Event-ID` resumes. **Clients must de-duplicate by `event_id`**: two writers (engine and API) insert events concurrently, so a higher id can commit before a lower one. On reconnect the server therefore replays from `last_event_id - 20`, and the dashboard ignores ids it already has.

**Simulate** (`POST /api/simulate`)
```json
// request
{"crews_per_station": 2, "cost_breakdown": 200000, "cost_service": 20000,
 "threshold": null, "horizon_days": null}
// response
{"policies": [
   {"policy": "run_to_failure", "breakdowns": 100, "planned_services": 0, "wasted_services": 0, "crew_days": 0, "total_cost": 20000000},
   {"policy": "fixed_schedule", "breakdowns": 31, "planned_services": 160, "wasted_services": 84, "crew_days": 160, "total_cost": 9400000},
   {"policy": "pipeguard", "breakdowns": 6, "planned_services": 109, "wasted_services": 9, "crew_days": 109, "total_cost": 3380000}],
 "default": {"threshold": 0.5, "horizon_days": 14, "total_cost": 4100000},
 "tuned":   {"threshold": 0.4, "horizon_days": 14, "total_cost": 3380000},
 "headline": {"detected": 91, "actioned": 88, "total": 100, "lead_days": 14,
              "text": "PipeGuard would have caught 88 of 100 failures at least 14 days early."},
 "computed_ms": 240}
```
(The numbers above are placeholders to show the shape.) Target response time: under 1 second.

**Ring event** (SSE on `/api/field/{field_page_id}/stream`)
```json
{"type": "ring", "call_request_id": 41, "unit_id": "EDS-07", "station_name": "Edson",
 "technician_id": 3, "technician_name": "Marc Tremblay", "language": "fr",
 "rul_low": 14, "rul_high": 35, "reason": "...", "expires_at": "2026-10-04T16:02:30Z"}
```

**Answer response** (`POST /api/field/{field_page_id}/answer`)
```json
{"signed_url": "wss://api.elevenlabs.io/v1/convai/conversation?agent_id=...",
 "language": "fr",
 "dynamic_variables": {"technician_id": "3", "technician_name": "Marc Tremblay", "unit_id": "EDS-07",
   "station_name": "Edson", "rul_low": "14", "rul_high": "35", "reason": "...", "proposed_day": "Thursday",
   "call_request_id": "41", "sim_today": "Tuesday, October 6"}}
```
All dynamic variables are **strings**.

**Tool endpoints and webhook** (called by ElevenLabs, not by the browser): see `techstack.md` sections 11.4 and 12. David configures the tools in ElevenLabs, Ebube implements the endpoints.

### 4.4 David gives Ebube and Olise
| What | To | Why |
|---|---|---|
| ElevenLabs agent id, agent config export, webhook secret | Ebube | `.env` on the server |
| `infra/recorded_call.json` (a real successful call) | Ebube | `/api/admin/simulate-call` replays it |
| A list of what the dashboard needs that is missing from the API | Ebube | Raise it early, not at 6 PM |
| What the Impact tab needs from the simulation (extra metrics) | Olise | As early as possible |
| The pitch's numbers wishlist | Olise | Headline number, test metrics, before/after |

---

## 5. Schedule and checkpoints

All times Mountain Time. Today is Saturday, October 3. Adjust the early slots to the actual start time, keep the fixed ones.

| When | Olise | Ebube | David |
|---|---|---|---|
| **First 30 min** | `core/contracts.py` v0 | Git repo + skeleton + Docker Compose with `db`; schema in `models.py` | Vite app skeleton, theme and routes, point the domain at the server, create the ElevenLabs agent |
| **First 90 min** | v0 model, `oof_predictions.parquet`, `scenario.json` v0 | Simulator streaming from the scenario into `readings`; API with fixtures | Fleet page against fixtures; first agent test call |
| **12:00 PM checkpoint** | Engine predicting live (fold models) | Fleet endpoint on real predictions, SSE working | Fleet page showing live predictions; `/field` rings and connects |
| **Afternoon** | Scheduler, simulation, tuning, quality checks, feedback | Tool endpoints, webhook, call state machine, guardrails, test mode, admin reset | Impact tab, decision log, Test mode, LLM test (12.10), recorded call |
| **Sat evening (no freeze)** | Keep integrating | Polish and deploy | Draft deck, export agent config backup |
| **Saturday night** | Help debug; final metrics | Deploy to server, test the laptop fallback | Full demo run with a real call; ElevenLabs usage check |
| **Sunday 8 to 10 AM** | All: 2 or 3 timed rehearsals, record the backup video, screenshots | | |
| **Sunday 11:00 AM** | **Submit the GitHub Issue** | | |

Sync points: a 10-minute standup at 12:00 PM, 3:00 PM and 7:00 PM. At each one, answer: what is working end to end, what is blocking, what are we cutting.

### Cut order (if time runs short)
1. Twilio phone calls, 2. Shift brief, 3. Work order export, 4. French call, 5. Test mode toggle (keep the planted fault), 6. Optimizer upgrade (keep greedy).

---

## 6. Integration tests everyone shares

Run these on the deployed stack. A failure is an incident, not a note.

| # | Test | Expected | Owner of the fix |
|---|---|---|---|
| 1 | `docker compose up` on a clean machine | All services healthy, dashboard loads | Ebube |
| 2 | Reset, then play at default speed | Same scenario every time; a unit turns red between 20 and 40 s | Olise (scenario), Ebube (simulator) |
| 3 | Live predictions vs `oof_predictions.parquet` on clean data | Match within a tiny tolerance | Olise |
| 4 | Kill sensor on a healthy unit | Grey + wrench, no call, prediction continues, `confidence: low` | Olise, Ebube, David |
| 5 | A call rings on `/field`, technician says "not before Friday" | Plan changes on the dashboard within 3 s of the tool call; decision log shows the chain | All |
| 6 | Post-call webhook | Transcript and summary appear within 60 s; if the webhook is blocked, the pull fallback fills them | Ebube |
| 7 | Move an Impact slider | Result updates in under 1 s | Olise, Ebube, David |
| 8 | Decline or ignore the call | Backup technician rings after 30 s, then a manager alert | Ebube |
| 9 | Press **simulate call** with ElevenLabs unreachable | Same plan change and log entries as a real call | Ebube, David |
| 10 | Restart `engine` and `api` mid-run | No lost ringing call, no duplicate events | Ebube, Olise |
| 11 | Open the dashboard at 1280x720 and 1920x1080 | Readable, nothing clipped | David |
| 12 | Repo scan | No secrets committed | All |

---

## 7. Things nobody has been assigned yet (claim them)

| Item | Suggested owner |
|---|---|
| Link the local folder to `github.com/duvtant/pipeguard`, push `docs/`, then Ebube pushes the skeleton | David, then Ebube |
| Add the Porkbun `A` record `pipeguard` pointing at the Hetzner server (Ebube gives David the IP) | David |
| Option A approval in writing from organizers (deadline tonight 11:59 PM) | David |
| Discord mentor question for the ElevenLabs Creator tier (French, credits) | David |
| A French speaker for the stage final (pre-arranged at Sunday lunch) | David |
| Demo hardware: phone for `/field`, headphones, hotspot, charger, laptop fallback | David and Ebube |
| Who answers the call as the technician in the judging room | David (decide and rehearse) |
| Architecture diagram image (one slide, one README) | David, with facts from Ebube |
| README for judges: what it is, how to run, data citation, ElevenLabs credit | David |
| Citations: NASA C-MAPSS (Saxena et al., 2008), reused starter code if any | David |
| Backup demo video and screenshots (fleet, Impact, decision log, voice call, unit detail) | David |
| Timekeeper for rehearsals | Anyone, assign it |

---

## 8. How to brief your coding agent

Give the agent, in this order: this file, your own guide, then `techstack.md`. A good first prompt:

> You are helping me build PipeGuard. Read `docs/delegation/00_TEAM_CONTRACT.md`, then `docs/delegation/<my guide>`, then `docs/techstack.md`. I own only the files my guide lists. Do not invent architecture. If something is missing, add it to `techstack.md` section 19 and use the stated default. Start with the first item in my guide's build order, write tests for the edge cases it lists, and tell me when it is ready for review.

Keep each agent task small: one function or endpoint, its tests, and a short note about what changed in the contract if anything.
