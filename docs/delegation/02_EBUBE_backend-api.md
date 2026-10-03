# Ebube: Backend

**You own everything that stores, moves or serves data:** the database, the historian simulator, the FastAPI service (REST, live updates, the endpoints ElevenLabs calls), the call guardrails and call state, and Docker, Caddy (HTTPS) and deployment on the Hetzner server, including the laptop fallback.

This is 20% of the score (Execution & Software Architecture) and it decides whether the demo is reliable (part of the 15% for Presentation & Demo Quality). If your layer is solid, nobody else's work fails on stage.

**Read first:** `00_TEAM_CONTRACT.md`, then this file, then `docs/techstack.md` sections 4, 8, 9, 10, 11, 12.6, 12.7, 14, 15 and 16.
Repo: https://github.com/duvtant/pipeguard. Branches: `ebube/...`.

---

## 1. What you deliver

| # | Deliverable | Needed by | Who is waiting |
|---|---|---|---|
| 1 | Repo skeleton pushed to `main` (layout from `techstack.md` section 3), `.env.example`, `.gitignore`, Docker Compose with `db` | first 30 min | Everyone |
| 2 | `core/models.py` (schema) and `core/db.py` (sessions, NOTIFY and LISTEN helpers), `core/config.py` | first 60 min | Olise (worker), David |
| 3 | **API with fixture responses** (`api/fixtures/*.json`, `MOCK_API=1`) and `/openapi.json` | first 90 min | David (builds the dashboard on it) |
| 4 | Simulator streaming the scenario into `readings` (with full-history backfill) | about 90 min, as soon as Olise's v0 scenario lands | Olise, David |
| 5 | Real fleet, unit, events, plan endpoints and SSE on live data | Sat 12 PM checkpoint | David |
| 6 | Field endpoints, voice tool endpoints, webhook, call state machine, `alerts.py` | Sat afternoon | David (technician page), the whole voice demo |
| 7 | Test mode, admin reset, simulate-call fallback, work orders CSV | Sat afternoon | David |
| 8 | Deployed on the server behind `pipeguard.blunelabs.com`, plus the laptop fallback | Sat night | Everyone |
| 9 | `scripts/preflight` check and a one-page runbook | Sat night | David (demo) |

---

## 2. Files you own

```
core/config.py  core/db.py  core/models.py  core/alerts.py
api/            main.py, deps.py, routers/ (fleet, plan, simulate, voice, field, webhooks, testmode, admin), fixtures/
simulator/      worker.py
infra/          docker-compose.yml, db/init.sql, seed.py, nginx/, Caddyfile, DEPLOY_HETZNER.md
scripts/        preflight, reset
```
You **import** (never edit) Olise's pure functions from `core/` (`scheduler`, `simulate`, `feedback`, `risk`, and so on). If the signature is wrong or a field is missing (for example the scheduler diff), tell Olise. David owns `web/`, `infra/elevenlabs/` and `infra/recorded_call.json`.

---

## 3. Setup

- Python 3.11. One image for `api`, `engine`, `simulator` (different `command`s). Base `python:3.11-slim`. **LightGBM needs OpenMP on Linux**: install `libgomp1` in the image (`apt-get install -y --no-install-recommends libgomp1`), or the engine fails at import.
- PostgreSQL 16.
- Libraries: **FastAPI 0.135 or newer** (needed for the native `fastapi.sse.EventSourceResponse`; check `pip show fastapi`), `uvicorn`, `sqlmodel`, `psycopg[binary]` (psycopg 3), `httpx`, `elevenlabs` (the official Python SDK, for webhook signature verification), `dateparser`, `pydantic-settings`, `pytest`.
- Database URL: `postgresql+psycopg://...` (SQLAlchemy 2 uses psycopg 3 with this prefix, for both sync and async).
- Pin exact versions in one `requirements.txt` shared with Olise.
- **Architecture gotcha:** the server is probably x86 and the laptop fallback may be an Apple Silicon Mac. Do **not** build once and copy the image. Run `docker compose build` on each machine.

