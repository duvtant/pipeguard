# Message to Ebube: everything the dashboard needs from the backend

**One document, kept up to date.** David sends this file; when something new comes up we add it here (and change the version line) instead of sending a new message. If you have already read an earlier version, only the items marked **NEW** or **CHANGED** below are different.

**Version:** v5 · Sun Oct 4, 2026 · **Read this first:** `00_TEAM_CONTRACT.md` is still the source of truth for anything already in it. This file lists only what the dashboard uses that the contract does not cover yet.

## READ THIS FIRST (v5): David changed three things in YOUR files on `dev`, merge `dev` into your branch before you push
These were found by running the real stack and are tested (backend 229 passed on Postgres, engine 55 passed). Please read the diffs, do not revert them:
1. **`engine/pg_store.py` `replan` (about 15 lines):** an overdue booking is now the same booking rolled forward to today. Before, past rows were never deleted and the same unit looked "new" every simulated day (a "Plan changed" event and an extra `plan_items` row per day). Regression tests are in `tests/test_engine_store.py`.
2. **`api/routers/clock.py`:** `reset` and `advance` now need `X-Admin-Token` (play, pause and speed stay open). Test in `tests/test_reads.py`.
3. **`GET/PUT /api/settings` is built** (your item 5): `core/app_settings.py`, `api/routers/settings.py`, a new `app_settings` table (added to an existing database by `core/migrate.py`). The engine, alerts and voice re-plan read it. Tests in `tests/test_settings.py`.

## (v4) how we work together from now on
**Branches.** Keep working **on your own branch** (`ebube/backend`) and keep pushing to it exactly as you do now. **Do not work on `dev` and do not push to `main`.** David is the only person who merges into `dev`, so nothing breaks while people are building.
- David is creating a `dev` branch that holds the dashboard, the voice agent setup and the updated contract and docs. **Once it is pushed, merge it into your branch one time** (`git fetch origin` then `git merge origin/dev`) so you build against the current contract (it adds the new event types and the optional items below). After that, carry on as before.
- When you push something that works, **message David**, and he merges your branch into `dev` and tests it with the dashboard. Your files and the dashboard's files do not overlap, so merges should be clean.

**Thanks, your fake API already works.** David ran it against the dashboard's expected shapes: `/api/fleet`, `/api/plan`, `/api/events`, `/api/technicians` and the unit detail match field for field. One thing is already handled on David's side: your phone stream sends a named `ring` event, and the phone page now listens for both named and unnamed events, so **you do not need to change `event: ring`**.

## READ THIS FIRST (v3): there is no feature freeze, and here is what is left
Keep building until the real deadline (Sun 11 AM). David's read of where you are: the fake API, schema and simulator are good (about 25% of the real backend). **Please build in this order and tell David as each one works:**
1. **Today: tell David which of these you will deliver**, so the demo fallback (your fake API plus the Simulate call button) is chosen early.
2. **Voice tool endpoints** (`submit-availability`, `get-unit-status`, `field-report`, `feedback`): bearer-secret check, "not before Friday" day resolver, always HTTP 200 (see guide 02, 8.5). The voice demo needs these.
3. **Post-call webhook** (signature check, save the full transcript unchanged).
4. **`core/alerts.py`** call creation, the real field stream, answer and decline.
5. **Real fleet, unit, plan, events, stream and clock endpoints** reading Olise's tables (`POST /api/clock` as well).
6. Seed `engine_params` from `ml/artifacts/metadata.json["tuned"]` (threshold 0.3, horizon 21), and run the engine and simulator together with Olise against a real database.
7. `ADMIN_TOKEN` set, deploy, real health check, preflight, tests.
8. The seven optional items below.

## The one rule that makes all of this safe
**Every item below is optional, and the dashboard switches itself on only if the API sends the field.** If something is missing, that screen simply doesn't show it (nothing fake is shown, nothing breaks). So the order below is the order of how much it adds to the demo. Do what fits. **Tell David by 6 PM Saturday which items you will skip.**

Exact shapes live in `web/src/lib/types.ts` (search "NOT IN CONTRACT YET"). A working fake backend is `web/src/mocks/handlers.ts`: read it to see precisely what each endpoint returns. Example data: `web/src/mocks/fixtures/`.

## At a glance

