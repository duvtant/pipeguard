# David's Phase Plan: setup to a fully running, submitted product

**Scope:** only *your* lane: the manager dashboard, the technician phone page, the ElevenLabs voice agent (and the LLM test), the pitch, and the submission. Olise's engine and Ebube's backend have their own guides. This plan is built so you can finish almost everything **without waiting** for them, then integrate.

Read with: `00_TEAM_CONTRACT.md` (shapes and schedule) and `03_DAVID_dashboard-voice-pitch.md` (detail). This file is the **ordered runbook and live tracker**.

**The shape of the plan:** Setup → **Design (yours)** → Build → Integrate and ship. Design comes *before* the screens are built, because layout, hierarchy and the status system are design decisions, and they are cheaper to get right once than to rework. Phase 2 is where you lead.

**Legend:** 🤖 AUTO = code, scripts or Claude does it · ✋ **MANUAL** = only you can do it (accounts, keys, third-party consoles, decisions, taste) · ⬜ todo · 🟦 in progress · ✅ done · ⛔ blocked

**Hard anchors (Mountain Time):** Sat 12:00 PM team checkpoint · **Sat 7:00 PM feature freeze** · **Sat 11:59 PM Option A confirmation** · Sun 8 to 10 AM rehearsal and video · **Sun 11:00 AM submit** · Sun 12:00 PM hard stop.

---

## Task tracker (kept current as work happens)

> Claude updates this table while working. If a task's status here disagrees with reality, tell Claude and it gets fixed. Last updated: **Sat Oct 3, 04:10 AM MDT** (Phase 1 complete; Phase 2 is yours to start).

### Phase 1: Setup and foundations
| ID | Task | Who | Status | Notes |
|---|---|---|---|---|
| P1.0a | Repo scaffold (backend stubs, Docker, web app) pushed to GitHub | 🤖 | ✅ | `4963017` |
| P1.0b | Delegation guides, rubric-driven README, handbook cross-check | 🤖 | ✅ | `0dc9918`; README still has `[FILL]` placeholders |
| P1.0c | Doc and package research; guides corrected (SDK 1.16 usage, environment-variable failover instead of a second agent) | 🤖 | ✅ | See "Verified facts"; **corrections not yet committed** |
| P1.1 | Tell organizers about Option A (written, kept) | ✋ | ✅ | Confirmed by you |
| P1.2 | ~~Point the domain at the server~~ **Moved to Phase 4 (deployment, yours, at the end)** | ✋ | ⏭ | Not needed for Phase 1; the agent config can reference the future URL |
| P1.3 | ElevenLabs account and credits | ✋ | ✅ | One production key (Creator, active, 131,000 credits). No separate testing account: the LLM test will spend production credits, so run it sparingly |
| P1.4 | API key into `.env` | ✋ | ✅ | Verified against the API; git-ignored |
| P1.5 | Generate `VOICE_TOOL_SECRET` and `ADMIN_TOKEN` | ✋ | ✅ | Both set and different. Handing them to Ebube happens at deployment |
| P1.6 | Install ElevenLabs CLI and log in | 🤖 + ✋ | ✅ | CLI 1.4.0 installed; authenticates from `ELEVENLABS_API_KEY` in `.env` (verified with `agents llm list`) |
| P1.7 | Mock layer, test runner, types pipeline (no visual choices yet) | 🤖 | ✅ | 22 tests pass, build passes. REST mocks verified; **SSE mock streams not yet verified in a browser** (extension was offline): open `pnpm dev:mock` |
| P1.8 | Fixtures and temporary TypeScript types from the contract | 🤖 | ✅ | 100 units + the edge cases; Technician and Call shapes are **not in the contract yet**, confirm with Ebube |
| P1.9 | Voice agent created as code | 🤖 | ✅ | Live and verified by reading it back: id `agent_0201m40dhg4pfdqaq537zb3ckdrv`, signed-URL auth on, overrides on, 120 s cap, 4 data-collection fields, 10 variable defaults. LLM is still the placeholder `gemini-3.8-flash`. **French is not set up yet** (see notes) |
| P1.10 | Agent tools, secret, environment variable, post-call webhook | 🤖 | ✅ | Secret `pipeguard_voice_tool_auth`, variable `api_host`, 4 tools (all read back and verified), `end_call` enabled, webhook created and linked, signing secret saved to `.env`. Nothing is reachable until the server is deployed (Phase 4) |
| P1.11 | First spoken test call with a hand-minted signed URL | 🤖 + ✋ | ✅ | You confirmed it works |
| **CP1** | **Checkpoint 1: passed**, with three carry-overs below | | ✅ | Secrets scan clean (118 files); agent status OK |

