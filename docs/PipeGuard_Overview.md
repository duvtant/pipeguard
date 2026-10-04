# PipeGuard: Product Overview

**Predicts which pipeline compressor turbine will fail next, schedules the fix, and calls the technician.**

IEEE YP Industry Hackathon 2026 | Energy and Infrastructure Systems | Option A (own problem statement)

---

## 1. Summary

Gas pipelines rely on compressor stations to keep gas moving. Many of those compressors are driven by gas turbines. When a turbine fails without warning, gas flow drops, crews scramble, and the operator loses money every hour.

PipeGuard is an enterprise maintenance product with two layers:

1. **The Engine:** predicts each turbine's remaining life, decides which units to service this week with limited crews, simulates the outcome, and tunes its own settings.
2. **The Enterprise App:** what a real operator logs into. A live fleet dashboard, an Impact tab, a decision log, and a voice agent (ElevenLabs) that calls technicians and re-plans from their answers.

**Proof it works (already tested on the real dataset):** a quick, untuned model cut average prediction error from **27.5 to 14.8 cycles** and caught **18 of 25** failing engines, versus **12 of 25** for the starter-style model.

---

## 2. Key decisions and deadlines

| Item | Decision |
|---|---|
| Stream | Energy and Infrastructure Systems |
| Path | Option A: our own problem statement, scored on the same rubric |
| Problem | Predictive maintenance for gas turbines that drive pipeline compressor stations |
| Data | NASA C-MAPSS FD001 turbine wear data (public, cited) |
| Demo company | Prairie Gas Transmission (fictional, clearly labelled as simulated) |
| Product name | PipeGuard |
| Demo fleet | The 100 NASA **training** engines (full run-to-failure histories), with cross-fitted predictions |
| Live data | A historian simulator streams sensor readings day by day; the engine predicts live |
| Fault handling | Data quality checks plus a fault injection Test mode (dead sensor, bad values) |
| Stack | React + FastAPI + PostgreSQL + LightGBM, two background workers, Docker Compose on our own server. Full detail in `techstack.md` |

| Deadline (MT) | What |
|---|---|
| Fri Oct 2, 11:59 PM | Send team details and chosen stream to organizers |
| Sat Oct 3, 11:59 PM | Final team details confirmed; **Option A problem and dataset approved by organizers, in writing** |
| Sun Oct 4, 11:00 AM | Our internal submission target (one hour of buffer) |
| Sun Oct 4, 12:00 PM | GitHub Issue submission closes. No exceptions |
| Sun Oct 4, 1:00 to 4:00 PM | Judging rooms: 5-minute pitch + 3-minute Q&A |
| Sun Oct 4, 4:00 PM | Stage pitches for shortlisted teams, audience vote for Fan Favourite |

### Option A requirements and how we meet them

| Requirement | How we meet it |
|---|---|
| Fits the stream theme | Pipelines are core energy infrastructure |
| Real public dataset, cited | NASA C-MAPSS FD001 |
| Named naive baseline | Fixed maintenance schedule, plus run-until-it-breaks |
| At least one plan, score, change cycle in code | Engine predicts, simulation scores, engine re-tunes its own settings |
| Named user | Maintenance team at a mid-size Alberta gas operator |
| Organizer validation by Saturday night | Request sent Friday night via Discord DM or email |

---

## 3. The problem