| # | What | Time | Why it matters | Status |
|---|---|---|---|---|
| 1 | Manager approval of plan changes | ~1 h | The "who approved that?" answer, one click | Not started |
| 2 | Manager decision when no crew is free | ~45 min | Today that warning has nothing to act on | **NEW** |
| 3 | Store the full ElevenLabs call record | ~30 min | Shows tool calls, safety stops and the report card | Not started |
| 4 | Policy checks on events | ~30 min | The log can say *why* a call was or wasn't made | Not started |
| 5 | Settings endpoints | ~20 min | The Settings page saves for real | Not started |
| 6 | Three small read endpoints (trend, model, cost series) | ~30 min | Charts on Fleet and Impact | Not started |
| 7 | Technician track record (how often warnings were confirmed) | ~15 min | Builds trust: "technicians confirmed 10 of 12 warnings" | **NEW** |

Tick the Status column as you go and tell David; he updates this file.

---

## 1. Manager approval of plan changes
**What and why:** when the voice agent changes the plan (the "not before Friday" moment), the change shows as **Proposed**, and a manager clicks **Approve** before it becomes a work order. Gas-industry judges will ask "who approved that?".

1. **New field `approval`** on every plan item: `"proposed"` or `"approved"`.
   - The seeded plan, and the plan after `POST /api/admin/reset`: everything `"approved"`.
   - When `submit_availability` moves a unit to a **different day**: that item becomes `"proposed"` (even if it was approved). Same day again: leave it unchanged (the tool is idempotent, so repeating a call must never un-approve something).
   - Items with `state = needs_manager_decision` can stay `"proposed"`; the dashboard ignores them here (see item 2).
2. `GET /api/plan` returns `approval` on every item.
3. **`POST /api/plan/{id}/approve`**: sets `"approved"`, returns the item. **Idempotent** (approving twice is fine and writes no second event). `404` if unknown.
4. **`POST /api/plan/approve-all`**: approves every `"proposed"` item (skip `needs_manager_decision`). Returns `{"approved": <count>}`.
5. **New event type `plan_approved`**, one per item approved, through the normal events table and SSE:
   `{"type":"plan_approved","unit_id":"EDS-07","title":"Plan approved","detail":"A manager approved EDS-07 for Fri, Nov 6. It is now a work order.","severity":"info"}`
6. **`GET /api/work-orders.csv`** includes **only `"approved"`** items.

**Check (30 s):** reset → every item `approved`. Simulate call → EDS-07 is `proposed`, not in the CSV. Approve it → it is `approved`, in the CSV, exactly one `plan_approved` event; approving again adds no second event.

## 2. Manager decision when no crew is free  — NEW
**What and why:** a unit with `state = needs_manager_decision` (no crew slot in 7 days) used to be a dead-end warning. The Plan page now shows a card with two buttons: **Add an overtime crew** and **Accept the risk for now**.

1. **`POST /api/plan/{id}/decide`** with body `{"choice": "overtime"}` or `{"choice": "defer"}`. Returns the updated plan item. `422` for any other choice, `404` unknown id, `409` if the item does not need a decision.
2. **`overtime`:** the item becomes `state: "planned"`, `planned_day` = tomorrow (an extra crew, so it does **not** take a normal slot), `approval: "approved"`, `decision: "overtime"`. Set the unit's `needs_manager_decision` to `false`. It appears in the CSV.
3. **`defer`** ("accept the risk for now"): the item **stays** `state: "needs_manager_decision"` and gets `decision: "deferred"`. Set the unit's `needs_manager_decision` to `false`. It is **not** in the CSV and not on the schedule.
4. A deferred item may later be switched to `overtime`. **Idempotent:** the same choice twice changes nothing and writes no second event.
5. **New optional field `decision`** on plan items: `"overtime"` or `"deferred"`.
6. **New event type `manager_decision`**, one per real change: `{"type":"manager_decision","unit_id":"EDS-14","title":"Overtime crew approved" | "Risk accepted for now","detail":"...","severity":"info","payload":{"choice":"overtime"|"deferred"}}`.

**Check (30 s):** the unit with no free crew (EDS-14 in the demo data) → `decide overtime` → plan shows it `planned` with `decision: "overtime"`, the CSV contains it, its `needs_manager_decision` flag is false, exactly one `manager_decision` event. Calling it again adds none. If you skip this item the two buttons show "Try again"; nothing else breaks.

## 3. Store the full ElevenLabs call record
**Why:** the Decision log now shows, per call, which tools the agent used, whether a safety guardrail fired, and a 4-line "report card". ElevenLabs already sends all of it in the post-call webhook; the old spec kept only `role`, `message`, `time`, which would throw it away.

1. **Store `data.transcript[]` exactly as sent** (JSON in `calls.transcript`; do not pick fields out). Each turn may carry:
   - `tool_calls`: `[{request_id, tool_name, params_as_json, tool_has_been_called}]`
   - `tool_results`: `[{request_id, tool_name, result_value, is_error, tool_latency_secs}]`
   - `triggered_guardrails`: `[{guardrail_type, guardrail_name}]`