### Phase 2: Design (you lead)
| ID | Task | Who | Status | Notes |
|---|---|---|---|---|
| P2.1 | **You design** Fleet, Impact and the phone page, plus the status system: hierarchy, layout, look. Any tool you like | ✋ | ⬜ | Claude does not make taste decisions |
| P2.2 | Starting points on request only: screen briefs, directions, references | 🤖 | ⬜ | Only if you ask |
| **G1** | **Gate 1: you hand Claude the spec** (direction, status system, layouts) | ✋ | ⬜ | |
| P2.3 | Design tokens in code from your spec; style-guide route | 🤖 | ⬜ | No UI library is required |
| P2.4 | Fleet, Impact and phone page built to your spec on fixtures (the vertical slice) | 🤖 | ⬜ | |
| P2.5 | Accessibility baseline: contrast, colour-blind check, text size | 🤖 | ⬜ | |
| **G2** | **Gate 2: you review the three screens; the design system is frozen** | ✋ | ⬜ | |
| **CP2** | **Checkpoint 2** | | ⬜ | |

### Phase 3: Build
| ID | Task | Who | Status | Notes |
|---|---|---|---|---|
| P3.1 | App shell: providers, one shared event stream, mock on/off switch | 🤖 | ⬜ | Track A (screens) |
| P3.2 | Wire Fleet, unit drawer and Impact to the data layer | 🤖 | ⬜ | Track A |
| P3.3 | Plan, Decision log, Roster, Work orders, Settings | 🤖 | ⬜ | Track A, in the frozen design system |
| P3.4 | Test mode (admin-gated) | 🤖 | ⬜ | Track A |
| P3.5 | Phone page: real voice session, edge cases | 🤖 | ⬜ | Track A |
| P3.6 | Agent test suite (14 scenarios) as code + run per candidate LLM | 🤖 | ⬜ | Track B (voice), independent of design |
| P3.7 | Live latency calls, 5 per finalist | ✋ | ⬜ | Track B, you speak on a phone |
| P3.8 | Pick the LLM; write `docs/llm_test_results.md`; update agent config | 🤖 + ✋ | ⬜ | Track B, you approve |
| **G3** | **Gate 3: you review every screen once; list of fixes** | ✋ | ⬜ | |
| P3.9 | Fix pass from Gate 3 (fixes only, no new directions) | 🤖 | ⬜ | Done before the 7 PM freeze |
| **CP3** | **Checkpoint 3** | | ⬜ | |

### Phase 4: Integrate, run in production, rehearse, submit
| ID | Task | Who | Status | Notes |
|---|---|---|---|---|
| P4.1 | Switch mocks off, regenerate types from the real API, fix shape drift | 🤖 | ⬜ | Needs Ebube's API |
| P4.2 | Real event stream and field endpoints | 🤖 | ⬜ | Needs Ebube |
| P4.3 | ElevenLabs production wiring: tool secret, environment variable, webhook | ✋ | ⬜ | |
| P4.4 | Real call from a real phone over the public URL | ✋ | ⬜ | |
| P4.5 | Record the real call → `infra/recorded_call.json` | 🤖 + ✋ | ⬜ | |
| P4.6 | Freeze and export the agent config at 7 PM | 🤖 + ✋ | ⬜ | |
| P4.7 | Fill README and deck numbers from final results | 🤖 + ✋ | ⬜ | Needs Olise |
| P4.8 | Screenshots, architecture image, backup video | ✋ | ⬜ | |
| P4.9 | Rehearse 2 to 3 times, timed | ✋ | ⬜ | |
| P4.10 | Make the repo public; final secrets scan | ✋ | ⬜ | |
| P4.11 | Submit the GitHub Issue | ✋ | ⬜ | **Sun 11:00 AM** |
| **CP4** | **Checkpoint 4: submitted** | | ⬜ | |

---

## Verified facts this plan relies on (checked against current docs and the installed packages)