### How a gas pipeline works
- Natural gas loses pressure as it travels hundreds of kilometres through a pipe.
- **Compressor stations** along the line squeeze the gas back to high pressure so it keeps flowing.
- Each compressor is spun by a large driver. Very often that driver is a **gas turbine**, many of which are **aeroderivative**: jet engines adapted for ground use (for example, GE's LM2500 is derived from the CF6-6 aircraft engine and has a version built to drive pipeline gas compressors).

### What goes wrong
- A turbine wears out gradually. If no one catches it, it fails suddenly.
- **Every day counts.** PipeGuard's warnings are measured in days of remaining life, so each day a failing unit waits in a queue is a day off its window. A surprise failure turns planned work into emergency work (premium parts, overtime, lost flow).
- When it fails, that station stops pushing gas. Flow drops, customers and power plants downstream can lose supply, and the operator pays for emergency repairs and lost throughput.

### How it is handled today
- **Fixed schedule:** service every unit every N days. Wastes work on healthy units and still misses units that wear out early.
- **Run until it breaks:** cheapest until the breakdown, which is the most expensive outcome.

### Who has the problem
- **Maintenance manager:** plans each week's work with limited crews and must justify spend.
- **On-call field technician:** does the work, often far from the office, needs clear, short instructions.

---

## 4. Product at a glance

```
NASA turbine sensor data
        |
        v
  Historian simulator (streams readings day by day, applies faults)
        |
        v
+----------------- THE ENGINE -----------------+
| Quality check -> Predict -> Explain ->        |
| Decide -> Simulate                            |
|        ^                          |           |
|        +-- Self-tune / Re-plan / Feedback ----+
+-----------------------------------------------+
        |                       ^
        v                       |
+----------- THE ENTERPRISE APP ----------------+
| Fleet dashboard | Impact tab | Weekly plan    |
| Decision log    | Roster     | Work orders    |
+-----------------------------------------------+
        |                       ^
        v                       |
   ElevenLabs voice agent  <--> Technician
   (alert call, answer, field report, feedback)
```

---

## 5. Data sources

### Real public data
**NASA C-MAPSS FD001** (Turbofan Engine Degradation Simulation), bundled in the hackathon repository.

| File | Contents |
|---|---|
| `train_FD001.txt` | 100 engines run from healthy to failure, 20,631 rows |
| `test_FD001.txt` | 100 engines cut off before failure, 13,096 rows |
| `RUL_FD001.txt` | True remaining life for each test engine (the answer key) |

- Each row: engine id, cycle number, 3 operating settings, 21 sensors (temperatures, pressures, speeds).
- 15 of the 21 sensors change as the engine wears. The other 6 are flat and are dropped.
- Engine lifetimes range from 128 to 362 cycles (median 199).
- One operating condition, one failure mode: **high-pressure compressor degradation**.

### Simulated company layer (clearly labelled as simulated)
**Prairie Gas Transmission**, a fictional operator.
- 5 compressor stations, named after Alberta towns
- 100 turbines, mapped one-to-one from the **100 training engines**. Training engines run all the way to failure, so real failures appear in the replay. (Test engines stop before failure, so they are used only for the official accuracy benchmark.)
- **Cross-fitting:** the model is trained on 80% of engines and predicts the other 20%, rotating through all five groups. Every turbine in the demo is judged by a model that never saw it
- Technician roster: name, station, shift, phone page, preferred language (at least one French speaker)
- Crew capacity per station
- Cost assumptions: cost of an unplanned breakdown vs a planned service (round numbers, stated openly in the pitch)

### The live feed (historian simulator)
- Real operators store sensor readings in a data historian. Our **historian simulator** plays that role: it streams each turbine's NASA readings forward one day at a time into the database.
- The engine reads those readings, read-only, and predicts **live**, exactly as it would at a customer.
- No failures are invented. Every training engine genuinely wears out. We only choose **where the replay starts**, so a unit reaches the danger zone during the demo. Same starting point every run, so rehearsals match the pitch.
- Play, pause and speed controls let the presenter set the pace.

### Faults (for robustness)
- The simulator keeps a **fault list**: unit, sensor, fault type, start day.
- **Dead sensor:** sends blank readings. **Bad values:** stuck, spike, or out of range.
- Faults can be **planted** in the scenario in advance, or **toggled live** from Test mode. Same mechanism.

### Assumptions
- 1 cycle = 1 day of operation
- All cost figures are illustrative assumptions, not industry data

### Data generated by the product
- Call transcripts and AI summaries from the voice agent
- Technician feedback after each job
- Plan changes and their reasons

### In a real deployment
- The operator's existing sensor data system (data historian), read-only
- The operator's maintenance and repair records

### Why this dataset fits
Operators do not publish their turbine sensor data. NASA C-MAPSS is the standard public benchmark for turbine wear, and its failure mode (compressor-section wear in a jet engine) matches the aeroderivative turbines that drive many pipeline compressors. **We never claim it is pipeline data.** The method transfers; the model is retrained on each operator's own data in a pilot.

---

## 6. The Engine

**Rubric target: Autonomous Reasoning + Data-Driven Decisions (30%)**

| Step | What it does | How |
|---|---|---|
| **0. Check data quality** | Catches dead sensors and bad values before they reach the model | Rules for blank, stuck, spike and out-of-range readings. A broken sensor triggers an instrument check, never a crew call |
| **1. Predict (live)** | Remaining life of each turbine as a range (low, likely, high), on every new reading | LightGBM gradient boosting on rolling sensor averages and trends; remaining life capped at 125 cycles; three models for the range. Trained in advance, predicts live |
| **2. Explain** | Why a unit is flagged | The sensor that drifted most, in plain words ("turbine temperature rising for six days") |
| **3. Decide** | Which units to service this week | Scheduler that weighs breakdown risk x breakdown cost against service cost, within crew capacity. Greedy first, optimizer if time allows |
| **4. Simulate** | Plays the fleet forward week by week | Compares 3 approaches: run until it breaks, fixed schedule, PipeGuard |
| **5. Self-tune** | Picks its own best alert threshold | Runs the simulation across thresholds and keeps the cheapest |
| **6. Re-plan** | Reacts to new limits | A technician's answer ("not before Friday") becomes a constraint; the schedule is rebuilt |
| **7. Learn from feedback** | Gets better from the field | Technician verdicts adjust unit urgency and nudge the alert threshold |

### Baselines (the lazy approaches we must beat)
1. **Run until it breaks**
2. **Fixed schedule:** service every unit every N cycles
3. **Starter model:** linear model on 5 sensors

### Results so far

| Model | Average error | Failing engines caught (of 25) | False alarms |
|---|---|---|---|
| Starter-style linear model | 27.5 cycles | 12 | 0 |
| Gradient boosting, capped, untuned | 14.8 cycles | 18 | 1 |

**Headline number (to compute):** "PipeGuard would have caught X of Y failures at least two weeks early."

### Edge cases the engine handles
- **No feasible plan** (all crews booked): unit flagged "at risk, needs manager decision." Never fails silently.
- **Low confidence** (unit with little history): wide range and a "low confidence" label instead of fake precision.
- **Dead sensor:** prediction continues on the other sensors with a wider range and "low confidence." Instrument check requested.
- **Bad values (stuck, spike, out of range):** thrown out so they cannot trigger a false alarm. Instrument check requested.
- **Jumpy live data:** a unit must stay in the danger zone for 3 readings in a row before a call is made.

### Known limits
- Stand-in data, not real pipeline data
- One operating condition and one failure mode
- Both are solved by retraining on an operator's own data during a pilot

---

## 7. The Enterprise App

**Rubric targets: Execution & Software Architecture (20%), Presentation & Demo Quality (15%)**

### The demo company
Prairie Gas Transmission, pre-loaded. One-click login (no real accounts or multiple companies).

### Screens

| Screen | What it shows | Why it matters |
|---|---|---|
| **Fleet overview** | 5 stations, 100 turbines in red, yellow, green. Replay clock runs sensor data forward (for example, one day per second) | Looks live without real-time infrastructure |
| **Unit detail** | Remaining life range, sensor trend chart, reason, history | Shows the engine is explainable |
| **Weekly plan** | Which units get serviced, by whom, and why. A change from a technician's call shows as **Proposed**; a manager clicks **Approve** and it becomes a work order | The decision, made visible, with a human signing off |
| **Impact tab** | PipeGuard vs fixed schedule vs run until it breaks: breakdowns, wasted services, dollars. Sliders for crew size and breakdown cost | **Most important screen for scoring.** Judges see the decision change live |
| **Decision log** | Every alert as a chain: sensor drift, prediction, rules check, call, technician's answer, what changed in the plan, manager approval, feedback. Each call shows the tools the agent used, any safety stop, and a 4-line report card | Proves voice changes decisions, and that it stayed on task |
| **Roster** | Technicians: name, station, shift, phone, preferred language | Decides who gets called |
| **Work orders** | Download this week's service list (approved items only), and a one-page printable **Weekly summary** for the director | Real enterprise feel |
| **Exports** | CSV download from Fleet (every unit), Decision log (what is on screen) and Impact (policies and assumptions), built for Excel | Managers can do their own analysis and keep records |
| **Settings** | Crew size, costs, call rules | Shows operators stay in control |
| **Test mode** | Fault injection: "Kill sensor" and "Corrupt sensor" for any unit; reset demo; simulate-call fallback | Proves robustness live, especially in Q&A. Kept separate from the manager's main screens |
| **Technician phone page** | Runs on a phone browser: incoming call screen, live call, verdict buttons | Where the voice call happens in the demo |

### Status colours (same everywhere)

| Status | Look | What happens |
|---|---|---|
| Healthy | Green | Nothing |
| Watch | Yellow | Monitored |
| At risk | Red | Crew scheduled, technician called |
| Sensor issue | Grey + wrench | Instrument check, no crew call |

### Roles
- **Maintenance manager:** sees everything, approves plan changes before they become work orders
- **Technician:** receives calls, gives feedback

---

## 8. Voice system (ElevenLabs)

**Rubric target: Autonomous Reasoning (30%), plus the Best Project Built with ElevenLabs prize**

ElevenLabs is a hackathon sponsor. All participants get the Creator tier. Voice is optional under the rules and not in the rubric, but here it changes decisions, which is what makes it central rather than decoration.

### Flows

**1. Alert call to the technician**
> "Unit 14 at the Edson station has about 20 to 35 days left. Turbine temperature has risen for six days. Can your crew service it by Thursday?"

The answer becomes a constraint. The engine re-plans. The decision log shows what changed.

**2. Field report**
After the job, the technician speaks a note ("replaced the seal, vibration still a bit high"). Speech-to-text turns it into data and the unit's status updates.

**3. Feedback verdict**
| Verdict | Effect |
|---|---|
| Confirmed wear | Warning counted as correct |
| Looks fine | Counted as a false alarm, urgency drops |
| Part replaced | Unit resets to healthy |

PipeGuard tracks how often its warnings are right and nudges its alert threshold.

**4. Multilingual calls**
Each technician has a preferred language. A French-speaking technician is called in French; the decision log shows the French transcript plus an English summary for the manager. Pipeline crews come from many backgrounds, so this is a real selling point.

**5. Shift brief (if time allows)**
A 30-second spoken summary for the next shift.

### Guardrails
- Calls only for top-priority units
- Daily cap on calls per technician
- No duplicate calls for the same unit within a set window
- **No answer:** call the backup technician on the roster, then alert the manager in the app
- **Unclear answer:** the agent confirms back ("So Friday, correct?")

These address **alarm fatigue**, a real problem in control rooms.

**Safety on the call itself (ElevenLabs settings, staged and tested before they go on the demo agent):**
- **Guardrails:** *Focus* keeps the agent on its job, *Manipulation* blocks attempts to talk it out of its rules. Our own rules code is the real gate; these are a second layer.
- **Call report card:** after every call, four yes/no checks: asked for the earliest day, confirmed before booking, stayed on task and facts, honest about being automated. Shown in the Decision log.
- **Retention:** call recordings and transcripts are kept 30 days at ElevenLabs. Our own decision log keeps the record.

### Where PipeGuard fits in the approval process
Real gas companies have layers of approval before a crew goes near a machine: work order approval, outage coordination, permit to work, management of change. **PipeGuard skips none of them. It starts them earlier.** It runs before the first gate: it tells the planner weeks ahead that a unit will need work, with the evidence, so the work order, outage notice and permit all happen calmly instead of in an emergency. The one gate the product shows is the first: the technician's answer makes a **Proposed** plan change, and the manager approves it. Permits and outage notices stay with the operator's people, as today.

### ElevenLabs parts used
- **Agents platform:** the conversational voice agent, with tools that call our API
- **Speech-to-text:** field reports
- **Text-to-speech:** shift brief
- **Post-call data:** transcripts and analysis sent to our server when a call ends, so we store and display them rather than building transcription ourselves
- **Phone calls:** a technician phone web page on a teammate's phone. It rings, the teammate taps Answer, and the voice session starts. Free, reliable, no phone network needed. Twilio phone calls are a stretch goal

**Check early Saturday:** French calls and English summaries work on the Creator tier. If not, demo in English and present multilingual support as a roadmap item. Full integration detail and tier limits are in `techstack.md`.

---

## 9. Architecture

**Rubric target: Execution & Software Architecture (20%).** The rubric asks for a diagram and the reasoning behind the design.

The full technical specification lives in **`techstack.md`**. This section is the summary.

```
[Training, offline] --> model files
                            |
[Historian simulator] --> [PostgreSQL] <--> [Engine worker]
   (clock, faults)            ^   |          quality -> predict -> plan -> alerts
                              |   v
                         [FastAPI API] <---- tools + webhooks ----> [ElevenLabs Agent]
                          |          |                                    ^
                          v          v                                    | voice
               [Manager dashboard]  [Technician phone page] --------------+
```

### Components
| Component | Job |
|---|---|
| Historian simulator (worker) | Plays the customer's data historian: streams readings, owns the clock, applies faults |
| Engine (worker) | Quality checks, live predictions, explanations, plan, alerts |
| PostgreSQL | Single source of truth; also passes "new data" signals between workers |
| FastAPI | Serves the dashboard and phone page, receives ElevenLabs tool calls and webhooks |
| React app | Manager dashboard and technician phone page |
| ElevenLabs Agent | The voice conversation; calls our API mid-call |

### Key choices
| Choice | Why |
|---|---|
| Monorepo | Three people, shared engine code, one GitHub link for judges |
| React + FastAPI | Looks like a real product; Python keeps the model and API in one language |
| PostgreSQL on our own server | Several processes write at once; production-grade; always on, no cold starts |
| LightGBM | Strong on tabular data, handles missing sensor values, gives ranges, trains in seconds |
| Two workers, no message queue | Postgres alone passes signals; fewer things to break on demo day |
| Docker Compose | Same setup on the server and the laptop backup |
| Caddy | Automatic HTTPS in front of the app on our Hetzner server, so ElevenLabs can reach our API |
| For an operator | No new sensors or hardware; reads data they already store, read-only |

---

## 10. Security and trust

- **Read-only:** PipeGuard reads sensor data. It never controls machines.
- **Data stays with the operator:** runs inside their environment.
- **Humans always decide:** PipeGuard recommends; a manager approves plan changes; technicians act. Nothing becomes a work order until a manager approves it.
- **Rules outside the AI:** a rules check (not the AI) decides whether a call may happen; the decision log shows which checks passed.
- **Guardrails and call report card** on every voice call (see section 8). Recordings kept 30 days.
- **Start the approvals earlier, don't skip them:** PipeGuard feeds the normal work order, outage and permit process weeks sooner. It never replaces it.
- **Call limits:** prevents alarm fatigue.

---

## 11. Business case

**Rubric target: Commercialization in Industry (15%)**

### Value proposition
PipeGuard tells maintenance teams which compressor turbine will fail next, weeks ahead, so they fix it on their schedule instead of losing gas flow to a surprise breakdown.

### Why us over the big vendors
Large vendors already sell predictive maintenance, but those are big, expensive systems that take months to roll out. PipeGuard is lightweight, priced for mid-size operators, live in weeks, and built for field crews with voice calls, not only a control room dashboard.

### First customer
- **Primary:** a mid-size Alberta gas operator with dozens of compressors. Enough machines to feel the pain, not the budget for the big systems.
- **Alternative:** a compression services company that maintains compressors for many clients. One customer, many sites.

### Deployment
1. Read-only connection to the operator's existing sensor data
2. Runs in their environment
3. Dashboard for the manager, voice calls for technicians
4. Humans decide

### First 100 days

| Phase | What happens | Success test |
|---|---|---|
| **Week 1** | Talk to 5 to 10 industry people; confirm the pain; request historical sensor data and repair logs | One company agrees to share data |
| **Days 1 to 30** | Pilot agreement for 10 to 20 machines; retrain on 2 to 3 years of their data | Would PipeGuard have warned them before their last 5 breakdowns? |
| **Days 31 to 60** | Shadow mode: runs alongside their normal process, no one acts on it | Warnings match what actually happens; false alarms tuned |
| **Days 61 to 100** | Live at one station: dashboard and voice calls | Breakdowns caught, false alarms, crew hours saved; convert to paid |

### Pricing
Monthly fee per machine monitored, framed as a small fraction of one surprise breakdown.

### Scaling
1. More stations at the same operator
2. More operators across Alberta and Canada
3. More machine types: piston-engine compressors, pumps, power plant gas turbines
4. Partners: control room automation companies as resellers

Each new customer costs less to start because the model and setup are reusable.

---

## 12. Demo and pitch

**Rubric target: Presentation & Demo Quality (15%).** 5-minute pitch, 3-minute Q&A.

### Opening hook
> "Every compressor that fails without warning cuts gas flow to thousands of homes. We built the system that sees it coming."

### 5-minute script

| Time | Section | What happens |
|---|---|---|
| 0:00 | Intro | Team, one line each (10 seconds) |
| 0:10 | Problem | Compressor stations, turbines, cost of surprise failures, how it is done today. State Option A and the NASA dataset upfront |
| 1:10 | **Live demo** | Already logged in. Fleet overview, press play, a unit turns red. Voice agent calls; a teammate answers as the technician ("not before Friday"). Plan change shows as **Proposed**; click **Approve** (one click) and it becomes a work order. Impact tab updates. Drag a slider to show it re-decide |
| 3:10 | Architecture and results | One diagram. Before and after: 27.5 to 14.8 cycles; headline number |
| 4:10 | Business case and close | First customer, 100-day pilot, pricing, scaling. Closing line |

### French call
- **Judging room:** a teammate answers with memorized phrases ("Oui", "Pas avant vendredi").
- **Stage final (4 PM):** invite a French speaker from the audience, pre-arranged at Sunday lunch. Teammate is the backup.

### Sensor fault moment (about 15 seconds)
Right after the plan changes from the call:
1. Presenter: "What if a sensor breaks? In the field, that happens all the time."
2. Teammate clicks **Kill sensor** on a unit in Test mode.
3. The unit turns **grey with a wrench**, not red. Notice: "Sensor offline. Prediction still running, lower confidence. Instrument check requested." No crew call.
4. Presenter: "PipeGuard knows a broken sensor isn't a broken turbine."

If the pitch is running long, skip the click: a **planted fault** in the scenario shows the same thing on its own, and the toggle is saved for Q&A ("what if a sensor fails?").

### Demo safety nets
- Reset demo before every run, so the scenario is identical
- Run on our server and on the laptop backup
- Phone hotspot in case Wi-Fi fails
- Recorded clip of a successful call, plus a simulate-call button
- Backup demo video (the rubric explicitly allows this)
- Impact tab screenshot on a slide

### Rehearsal rules
- One person keeps time. Never go over 5 minutes.
- Every Q&A answer under 20 seconds.

---

## 13. Q&A prep

**"Why doesn't this match Case 4 in the repo?"**
> "We didn't do Case 4. We chose Option A and brought our own problem statement, which the organizers approved. We reused the public NASA turbine dataset that Case 4 also uses, and we cite it. We pointed it at pipeline compressor turbines instead of buses because the data is turbine data, and many pipeline compressors run on aeroderivative turbines, jet engines adapted for ground use. That is a closer match than diesel bus engines, and a higher-stakes problem for Alberta."

**"So it's not real pipeline data?"**
> "Correct. Operators don't publish turbine sensor data, so NASA's dataset is the standard public benchmark for turbine wear. Our method transfers. In a pilot, the first step is retraining on the operator's own data, and the test is whether we would have caught their last breakdowns."

**"Many field compressors use piston engines, not turbines."**
> "True. We start with turbine-driven units, where our data fits. The same method extends to piston engines once we have their sensor data."

**"How do you handle false alarms?"**
> "Three ways: the model gives ranges and flags low confidence, calls only go out for top-priority units with daily caps, and technician feedback teaches PipeGuard which warnings were wrong."

**"What if a sensor fails or gives bad readings?"**
> (Click Kill sensor in Test mode.) "Every reading is checked first. A dead or faulty sensor triggers an instrument check, not a crew call, and the prediction keeps running on the other sensors with lower confidence."

**"How do you know the model isn't just memorizing the engines?"**
> "Every turbine in the demo is judged by a model that never saw it. We train on 80% of engines and predict the other 20%, rotating through all of them. Our accuracy numbers come from NASA's separate test set."

**"We have layers of approval. Won't this slow things down or get blocked?"**
> "We keep every one of them. PipeGuard doesn't authorise or do any work, and it never touches the machines. It runs before the first gate, so the work order, outage notice and permit start weeks earlier instead of in an emergency. Each day a red unit waits is a day off its remaining life."

**"Who is accountable if it's wrong?"**
> "People are. PipeGuard recommends, the manager approves, the technician decides. The decision log keeps what we recommended, on what evidence, and what everyone did."

**"What stops the voice agent going off-script?"**
> "Rules in code decide whether it may call and what it may change. On the call, ElevenLabs guardrails keep it on topic, and every call gets a four-point report card in the decision log."

**"Is it secure?"**
> "It's read-only, never touches control systems, runs inside the operator's environment, and humans make every decision."

**"Why would anyone buy this over the big vendors?"**
> "The big systems are expensive and take months. PipeGuard is lightweight, priced for mid-size operators, live in weeks, and built for field crews with voice."

---

## 14. Risks

| Risk | Mitigation |
|---|---|
| Organizers do not approve Option A | Fall back to Case 4 with its fleet story; pipelines become the growth market |
| ML build takes longer than planned | Person 1 starts first thing Saturday; tested script already exists |
| Voice agent issues on Creator tier | Test early Saturday; browser call by default; recorded clip as backup |
| Judges question the stand-in data | Say it first, openly; prepared answers above |
| Live demo fails | Server and laptop copies, hotspot, simulate-call button, backup video |
| Our server or its internet goes down | Laptop runs the same Docker Compose setup |
| Live data or model hiccup mid-demo | Engine switches to pre-calculated backup predictions |
| **Majoring on the minor:** enterprise polish eats time while the engine is unfinished | Strict build order, building right up to the real deadline (section 15) |

---

## 15. Build plan

### Team split (all three are full stack)

| Person | Owns |
|---|---|
| **Olise: ML engine** | Training with cross-fitting, data quality checks, live prediction with ranges, explanations, scheduler, simulation, self-tuning, feedback logic, headline number, demo scenario |
| **Ebube: backend** | Database, historian simulator, FastAPI backend (including voice tool endpoints and webhooks), live updates, call guardrails and call state, Docker, Caddy and server deployment, laptop fallback |
| **David: dashboard, voice pipeline, pitch** | Manager dashboard (fleet, Impact tab, decision log, Test mode, roster, work orders), technician phone page, ElevenLabs agent and LLM test, French call, simulate-call fallback, architecture diagram, pitch deck and script, Q&A, GitHub submission, screenshots, backup video |

Per-person guides for builders and their coding agents are in `docs/delegation/`.

### Build order (major on the major)
1. Trained models and results vs the baseline
2. Database, historian simulator and engine running together
3. Fleet dashboard with live replay and status colours
4. Impact tab with the simulation and tuned vs default settings
5. One voice call that changes the plan
6. Decision log with transcripts and summaries
7. Data quality checks, planted fault, Test mode toggle
8. Feedback system
9. French call
10. Headline number, work orders, roster, polish

### Timeline

| When | Brain | Face | Voice and story |
|---|---|---|---|
| **Sat morning** | Train models, cross-fitting, benchmark | Repo, database, seed, simulator | ElevenLabs agent answers a test call; test French |
| **Sat 12 PM checkpoint** | Engine predicting live | Fleet page showing live predictions | Phone page rings and connects |
| **Sat afternoon** | Scheduler, simulation, self-tuning, quality checks, feedback | Impact tab, decision log, Test mode, live updates | Voice tool endpoints, re-plan loop, guardrails, ask a Discord mentor |
| **Sat evening (no feature freeze)** | Keep building and integrating; pull final numbers late | Polish | Draft pitch and slides |
| **Sat night** | Help debug | Deploy to server, test laptop backup | Full demo run with a real call; check ElevenLabs usage |
| **Sun 8 to 10 AM** | All: 2 or 3 timed rehearsals, record backup video, screenshots | | |
| **Sun 11 AM** | **Submit** | | |

### Cut order if time runs short
1. Twilio phone calls
2. Shift brief
3. Work order export
4. French call
5. Test mode toggle (keep the planted fault)
6. Optimizer upgrade (keep the greedy scheduler)

### Never cut
- The model's before and after
- The replay simulation and Impact tab
- One live voice call that changes the plan

---

## 16. Submission checklist (GitHub Issue)

- [ ] Team name, 3 members with GitHub handles
- [ ] Stream: Energy and Infrastructure Systems
- [ ] Project title and tagline (3 lines max)
- [ ] About: inspiration, how we built it, what we learned, challenges, architecture diagram, results vs baseline
- [ ] 2 to 5 screenshots: fleet overview, Impact tab, decision log, voice call, unit detail
- [ ] Demo video link (5 minutes max)
- [ ] Additional info: Option A (organizer approval noted), NASA C-MAPSS citation, any reused starter code cited, ElevenLabs listed as sponsor tech
- [ ] No API keys or secrets in the repo
- [ ] Submitted by 11 AM Sunday

---

## 17. Sources

- `techstack.md`: full technical specification
- [Hackathon repository](https://github.com/nagusubra/industry-hackathon-lab) and [judging rubric](https://github.com/nagusubra/industry-hackathon-lab/blob/main/JUDGING_RUBRIC.md)
- Industry Hackathon Participant Handbook (Final)
- NASA C-MAPSS Turbofan Engine Degradation Simulation Data Set (FD001), bundled in the hackathon repository
- [ElevenLabs batch calling documentation](https://elevenlabs.io/docs/agents-platform/phone-numbers/batch-calls)
- [General Electric LM2500 (aeroderivative turbine)](https://en.wikipedia.org/wiki/General_Electric_LM2500)
- [Rolls-Royce RB211 gas compression packages for a Canadian pipeline](https://www.rolls-royce.com/media/press-releases-archive/yr-2007/rr-rb211-gas.aspx)
- Model test script and output: `case4_vs_case10_check.py`, `output.txt`