2. **Store the report card:** take `data.analysis.evaluation_criteria_results_list` (or `evaluation_criteria_results` if the list is missing) and save it as JSON in a new column `calls.evaluation`: `[{criteria_id, result, rationale}]`, where `result` is `"success"`, `"failure"` or `"unknown"`. `null` if the call has none.
3. `GET /api/units/{id}` (inside `calls`) returns `transcript` unchanged and `evaluation`.
4. **Be tolerant:** ignore unknown fields; never reject a webhook because a field is missing or new.
5. The 60-second **pull fallback** (`GET /v1/convai/conversations/{id}`) stores the same fields; the shape is the same.

**Check (1 min):** run a call → `GET /api/units/EDS-07` → latest call has `evaluation` (4 items) and a transcript turn with `tool_calls` and `tool_results`. Dashboard → Decision log → "Show transcript" shows tool chips and the report card. Old calls without these fields still display.

## 4. Policy checks on events
**Why:** the log can show "why it was allowed to call, 5 of 5 checks passed" or "why it did not call: 1 check failed".

On `call_requested` and `manager_alert` events, put the gate's reasoning in `payload.checks`: `[{"rule": "...", "passed": true|false, "detail": "..."}]`. One entry per rule in the alert policy (`core/alerts.py`, techstack 7.8): three red readings in a row, top priority band, not a sensor problem, no repeat call within 3 days, technician under the daily limit, crew slot free. Plain-words `rule` and `detail` (the manager reads them). Example in `web/src/mocks/fixtures/events.ts` (`CALL_CHECKS`).

**Check:** an event for EDS-14 has `payload.checks` with one `passed: false` entry; Decision log shows "Why it did not call".

## 5. Settings endpoints
`GET /api/settings` and `PUT /api/settings` (merge the sent fields, return the full object):
`{"crews_per_station": 2, "cost_breakdown": 200000, "cost_service": 20000, "ring_timeout_secs": 30, "call_backup_when_missed": true, "require_manager_for_conflicts": true}`.
These should be the same values the engine and call rules actually use (`engine_params` / settings), so changing them on screen changes behaviour. No admin token (manager screen).

## 6. Three small read endpoints
All three are for charts; the charts hide themselves if the endpoint is missing. Some of the numbers come from Olise; you only serve them.
- **`GET /api/fleet/trend`** → `[{"sim_day": 29, "needing_attention": 9}, …]`, about the last 30 simulated days (units that were red or failed that day).
- **`GET /api/model`** → `{"rmse": 14.8, "baseline_rmse": 27.5, "model_version": "v1"}` from `ml/artifacts/metadata.json`.
- **`POST /api/simulate`** response gains an optional `series`: `[{"sim_day", "run_to_failure", "fixed_schedule", "pipeguard"}]`, cumulative cost per policy per simulated day (the Impact chart). Ask Olise if `core.simulate` can return it.

---

## 7. Technician track record  — NEW
**Why:** the strongest answer to "will it cry wolf?" is a visible score of how often the warnings were right. You already store technicians' verdicts (the `feedback` table).

**`GET /api/feedback/stats`** → `{"total": 12, "confirmed": 10}`.
- `total` = number of feedback rows with a verdict.
- `confirmed` = verdicts `confirmed_wear` plus `part_replaced`. `looks_fine` is a false alarm and counts only in `total`.
- No admin token. If `total` is 0 the dashboard hides the card, and if the endpoint is missing it hides it too.

**Check:** submit two verdicts (one `confirmed_wear`, one `looks_fine`) → `{"total": 2, "confirmed": 1}`. Dashboard → Impact shows "Warnings technicians confirmed: 1 of 2".

---

## Not for you (so you know what David handles)
- ElevenLabs agent settings (guardrails, report card, 30-day retention): staged in David's config files, **not pushed** until he approves and tests them. You do not need to change anything for these except item 3.
- All of the dashboard and phone page.

## Changelog
- **v4 · Oct 3 (evening):** added the branch workflow (stay on your branch, merge `dev` once), and noted the `ring` event needs no change. Everything else unchanged.
- **v3 · Oct 3 (evening):** no feature freeze; added the priority list at the top. Items 1 to 7 unchanged.
- **v2 · Oct 3 (later):** added item 7 (track record). Items 1 to 6 unchanged.
- **v1 · Oct 3:** first consolidated version. Merges the earlier plan-approval and full-call-record messages (those two files are gone) and adds items 2, 4, 5 and 6.