| Topic | What is true now | Effect on the plan |
|---|---|---|
| **ElevenLabs React SDK** (`@elevenlabs/react` **1.16.0**, installed) | `ConversationProvider` plus focused hooks: `useConversationControls` (`startSession`, `endSession`, `getId`, `setVolume`), `useConversationStatus`, `useConversationMode`, `useConversationInput`. `startSession(options)` takes `signedUrl` **or** `conversationToken` **or** `agentId` (mutually exclusive), plus `dynamicVariables`, `overrides`, `connectionType`. The provider takes the same options as defaults and callbacks (`onConnect`, `onDisconnect`, `onError`, `onMessage`, `onModeChange`). `useConversation` still exists | Pass `dynamicVariables` and `overrides` straight into `startSession` per call; no remounting |
| **Agents as code** | `@elevenlabs/cli` **1.4.0** (installed; it is the whole-API CLI). Auth: `elevenlabs auth login` or `ELEVENLABS_API_KEY`. `agents init / add / push / pull / status / test`, plus `tools add/push/pull`, `tests add/push/pull`, `environment-variables create`, `webhooks create`, `agents secrets`. `agents add` **always uploads** (no local-only flag). Files: `agents.json`, `tools.json`, `tests.json`, `agent_configs/`, `tool_configs/`, `test_configs/`. Real config keys confirmed from `agents templates show default`: `platform_settings.auth.enable_auth`, `platform_settings.overrides.conversation_config_override.agent.{first_message,language}`, `conversation_config.agent.dynamic_variables.dynamic_variable_placeholders`, `platform_settings.workspace_overrides.webhooks.post_call_webhook_id` | The agent lives in the repo and can be rebuilt in another account. The CLI documents **no test-run command**, so tests run via the API |
| **Environment variables** | Per-environment values (`production`, others optional). Reference as `{{system__env_<label>}}` in tool URLs, headers and webhook URLs; the URL must start with `https://` before the variable. Chosen at conversation start with an `environment` parameter (on `get-signed-url`, and an `environment` option in the React SDK). Falls back to `production` | One agent, environment `backup` points tool URLs at `pipeguard-backup.blunelabs.com` |
| **Signed URL** | `GET /v1/convai/conversation/get-signed-url?agent_id=…` with optional `include_conversation_id`, `branch_id`, `environment`; valid 15 minutes | Ebube adds the `environment` parameter |
| **Agent testing** | Tool-call, scenario and simulation tests; `POST /v1/convai/agents/{id}/run-tests` with `repeat_count` and `agent_config_override` (LLM per run). `simulate-conversation` is **deprecated, removed Oct 31, 2026** | Use run-tests only |
| **LLM ids** (from `elevenlabs agents llm list`, 107 models on this account) | ElevenLabs-hosted: `deepseek-v41-flash`, `glm-52`, `qwen36-35b-a3b`, `qwen35-397b-a17b`. OpenAI: `gpt-6-luna`, `gpt-6-sol`, `gpt-5.4-mini`, and more. Google: `gemini-3.8-flash` (reasoning cannot be turned off, minimum `low`), `gemini-3.6-flash`, `gemini-3.1-flash-lite`. Anthropic: `claude-haiku-4-5`, `claude-sonnet-5`. Several older ids are flagged deprecated, **including the CLI template's default `gemini-2.5-flash`** | GLM 5.2 is `glm-52`. Test shortlist is in `techstack.md` 12.10. Note each model's allowed `reasoning_effort` values |
| **Frontend** | React 19, Vite 8, Tailwind 4 via `@tailwindcss/vite`, TanStack Query 5, React Router 7, Recharts 3 (all installed and building). No UI component library is installed or required | Components and styling are your Phase 2 decision |
| **Mock SSE** | **MSW 3.0.1** (installed; the docs and examples online are mostly 2.x). `sse()` from `msw/sse` is browser only: it **throws if constructed in Node**, so SSE handlers live in their own file. The start option is `onUnhandledFrame` (renamed from `onUnhandledRequest`). `vitest` still lists msw `^2` as a peer; harmless because we use MSW directly | REST mocks are tested in Node; the streams are checked in the browser with `pnpm dev:mock` |
| **FastAPI SSE** | Native `EventSourceResponse` (0.135+), 15 s keep-alive, `Last-Event-ID` | Client reconnects with the header and de-duplicates by `event_id` |
| **Not confirmed by the docs** | Exact config-file keys for tool headers, secrets, parameter value sources and environment variables inside `agent_configs/` and `tool_configs/`; the tool response timeout and pre-tool speech options | Do it once in the dashboard, then `elevenlabs agents pull` to capture the real shape into the repo, rather than guessing a schema |

---

# PHASE 1: Setup and foundations

**Goal:** every account, key, tool and the agent skeleton exist, and there is realistic fixture data to design against. Nothing here involves a visual choice.
**Target window:** now through about 9 AM Saturday (about 2 hours of active work). You can stop after the ✋ items tonight and let Claude do the 🤖 items while you sleep.

### P1.1 ✋ **MANUAL**: confirm Option A with the organizers
**Why:** the handbook says Option A needs organizer validation of the problem and dataset by end of day Saturday, and that **unconfirmed selections default to the team being forfeited**. This is the single most expensive thing to forget.
**Do:** email `nagusubra@ieee.org` or DM an organizer on the event Discord (`discord.gg/w2MGxwzb9`). Send: team name and members, stream *Energy and Infrastructure Systems*, **Option A**, the one-line problem ("predictive maintenance for gas turbines that drive pipeline compressor stations"), the dataset (NASA C-MAPSS FD001, public, already in the hackathon repo) and the baseline. Ask for written confirmation. Screenshot the reply for the README's *Option A organizer approval* line.