---

## 4. Build order

1. Skeleton, Compose with `db`, schema, seed, `/api/health`.
2. API with fixtures so David is unblocked.
3. Simulator + backfill + clock, writing `readings` and sending `NOTIFY new_day`.
4. Real read endpoints and SSE (once Olise's engine writes predictions).
5. Voice: field endpoints, tool endpoints, webhook, call state, guardrails.
6. Test mode, admin reset, simulate-call, work orders, `/api/simulate`.
7. Deploy on Hetzner: Caddy, nginx, healthchecks, laptop fallback, preflight.

---

## 5. Database (`core/models.py`)

Schema is in `techstack.md` section 10. Notes:

- Use `SQLModel` tables and `create_all` at startup (no Alembic; a reset recreates everything). Keep timestamps in UTC (`timestamptz`).
- Additions from the v2 spec: `sim_state.epoch`, `units.life_start_day`, `call_requests.attempt` and `ring_expires_at`, and **negative `readings.sim_day`** for backfilled history.
- **Indexes:** `readings` PK `(unit_id, sim_day)`; `predictions` `(unit_id, sim_day DESC)` and PK `(unit_id, sim_day)`; `events(id)` and `(unit_id, id)`; `call_requests(state, ring_expires_at)`.
- **Idempotency by constraint:** `predictions` upsert on `(unit_id, sim_day)`; `calls` upsert on `conversation_id` (unique); `quality_flags` one open row per `(unit_id, sensor, flag_type)`; `constraints` unique on `(unit_id, technician_id, earliest_day, call_request_id)` or equivalent.
- **`/api/fleet` must be fast** (under about 100 ms for 100 units): get each unit's newest prediction with `DISTINCT ON (unit_id) ... ORDER BY unit_id, sim_day DESC`, or a view. Test it with the backfilled data loaded.
- Seed (`infra/seed.py`): stations, 100 units from `scenario.json` (with `life_start_day`), 12 technicians (names, station, shift, `field_page_id` slugs, language, at least one French speaker, 1 or 2 flagged `is_backup`), `engine_params` (threshold from Olise's tuned value), `sim_state` at day 0, planted faults, the backfilled readings via `COPY` (about 30,000 rows; use psycopg `copy`, not row-by-row inserts).
- **Reset must be one safe operation** (`POST /api/admin/reset`): set `status = paused` and bump `epoch`, then in **one transaction** truncate run-scoped tables (`readings`, `quality_flags`, `predictions`, `plan_items`, `constraints`, `call_requests`, `calls`, `feedback`, non-planted `faults`, `events`) and reseed. Workers compare the epoch and drop stale work. Same scenario, same seed, same result. Test: reset three times and diff the seeded tables.

---

## 6. Simulator (`simulator/worker.py`)

Plays the customer's data historian. Spec in `techstack.md` section 8; the points below are the traps.

- **Owns the clock.** `sim_state` holds `sim_day`, `status`, `speed_seconds_per_day` (0.25 to 5, default 1). The dashboard controls it through `POST /api/clock`; you receive it via `NOTIFY clock_cmd` and also poll `sim_state` every 250 ms as a safety net.
- **Pace with a monotonic clock**, scheduling each tick against a target time (`time.monotonic()`), not `sleep(speed)` after the work (that drifts). If the tick is late, do not burst-catch-up: skip ahead and stay on schedule.
- **Per tick:** for every non-failed unit write one reading in **one bulk insert and one transaction**, then commit, then `NOTIFY new_day, '<sim_day>'` (a NOTIFY becomes visible to listeners only at commit, so notify after the commit).
- **Source cycle:** `cycle = sim_day - life_start_day + 1`. The unit's reading comes from NASA engine `source_engine` at that cycle.
- **End of life:** when the cycle is past the engine's last row, the unit has failed: write one `failure` event (critical, with the unit and day), mark `units.status = failed`, stop its readings, and never write that event twice (idempotent on restart).
- **Full-history backfill:** at seed/reset, write every cycle before `start_offset` at negative `sim_day`. Olise's live-equals-cross-fitted test depends on this.
- **Faults:** read from `faults` (planted plus toggled) and apply them while writing the reading:

  | Type | Behaviour |
  |---|---|
  | `dead` | Write null for the sensor |
  | `stuck` | Repeat the last good value from before the fault started |
  | `spike` | Add about 10 x the sensor's training std on one reading |
  | `out_of_range` | Write a physically impossible value (for example training max + 10 x std) |

  The stds come from `ml/artifacts/feature_config.json`. A fault has `start_day` and an optional `end_day`. Applying faults must never change history that was already written. Ignore faults on failed units. A toggle for a fault that is already open on the same unit and sensor does nothing (idempotent). Unknown sensor or unit returns 422 from the API.
- **Deterministic:** no `random` without the scenario seed; no wall-clock values in readings.
- **Reset:** on `epoch` change, drop in-flight work and reload the scenario.
- **Fast-forward for tests:** support `POST /api/clock {action: "advance", days: N}` and `speed_seconds_per_day = 0` (as fast as possible). You and Olise need this to verify "a unit turns red between 20 and 40 seconds" without waiting.
- **Scenario end:** when every unit has failed or the scenario's last day is reached, pause and write an info event.

---

## 7. Messaging between processes

| Channel | Sender | Receiver | Payload |
|---|---|---|---|
| `new_day` | simulator | engine | `sim_day` |
| `ui_event` | engine, api | api (SSE relay) | `event_id` |
| `clock_cmd` | api | simulator | `play`, `pause`, `speed`, `reset`, `advance` |

Rules (from the psycopg 3 docs and Postgres behaviour):
- The listener must be a **dedicated connection in autocommit mode**, not one from the pool. Use one listener per process.
- Use **one receiving method only** (the `conn.notifies()` generator **or** a handler, not both).
- A NOTIFY payload is limited to about 8,000 bytes, so send **IDs only** and read the row. Notifications sent inside a transaction arrive on commit.
- **Notifications are lost while a listener is disconnected.** On reconnect, **catch up from the table**: the engine reads rows newer than its last processed `sim_day`, the SSE relay reads events newer than its last `event_id`. Reconnect with backoff and log it.
- Treat every message as at-least-once (duplicates are possible, so every consumer is idempotent).

---

## 8. API (`api/`)

Endpoints: `techstack.md` section 11. Response shapes: contract section 4.3.

### 8.1 Fixtures first
Commit one JSON fixture per endpoint (`api/fixtures/`), realistic and complete (a red unit, a yellow one, a grey wrench one, a failed one, a French call with transcript, a plan change). With `MOCK_API=1` the API serves them. David builds the dashboard against them in the first hour. Keep the fixtures in sync with the contract.

### 8.2 Conventions
- JSON everywhere, OpenAPI at `/docs` and `/openapi.json`, response models defined with Pydantic (David generates TypeScript types from them).
- Sync (`def`) endpoints for database work (FastAPI runs them in a thread pool). The SSE generators and the NOTIFY listener are async.
- Single demo tenant, no user accounts. Same-origin through nginx, so no CORS needed in production (add CORS only for local Vite dev).
- Every response that David displays directly uses plain English `title` and `detail`. Never leak stack traces; return a short error body and log the trace.
- Times are UTC in the API. The UI formats them for `America/Edmonton`.

### 8.3 Live updates (SSE)
- Use FastAPI's native SSE: `@router.get("/stream", response_class=EventSourceResponse)` with `async def` yielding `ServerSentEvent(data=..., event=..., id=str(event_id))`. FastAPI sends a keep-alive comment every 15 s and sets `Cache-Control: no-cache` and `X-Accel-Buffering: no` for you.
- **One listener, many clients:** a background task owns a single `LISTEN ui_event` connection and fans the message out to per-client `asyncio.Queue`s. Do not open a Postgres connection per browser.
- **Resume:** read the `Last-Event-ID` header; on connect replay from `last_event_id - 20` (the gap risk: two writers can commit ids out of order; clients de-duplicate), then stream live. Cap a replay at 500 events.
- **Cleanup:** when a client disconnects, remove its queue (no leak). Bound each queue; if a client is too slow, drop it and let it reconnect.
- **Polling fallback:** `GET /api/events?after_id=` must give the same data (David falls back to it if SSE fails behind a proxy).
- Run `uvicorn` with a **single worker** in the demo. That keeps the in-process fan-out simple.

### 8.4 Technician (field) endpoints
`/api/field/{field_page_id}/...` (the slug is unguessable; that is the only protection, which is fine for a single-tenant demo).
- **`stream` (SSE):** on connect, immediately send any call request for this technician that is still `ringing` and not expired (a phone that connects after the ring started must still ring), then stream new `ring` events. Include `expires_at` so the page can show a countdown.
- **`answer`:** atomically move the call request `ringing -> answered` (a conditional `UPDATE ... WHERE state = 'ringing' AND ring_expires_at > now()`; if it matched no row, return a clear "call expired" answer). Then request the signed URL from ElevenLabs server side: `GET https://api.elevenlabs.io/v1/convai/conversation/get-signed-url?agent_id=...&include_conversation_id=true&environment=${ELEVENLABS_ENVIRONMENT}` with header `xi-api-key`. Store the `conversation_id` from the response on a new `calls` row (confirm the exact response field name against the live response). Return the `signed_url`, `language` and the `dynamic_variables` (all strings; contract section 4.3). Use `httpx` with a short timeout (about 3 s). On failure return a body that tells the page to show the manual fallback instead of hanging.
- **`decline`:** the same transition to `missed` and trigger the backup flow immediately.
- **`feedback`:** manual verdict fallback; same code path as the voice `feedback` tool.
- **Conversation report:** accept `POST .../conversation` with the `conversation_id` on connect and on disconnect (idempotent). The primary link between a call and a request is the `call_request_id` echoed back in the webhook's dynamic variables (see 8.6), so a missing report is not fatal.
- Never return `ELEVENLABS_API_KEY`. Never log the signed URL.

### 8.5 Voice tool endpoints (called by ElevenLabs mid-call)
`POST /api/voice/tools/{unit-status, submit-availability, field-report, feedback}`. A person is waiting on the phone, so these have strict rules.

- **Auth:** `Authorization: Bearer <VOICE_TOOL_SECRET>`, compared with `hmac.compare_digest`. Reject missing or wrong with 401.
- **Always HTTP 200 with a body the agent can speak:** `{"ok": true|false, "say": "..."}`. Bad input is `ok:false` with a spoken question, never a 4xx or 5xx (the agent cannot read a stack trace).
- **Idempotent:** the LLM may call a tool twice. The same unit, technician and resolved day within one call must not create a second constraint or a second "plan changed" event.
- **Fast:** under 1 second including the re-plan. Log the duration.
- **`submit_availability` flow:**
  1. Validate `unit_id` and `technician_id` exist and that the technician has an active (`answered`) call request for that unit (otherwise `ok:false`).
  2. Resolve `earliest_day_text` against the **simulated** calendar (`calendar_start`, today = current `sim_day`) into a `sim_day`:
     - Weekday names: "Friday" and "not before Friday" mean the next Friday **on or after today** (so on a simulated Friday it means today). "Next Friday" means the following week's Friday.
     - "today", "tomorrow", "in 3 days", "next week" (Monday), ISO dates, and French: "vendredi", "pas avant vendredi", "demain", "lundi prochain".
     - Use `dateparser` with `settings={"RELATIVE_BASE": <sim date>, "PREFER_DATES_FROM": "future"}` and `languages=["en", "fr"]`, after your own small pre-parser for weekday phrases (the library's weekday behaviour is easy to get subtly wrong). Write a table-driven test with at least 20 phrases in both languages.
     - A day in the past becomes today. A phrase that cannot be resolved returns `ok:false` with "Which day can you do?". Vague input ("sometime next week maybe") is also `ok:false`.
  3. Insert the `constraints` row (`source = voice`), write a `constraint_added` event.
  4. Take the plan advisory lock (`pg_advisory_xact_lock`), load the latest predictions, call `core.scheduler.build_plan(...)` (Olise's), write the plan diff to `plan_items`, write the `plan_changed` event, commit, `NOTIFY ui_event`.
  5. Build the `say` sentence from the scheduler's `changes` ("Got it. Unit 14 moves to Friday, and Unit 9 takes Thursday's slot."). If the scheduler marks the unit `needs_manager_decision` (the technician is free only after the unit may already have failed) say so honestly and create a `manager_alert` event.
- **`unit-status`:** current range, reason and plan for a unit, in two short sentences. **`field-report`:** store the note, add an event, set the unit's inspection note. **`feedback`:** call Olise's `adjust_threshold`, persist the new threshold in `engine_params`, write `feedback_received` and `threshold_adjusted` events; `part_replaced` resets the unit (new `life_start_day`, simulator restarts it from cycle 1).
- **Fallback when a tool call fails mid-call:** the webhook's data collection (`available_day`, `verdict`) is applied after the call and marked `received_via = webhook_fallback`.

### 8.6 Post-call webhook
`POST /api/webhooks/elevenlabs/post-call`.
- Read the **raw body** (`await request.body()`) first. Verify with the SDK: `elevenlabs.webhooks.construct_event(rawBody=..., sig_header=<elevenlabs-signature header>, secret=ELEVENLABS_WEBHOOK_SECRET)`, which also checks the timestamp and parses the JSON. Reject invalid signatures with 401 (and do not log the body).
- **Respond 200 quickly** and do the work in a background task. ElevenLabs auto-disables a webhook after 10 or more consecutive failures with no success in 7 days.
- **Idempotent** on `conversation_id` (webhooks can be retried): upsert the `calls` row.
- Link the call to its request with `call_request_id` from `data.conversation_initiation_client_data.dynamic_variables` (preferred), falling back to the conversation id you stored at `answer` time.
- Store `transcript`, `summary` (`analysis.transcript_summary`), `data_collection` (`analysis.data_collection_results`), `duration_secs`, `language`, and set `received_via`. Expose `summary_en` to the dashboard as `data_collection.english_summary` when present, otherwise the plain summary (French calls need the English one).
- Write a `call_summary` event so the decision log shows it, then `NOTIFY ui_event`.
- **Pull fallback:** if no webhook arrives within 60 seconds of the call ending (a database-backed timer, see 9), fetch `GET https://api.elevenlabs.io/v1/convai/conversations/{conversation_id}` and run the same storing code, `received_via = pull`.

### 8.7 Other endpoints
- **`/api/simulate`:** call Olise's `core.simulate` in-process. Load `oof_predictions.parquet` once at startup and keep it in memory. Run it in the thread pool, cap concurrent runs, and return `computed_ms`. Target under 1 second (David debounces the sliders).
- **`/api/impact`:** cache the last result and the headline.
- **`/api/work-orders.csv`:** this week's plan, UTF-8 with BOM so Excel opens it cleanly, `Content-Disposition: attachment; filename="work_orders_day_<N>.csv"`; columns: date, station, unit, technician, expected saving, reason.
- **Test mode:** `POST /api/testmode/faults`, `DELETE /api/testmode/faults/{id}` with `X-Admin-Token`. Validate unit and sensor.
- **Admin:** `POST /api/admin/reset`, `POST /api/admin/simulate-call`, `POST /api/admin/tune` (calls `ml/tune`, stores the result in `engine_params`). All need `X-Admin-Token`.
- **`/api/health`:** database reachable, last simulator tick age, last engine tick age, model version, `data_source` mix, ElevenLabs configured, webhook secret set. David and the preflight script read it.
- **`/api/technicians`** includes an `online` flag (whether a `/field` SSE connection is open). It is useful in the demo and costs nothing.

### 8.8 Simulate-call fallback (`/api/admin/simulate-call`)
Replays `infra/recorded_call.json` (David records a real successful call): it must go through **exactly the same code** as a real call (create the call request, answer it, run `submit_availability`, write the transcript and summary), so the plan changes and the log entries are identical. If this path diverges from the real one it is worthless as a safety net. Test 9 in the contract checks that.

---

## 9. Guardrails and call state (`core/alerts.py`)

Alert fatigue is a real problem in control rooms, so these rules are part of the pitch. Spec in `techstack.md` 7.8.

**When a call request is created** (evaluated by the engine after each tick, using your function):
- The unit is `at_risk` (already confirmed over 3 readings by Olise's `classify`). A sensor issue never triggers a call (see D1 in the contract).
- Only the **top-priority band**: among `at_risk` units without an open request, the top N (default 3) by expected saving.
- **Daily cap:** at most 3 calls per technician per simulated day (`MAX_CALLS_PER_TECH_PER_DAY`).
- **No duplicates:** no repeat call for the same unit within 3 simulated days, unless its status worsened (for example `p_fail` rose by 0.15 or more).
- **Who:** the station's primary technician; if capped or unavailable, the next on the roster. (Shifts are labels only unless you model a simulated time of day. Keep it simple.)
- Every suppression writes a quiet event or log line ("call suppressed: daily cap reached") so a judge can see the guardrail working.

**Call state machine** (`call_requests`, one row per attempt):

```
ringing --answer--> answered --call ends--> done
   |
   +--decline or ring_expires_at passed--> missed --> (attempt 2: backup technician, ringing)
                                                          |
                                                          +--missed--> escalated + manager_alert event
```
- `ring_expires_at` is real time (default 30 s). **Timers live in the database, not in process memory.** A background sweeper in the API runs every second: `SELECT ... WHERE state = 'ringing' AND ring_expires_at < now() FOR UPDATE SKIP LOCKED`, applies the transition, writes events, and sends the next ring. A restart cannot lose a ringing call.
- All transitions are **conditional updates** (compare and set), so a late `answer` after expiry fails cleanly and two sweepers cannot double-fire.
- The same sweeper handles "webhook not received 60 s after the call ended", then pulls the conversation.
- The real-time ring timers are independent of the simulated clock (pausing the clock must not freeze the countdown).
- Optional: a `pause_on_call` setting (default off) that pauses the simulated clock while a call is active.
- A call that ends without a tool call (the technician hung up) becomes `done` with no plan change, and the unit stays flagged.

---

## 10. Infrastructure

### Docker Compose (`infra/docker-compose.yml`)
| Service | Notes |
|---|---|
| `db` | `postgres:16`, named volume, `pg_isready` healthcheck |
| `api` | `uvicorn api.main:app --host 0.0.0.0 --port 8000` (one worker), healthcheck on `/api/health` |
| `engine`, `simulator` | Same image, `python -m engine.worker` and `python -m simulator.worker` |
| `web` | David's Vite build served by nginx, proxies `/api` to `api` |
| `caddy` | Public HTTPS on 80/443 for `pipeguard.blunelabs.com`; proxies to `web` (below). Profile `prod`, started with `make prod` |

- `depends_on` with `condition: service_healthy`, and `restart: unless-stopped` on every service.
- `PYTHONUNBUFFERED=1`; read config from `.env` through `pydantic-settings`; `.dockerignore` excludes `.env`, `node_modules`, `.git`, and the raw data where not needed.
- Mount `ml/artifacts` read-only into the workers.
- Warning in the runbook: `docker compose down -v` deletes the database volume. A normal reset is the admin endpoint.

### nginx (`infra/nginx/`)
- Serve the SPA with `try_files $uri /index.html` (React Router paths must not 404 on refresh, including `/field/<id>`).
- Proxy `/api/` to `http://api:8000` with `proxy_http_version 1.1`, `proxy_set_header Connection ""`, `proxy_buffering off`, and a long `proxy_read_timeout` (about 3600 s) so SSE is not buffered or cut. Pass `Host` and `X-Forwarded-*`.
- gzip for static assets, not for the event stream.

### Public HTTPS: Hetzner + Porkbun + Caddy
Full steps: `infra/DEPLOY_HETZNER.md`; details: `techstack.md` section 15.2.
- DNS stays at **Porkbun**. David adds one `A` record: `pipeguard` pointing at the server's IPv4. You give him the IP. Check with `dig +short pipeguard.blunelabs.com`.
- **Caddy** (already in `infra/docker-compose.yml` and `infra/Caddyfile`) listens on 80 and 443 and gets the Let's Encrypt certificate by itself. Run `make prod` on the server. If HTTPS fails, check `docker compose logs caddy` (usually DNS has not propagated or 80/443 is blocked).
- **Firewall:** Hetzner Cloud Firewall allows `80/tcp`, `443/tcp`, `443/udp`, and `22/tcp` from your IP only. **Docker bypasses ufw**, so compose publishes only Caddy and binds `api` and `web` to `127.0.0.1`. Never publish `db`.
- Keep the `caddy_data` volume (the certificate). Deleting it triggers re-issuance, which Let's Encrypt rate-limits.

### Laptop fallback
The same Compose file, built on the laptop (build on each machine, the CPU architectures differ). A laptop is **not reachable from the internet**, so ElevenLabs cannot call its tool endpoints: the laptop fallback runs the whole stack locally and demos with **Simulate call** (no live voice). If a live call from a laptop is ever needed, start a quick tunnel and have David update the `api_host` `backup` value with `elevenlabs environment-variables update`; your `answer` endpoint then passes `environment=${ELEVENLABS_ENVIRONMENT}` (`backup`) on the `get-signed-url` request. Test the laptop copy end to end Saturday night.

### Preflight script (`scripts/preflight`)
One command that prints green or red for: containers healthy, `/api/health` ok, scenario seeded and clock at day 0, model version, fallback artifacts present, the **public URL reachable from outside** (run `curl` against `https://pipeguard.blunelabs.com/api/health` over the hotspot), ElevenLabs key and agent id valid, webhook secret set, tool secret set, no `.env` in the git index. David runs it before every rehearsal and before the pitch.

### Secrets
`ELEVENLABS_API_KEY`, `VOICE_TOOL_SECRET`, `ELEVENLABS_WEBHOOK_SECRET`, `ADMIN_TOKEN` exist only in `.env` on the server and laptop. Never in the repo, the image, logs or `VITE_` variables. Scan history before the submission (the repo is public). Rotate anything that was ever pasted into the group chat.

---

## 11. Edge cases checklist

| Area | Case | Expected |
|---|---|---|
| Clock | Pause during a tick | The tick finishes, then pauses; no half-written day |
| Clock | Reset while the engine is mid-tick | The epoch changes, stale work is dropped, no rows from the old run appear |
| Clock | Speed 0.25 s/day with 100 units | Tick stays on schedule; engine coalesces if behind |
| Clock | Scenario ends | Pauses with an info event |
| Messaging | Listener disconnects | Reconnects with backoff and catches up from the tables |
| Messaging | Same `new_day` delivered twice | No duplicate rows or events |
| Restart | `api` restarts mid-call | A ringing request is still ringing, timers continue, the webhook still arrives |
| Restart | `engine` restarts | Resumes from the last processed day |
| SSE | Browser reconnects | Resumes with no missed events; duplicates dropped client-side |
| SSE | 10 clients connected | One Postgres listener, memory stable |
| Voice | Tool called twice with the same input | One constraint, one plan change |
| Voice | Tool called after the call ended or for the wrong unit | `ok:false` with a spoken line, no write |
| Voice | "Friday" said on a simulated Friday | Resolves to today |
| Voice | French "pas avant vendredi" | Resolves correctly |
| Voice | Day beyond the unit's remaining life | Constraint stored, unit marked needs manager decision, manager alert, honest `say` |
| Call | Technician never answers | After 30 s the backup rings; after 30 s more a manager alert |
| Call | Answer arrives after expiry | Clean "call expired" response |
| Call | Phone connects after the ring began | Still rings, with the remaining time |
| Call | Technician at the daily cap | Next technician is used, suppression logged |
| Webhook | Bad signature | 401, nothing stored |
| Webhook | Retry of the same conversation | Same single row |
| Webhook | Never arrives | Pull after 60 s |
| ElevenLabs | Signed URL request fails or is slow | Page gets a manual-fallback response within about 3 s |
| Faults | Same toggle clicked twice | One open fault |
| Faults | Fault on a failed unit | Ignored |
| Plan | Engine and API re-plan at once | Advisory lock serialises them; no interleaved writes |
| Data | Predictions missing for a unit (engine fell back) | Fleet still returns the unit with `data_source: fallback` |
| Deploy | Server down | Laptop works with the same data and scenario |
| Security | Tool endpoint without the bearer secret | 401 |
| Security | Admin or test endpoint without the token | 401 |

---

## 12. Tests and acceptance

Write these with `pytest` against a test Postgres (the Compose `db`):
- Day resolver table (20 or more phrases, English and French, including Friday-on-Friday).
- `submit_availability` idempotency and its failure paths.
- Call state machine transitions, including expiry, backup and escalation, driven by changing `ring_expires_at` instead of waiting.
- Webhook: valid signature, bad signature, replay, link by `call_request_id`.
- SSE replay and reconnect (`Last-Event-ID`).
- Reset determinism (three resets, identical seeded tables).
- Fault application for all four types and idempotent toggles.
- A smoke test that boots the stack, fast-forwards to the first red unit, and checks the fleet endpoint.

**Acceptance (from `techstack.md` section 17.4, your parts):**
- [ ] `docker compose up` starts all services on the server and the laptop
- [ ] Reset produces the same scenario every time
- [ ] At default speed a unit turns red between 20 and 40 seconds in (with Olise's scenario)
- [ ] A spoken answer changes the plan on the dashboard within 3 seconds of the tool call
- [ ] Transcript and summary appear in the decision log within 60 seconds of call end (webhook or pull)
- [ ] Impact sliders return in under 1 second
- [ ] Simulate-call produces the same log entries as a real call
- [ ] Preflight passes from outside the network (phone hotspot)
- [ ] No secrets in the repo

## 13. Mistakes to avoid
- Opening a Postgres connection per SSE client, or listening on a pooled connection.
- Sending `NOTIFY` before the commit that makes the data visible.
- Timers held in memory.
- Returning 4xx or 5xx from a voice tool.
- Letting the simulate-call fallback take a different code path than a real call.
- Publishing `api`, `db` or `web` on a public interface. Docker bypasses the host firewall: bind them to `127.0.0.1` and expose only Caddy.
- Building the image on one CPU architecture and running it on another.
- Forgetting `libgomp1` (the engine crashes on import of LightGBM).
- Putting a secret in a `VITE_` variable or in the repo.

When you are blocked or something in the docs looks wrong, add it to `techstack.md` section 19 and tell the group.