### P1.2 ✋ **MANUAL**: point `pipeguard.blunelabs.com` at the Hetzner server
**Why:** ElevenLabs runs on its own servers and has to reach our backend over the internet during a call, both to run our tools ("change the plan to Friday") and to deliver the transcript afterwards. A DNS `A` record is the phone-book entry that sends the name `pipeguard.blunelabs.com` to the server. Caddy (a small web server in our Docker setup) then serves it over HTTPS, with the certificate handled automatically.
**Do:** get the server's public IPv4 from Ebube. At Porkbun, open the DNS records for `blunelabs.com` and add: Type `A`, Host `pipeguard`, Answer `<the IP>`, TTL 600. Make sure no URL-forward or parking record exists for that host. Check with `dig +short pipeguard.blunelabs.com` (it should print the IP; it can take a few minutes). Ebube must also allow ports 80 and 443 in the Hetzner firewall (see `infra/DEPLOY_HETZNER.md`).

### P1.3 ✋ **MANUAL**: ElevenLabs accounts and credits
**Why:** you have three accounts. The production demo agent must live in one; all messy testing (the LLM test spends credits quickly) belongs in another.
**Do:** redeem the free Creator tier through the ElevenLabs Discord (`#coupon-codes`, "Start Redemption", event "Industry Hackathon", registration email) on each account. Note each account's credit balance. Decide and write down: **account A = production**, **account B = testing**.

### P1.4 ✋ **MANUAL**: API keys into `.env`
**Why:** the CLI, your smoke tests and Ebube's backend all need keys. Keys in the repo would be public.
**Do:** create an API key in each account. Copy `.env.example` to `.env` and set `ELEVENLABS_API_KEY` (account A). Put account B's key in `.env.dev` (already git-ignored by `.env.*`). Ebube gets the production key privately, **not in the group chat**.

### P1.5 ✋ **MANUAL**: generate the shared secrets
**Why:** `VOICE_TOOL_SECRET` is the bearer token ElevenLabs sends to our tool endpoints (without it anyone could change the plan); `ADMIN_TOKEN` protects reset and Test mode.
**Do:** `openssl rand -hex 32` twice. Put both in your `.env`, and send them to Ebube privately.

### P1.6 🤖 + ✋ install the ElevenLabs CLI and log in
**Why:** agents-as-code means the agent's prompt, voice and settings are files in the repo (reviewable, rebuildable in another account, safe against 3 AM dashboard accidents).
**Auto:** `npm install -g @elevenlabs/cli` (or `brew install elevenlabs/tap/elevenlabs`), then `elevenlabs auth status`.
✋ **MANUAL:** `elevenlabs auth login` opens a browser, or set `ELEVENLABS_API_KEY` in your shell. Use `! elevenlabs auth login` in the Claude prompt to run it in-session.

### P1.7 🤖 mock layer, test runner and types pipeline
**Why:** these let you build and look at every screen before the backend exists. They contain **no visual choices**, so they are safe to do before Phase 2.
**Auto:** **MSW 2** with `sse()` for the event stream (`pnpm add -D msw`, `pnpm dlx msw init public/ --save`), a `VITE_MOCK=1` switch so the same code runs against mocks or the real API, `vitest` and React Testing Library for the few things worth testing (event de-duplication, the Impact debounce). `openapi-typescript` is already installed (`pnpm gen:api` once Ebube's API exists). No UI component library is installed on purpose: how things look is your Phase 2 decision.

### P1.8 🤖 fixtures and temporary types
**Why:** the contract (`00_TEAM_CONTRACT.md` §4.3) fixes the JSON shapes. Hand-written types and fixtures let you build now, and give Phase 2 **real content to design against** (a design is judged on real states, not lorem ipsum).
**Auto:** `web/src/lib/types.ts` (FleetUnit, UnitDetail, PlanItem, EventMsg, SimulateRequest/Response, RingEvent, AnswerResponse), and `web/src/mocks/fixtures/` covering the interesting cases: a red unit, a yellow one, a grey-wrench one, a red-with-wrench one, a failed one, a plan change, a French call with transcript and English summary, a missed call and escalation.

### P1.9 🤖 create the agent as code
**Why:** the agent is your biggest independent block and the heart of the demo, and it does not depend on how anything looks.
**Auto:** `elevenlabs agents init`, `elevenlabs agents add "PipeGuard Dispatcher" --template minimal`, then edit the generated JSON in `agent_configs/`: the system prompt (`03_DAVID...` §5.4), `temperature` 0, `max_duration_seconds` 120, English plus French with a first message per language (§5.3), a voice per language, a placeholder `llm` (final choice is P3.8). Preview with `elevenlabs agents push --dry-run`, then `elevenlabs agents push`.

### P1.10 🤖 + ✋ tools, secret, environment variable, webhook
**Why:** this wires the agent to our backend: the four tools it calls mid-call, the secret that authenticates them, the variable that lets us fail over to the laptop, and the webhook that delivers the transcript.
**What is already done (in the agent config, no dashboard needed):** signed-URL auth turned on, the language and first-message override switches on, default values for every dynamic variable, the four data-collection fields, the 120 s cap.
**Auto, once you are logged in (P1.6):** the CLI can create these (`elevenlabs agents secrets`, `elevenlabs environment-variables create`, `elevenlabs tools add`, `elevenlabs webhooks create`), then `agents push` / `tools push` and `agents pull` to capture the result. Claude does this and shows you each command first. Exact flags are read from `--help` and `--dry-run`, not guessed.
✋ **MANUAL (small):** give Claude the values only you hold: confirm `VOICE_TOOL_SECRET` is in `.env` (P1.5), and say which voice you want if you do not like the default (a taste choice: listen to a few in the dashboard).
**Still unconfirmed by the docs:** the config shape for `language_presets` (per-language first message and voice) and for tool auth headers. If a push is rejected, do that part once in the dashboard and `agents pull` to capture the real shape.
**Webhook:** the URL `https://pipeguard.blunelabs.com/api/webhooks/elevenlabs/post-call` does not exist until Ebube deploys; create it now, verify it in Phase 4.

### P1.11 🤖 + ✋ first spoken call
**Why:** proves the agent speaks, listens and uses the dynamic variables, before any of our own code is involved.
**Auto:** a script mints a signed URL with `curl` (`GET /v1/convai/conversation/get-signed-url?agent_id=…` using your key) and a throwaway dev route in the web app opens a session with `startSession({ signedUrl, dynamicVariables })`.
✋ **MANUAL:** put on headphones and talk to it. Say "Thursday", then "not before Friday". The tool calls will fail (no backend yet) and that is expected; confirm the agent reacts sensibly.

**Carry-overs from Phase 1 (not blocking Phase 2):**
1. **SSE mock streams not yet checked in a browser** (the extension was offline). Do it when you open `pnpm dev:mock` in Phase 2: events should appear in the console every ~4 s.
2. **French is not set up** on the agent (needs a `language_presets` entry; see `infra/elevenlabs/README.md`). It is item 4 on the cut list. Decide later whether it is in the demo.
3. **Nothing from Phase 1 is committed or pushed yet.**

### ✅ CHECKPOINT 1 (Phase 1 is done when all of these are true)
- [ ] Written Option A confirmation received (or at least sent, with the time)
- [ ] ~~`dig` returns the server IP~~ (deployment, moved to Phase 4)
- [ ] `elevenlabs agents status` shows the agent; `agent_configs/` is committed with no secrets in it
- [ ] `pnpm build` and `pnpm dev` work; `VITE_MOCK=1` serves fixtures
- [ ] You had a spoken exchange with the agent in English (French if the account allows it)
- [ ] `git grep -nE "(sk_|xi-api-key: *[A-Za-z0-9]{8,})"` finds nothing

---

# PHASE 2: Design (you lead)

**Goal:** decide how PipeGuard **looks, reads and is organised**, then have the three screens that define the demo (**Fleet, Impact and the technician phone page**) built to your spec. When this phase ends, the design system is frozen and everything else is built inside it.
**You lead this phase.** You make the design decisions and design the screens in whatever tool and way you prefer (Figma, Pencil, paper, straight in code). Claude does not offer unrequested alternatives or make taste calls. It is on call: it can draft briefs or gather references **if you ask**, and once you hand over a spec it builds the design tokens and the screens to match, and runs the accessibility checks.
**Target window:** about 3 hours once you are up, roughly 9 AM to noon, so a Fleet screen on fixtures exists by the 12 PM team checkpoint.

### What design means here (not just paint)
Design is five decisions, and they are made **here, before screens are built**:

| Decision | The question it answers |
|---|---|
| **Hierarchy** | What does the eye hit first on each screen? Fleet: the red units. Impact: the before/after dollars and the headline sentence |
| **Information architecture** | What is on the screen, what is one click away, what is left out? |
| **Status system** | How do green, yellow, red, grey-wrench and failed read at a glance, **never by colour alone**? |
| **Visual language** | Colour, type, spacing, density, motion: the feel |
| **Context of use** | A maintenance manager in a control room, judged on a projector at 1280x720 in seconds; a technician on a phone, outdoors, one hand |

### Principles every screen is judged by
| Principle | What it demands |
|---|---|
| **Status first** | The five statuses are distinguishable at a glance and by shape or label, not colour alone |
| **One focal point per screen** | Fleet: the red units. Impact: the before/after dollars and the headline |
| **Numbers are the hero** | Tabular numerals, consistent units and rounding, clear labels. No decorative charts |
| **Calm density** | Enough information to feel like an enterprise tool, no clutter, no boxes inside boxes |
| **Restrained motion** | A one-second highlight on change, nothing that blinks continuously |
| **Projector-proof** | About 14 px minimum text, strong contrast, no thin grey text |
| **Honest labelling** | "Simulated" and "low confidence" are visible but quiet |

### P2.1 ✋ **MANUAL**: you design
Decide and document, for **Fleet, Impact and the phone page**:
- what the eye hits first, what is secondary, what is one click away or left out;
- the status system (how green, yellow, red, grey-wrench and failed read, **never by colour alone**);
- the visual language: colour, type, spacing, density, motion;
- the states each screen must handle: empty, loading, error, reconnecting, a failed unit, low confidence.
Use fixture data from Phase 1 so you are judging real content, not lorem ipsum. A rough layout plus a short note per screen is enough, as long as Claude can build from it without guessing.

### P2.2 🤖 starting points, only on request
If you want help, ask. Claude can draft one-page screen briefs, put together references (for example from Mobbin or a Pencil file), or build a quick comparison of options on the real Fleet screen. It will not do any of this unless you ask.
Skills in this session that can help if you ask: `design-taste-frontend`, `high-end-visual-design`, `industrial-brutalist-ui`, `minimalist-ui`, `redesign-existing-projects`, `hallmark`, and `dataviz` for chart colours.

### ✋ **Gate 1: you hand Claude the spec.**
Nothing is built to a final design until you say "this is the spec".

### P2.3 🤖 design tokens in code
From your spec: colour roles and the status palette (the same five everywhere, checked for colour-blind safety and contrast), type scale, spacing, radii and elevation, as CSS variables and Tailwind theme values. A small style-guide route shows every token. No UI component library is required; shared components are built plainly on top of the tokens.

### P2.4 🤖 build the three screens to your spec, on fixtures
Fleet (tiles, clock controls, toast), Impact (policy table and chart, sliders, default vs self-tuned, headline) and the phone page (idle, ringing, in call, after call, as large touch targets), each with every state from your spec.
**Why these three first:** they are most of the demo, and building them settles the design system for real (a design that only exists in sketches hides problems).

### P2.5 🤖 accessibility baseline
Contrast check and a colour-blind simulation of the status colours, keyboard focus order, reduced-motion, text size at 1280x720. Findings come back as a list for you to decide on, not as silent changes to your design.

### ✋ **Gate 2: you review the three screens, and the design system is frozen.**
Look at them on the **real phone** and on a **large monitor or projector** at arm's length. If you cannot read a number from three metres, it fails. After Gate 2, colours, type scale and layout patterns are fixed; new screens use them instead of inventing new ones.

### ✅ CHECKPOINT 2
- [ ] You designed the three screens and approved both gates
- [ ] The style-guide route shows every token
- [ ] Fleet, Impact and the phone page are built to your spec on fixtures and handle every state in it
- [ ] Every status is distinguishable without colour; contrast passes
- [ ] They are readable at 1280x720 and on a phone
- [ ] You would put a screenshot of Fleet and Impact on a slide as is

---

# PHASE 3: Build

**Goal:** the rest of the product, built inside the frozen design system, plus the voice agent's model chosen by measurement. Two tracks run in parallel, and Track B never waits on design.
**Target window:** about noon to 6 PM Saturday, with the fix pass finished before the **7 PM freeze**.

## Track A: screens and data layer

### P3.1 🤖 app shell
One `EventSource` context for the whole app (de-duplicating by `event_id`, reconnecting with `Last-Event-ID`, falling back to polling `/api/events?after_id=`), TanStack Query with cache patching, the `VITE_MOCK` switch, an error boundary, a "reconnecting" banner and the permanent "simulated company" footer.
**Why:** 100 tiles updating each second only stays smooth with one shared stream and targeted cache updates.

### P3.2 🤖 wire Fleet, the unit drawer and Impact to the data layer
The Phase 2 screens move from static fixtures to the live data layer (still mocks until Phase 4). Unit drawer: range bar, reason, sensor charts, history, events and calls. Impact sliders call `POST /api/simulate` with a ~200 ms debounce that **cancels the previous request**.

### P3.3 🤖 Plan, Decision log, Roster, Work orders, Settings
Built from your spec, using the frozen tokens and shared components. Decision log is a chain per alert with expandable transcripts; French shows the French transcript plus the English summary.

### P3.4 🤖 Test mode
Admin-gated route (token in `sessionStorage`, never in the bundle). Kill and corrupt sensor, active faults, reset (in-page confirmation, **never** `window.confirm`), simulate call, tune now.

### P3.5 🤖 technician phone page: the real voice session
Uses the **v1.16 API**: `ConversationProvider`, `useConversationControls().startSession({ signedUrl, dynamicVariables, overrides: { agent: { language, firstMessage } } })`, `useConversationStatus`, `useConversationMode` for the speaking indicator, `getId()` posted to the API on connect. Handles the edge cases in `03_DAVID...` §4.3 (mic permission, audio-unlock tap, wake lock, dropped calls, expired ring, double-tap).

## Track B: voice agent (independent of design)

### P3.6 🤖 agent tests as code
Create the 14 scenarios from `techstack.md` §12.10 in the CLI's test configs (or via the API), with the server tools mocked and one mock returning `ok:false`. Add a small script that calls `POST /v1/convai/agents/{id}/run-tests` once per candidate with `agent_config_override` (LLM and `reasoning_effort`) and `repeat_count` 5, and prints a pass-rate table. **Run it only in account B** (it spends credits).

### P3.7 ✋ **MANUAL**: live latency calls
**Why:** text tests cannot measure speech latency, and latency is what decides whether a call feels natural.
**Do:** for each finalist, make **5 real calls** from your phone on the dev page with headphones, using the "not before Friday" line. The script reads response latency and tool round trip from each conversation's `time_in_call_secs`. Targets: median at most 1.5 s, p95 at most 3 s.

### P3.8 🤖 + ✋ pick the model
Apply the decision rule in `techstack.md` §12.10 (at least 95% on the demo-critical tests, latency targets, cheapest survivor). Write `docs/llm_test_results.md`, set the model and `reasoning_effort` in the agent config, `agents push`. ✋ **MANUAL:** you approve the choice. Never `reasoning_effort: max` on a live call (Luna at max was measured at about 80 to 110 s to first answer token).

## Review and fixes

### ✋ **Gate 3: you review every screen once.**
You look through the full product on the real phone and on a large display and write down what is wrong. This is a review of the system you already approved, so expect fixes (alignment, wording, a missing state), **not** new directions.

### P3.9 🤖 fix pass
Apply Gate 3's list. Finish before the 7 PM freeze. After the freeze, only bug fixes.

### ✅ CHECKPOINT 3
- [ ] Every page renders from mocks with no console errors; `pnpm build` passes
- [ ] No page invents its own colours, type sizes or spacing outside the design system
- [ ] The phone page shows all four states, and a real voice session works with a hand-minted signed URL
- [ ] SSE mock: killing and restoring the stream resumes with no duplicate or missing events
- [ ] Impact sliders drag smoothly with no out-of-order results (try 20 fast drags)
- [ ] `docs/llm_test_results.md` exists, with the winner and the numbers; the production agent uses it
- [ ] Gate 3's list is cleared or consciously deferred

---

# PHASE 4: Integrate, run in production, rehearse, submit

**Goal:** the real stack, the real call, the real numbers, a recorded backup, and the submission sent. Parts of this wait on Olise and Ebube; start each item the moment its dependency lands.
**Target window:** integration from the 12 PM checkpoint onward as pieces arrive; freeze at 7 PM; Saturday night full run; Sunday 8 to 10 AM rehearsal; **11 AM submit**.

### P4.1 🤖 switch to the real API
Turn `VITE_MOCK` off, run `pnpm gen:api` against Ebube's `/openapi.json`, replace the hand-written types, fix any drift between fixtures and reality. Anything missing goes to Ebube immediately, not at 6 PM.
**Why:** shape drift found now is a 10-minute fix; found at the demo it is a failure.

### P4.2 🤖 real event stream and field endpoints
Point `/field` at the real `stream`, `answer`, `decline` and `feedback` endpoints. Confirm reconnect behaviour against the real server through the public URL.

### P4.3 ✋ **MANUAL**: ElevenLabs production wiring
**Why:** this is where our backend and ElevenLabs actually meet; a wrong secret or URL means silent tool failures on stage.
**Do:** confirm the workspace secret equals Ebube's `VOICE_TOOL_SECRET`; confirm the `api_host` environment variable resolves to `pipeguard.blunelabs.com`; paste the webhook signing secret to Ebube; set Ebube's `ELEVENLABS_AGENT_ID` and key. Then make one call and check the decision log shows the transcript within 60 seconds. Also test the **backup environment**: pass `environment=backup` and confirm the tool URL resolves to the backup host.

### P4.4 ✋ **MANUAL**: real call, real phone, public URL
**Why:** microphone access, audio unlocking and the signed URL only behave like the demo on a real phone over HTTPS.
**Do:** open `https://pipeguard.blunelabs.com/field/<id>` on the phone (cellular and Wi-Fi), tap "I'm on shift", wait for the red unit, answer, say "not before Friday", and watch the plan change on the laptop within 3 seconds. Repeat in French if French is in the demo. Put the phone to sleep mid-call once to see how it recovers.

### P4.5 🤖 + ✋ record the call
**Why:** the safety net. If ElevenLabs or the Wi-Fi fails on stage, **Simulate call** replays this recording through the same code.
**Do:** make one clean successful call; 🤖 export its transcript and tool calls (`GET /v1/convai/conversations/{id}`) into `infra/recorded_call.json`; ✋ confirm Ebube's `simulate-call` produces the same log entries as the real call.

### P4.6 🤖 + ✋ freeze at 7 PM
`elevenlabs agents pull`, commit `agent_configs/` and the exported config (no secrets). ✋ **MANUAL:** agree with the team that the agent prompt, scenario and model files are frozen. Late "small tweaks" are how demos break.

### P4.7 🤖 + ✋ fill the numbers
**Why:** a README or deck number that differs from the Impact tab costs credibility.
Pull the final figures from Olise's `ml/artifacts/metadata.json` and the Impact tab, and replace every `[FILL ...]` in `README.md`. ✋ **MANUAL:** the items only you can supply: team name and captain, teammates' handles, the one real line from an industry mentor (or delete that paragraph), the video link, whether French works. `./scripts/preflight` fails until no `[FILL` remains.

### P4.8 ✋ **MANUAL**: assets
Screenshots (fleet, Impact, decision log, voice call, unit detail) at 1920 wide with no secrets visible; the architecture image (the diagram in the README is the source); the **backup video** (5 minutes max, one clean run on the laptop including the real call and the sensor kill, uploaded unlisted); the deck. Use the same palette and type as the product so the deck looks like part of it.

### P4.9 ✋ **MANUAL**: rehearse
Two or three **timed** runs of the full 5-minute pitch with a timekeeper, each starting with **Reset**. Practise the failure paths: sensor kill, French call, a missed call, **Simulate call**, switching to the laptop (run the laptop copy with Simulate call; live voice from a laptop would need a quick tunnel and the backup environment). Every Q&A answer under 20 seconds.

### P4.10 ✋ **MANUAL**: make the repo public
In GitHub: Settings → General → Danger Zone → change visibility. First run the final secrets scan (`./scripts/preflight` and a history scan, not only the working tree). **Why:** submissions are public, and a leaked key in history stays leaked.

### P4.11 ✋ **MANUAL**: submit
Open a GitHub Issue on **`nagusubra/industry-hackathon-lab`** (the main repo, not ours) with the nine fields: team name; member names and GitHub handles; stream; project title; tagline (3 lines max); about (inspiration, what you learned, how you built it, challenges); 2 to 5 screenshots; demo video or live link; optional extras (Option A approval, dataset citation, ElevenLabs as sponsor tech, link to our repo). The handbook also asks for the team captain and contact emails. **Target 11:00 AM Sunday; 12:00 PM is a hard stop with no exceptions.** Put the Issue link in the README.

### ✅ CHECKPOINT 4: submitted
- [ ] The Issue is open on the main repo, before 11:00 AM Sunday
- [ ] `./scripts/preflight` is green (public URL reachable from a phone hotspot, no `[FILL` in the README, no secrets)
- [ ] The real call works end to end on the real phone; **Simulate call** works as well
- [ ] The backup video and screenshots are saved locally and linked
- [ ] The repo is public and its history has no keys
- [ ] The Issue link is in the README

---

## How Claude keeps this plan honest

- The tracker at the top is updated **as each task is completed or blocked**, with a one-line note. Status flips to ✅ only after the checkpoint test for that task passes, not when code is merely written.
- **The design gates are hard stops.** Claude does not start the work after a gate until you have approved it. If you are not available at a gate, the dependent tasks show ⛔ with the reason, and Track B (voice) and Phase 1 work continue meanwhile.
- If work drifts outside the plan (for example a new screen no phase mentions), Claude flags it and asks whether to add it or skip it, instead of silently doing it.
- If a documented fact turns out wrong in practice (for example the config-file shape for tools), the "Verified facts" table is corrected and the affected tasks are marked.
- Items that need your hands carry ✋ **MANUAL**. If a ✋ item is open and something downstream depends on it, the tracker shows ⛔ on the dependent task and names what is blocking it.
