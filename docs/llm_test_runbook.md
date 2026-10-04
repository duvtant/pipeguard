# Choosing the voice agent's model: runbook (plan tasks P3.6, P3.7, P3.8)

Everything is built and checked offline. **Nothing here has spent any ElevenLabs credits yet.** Every command that does is locked behind `--yes`
and prints what it will do first. Run the paid parts in a **spare account (account B)**, not the demo account, and keep the key in `.env`.

All commands run from `infra/elevenlabs/llm_test/`.

## Step 0: free, offline, do it any time
```bash
python3 run.py selfcheck     # validates all 19 test definitions (8 are demo-critical)
python3 run.py plan --candidates gemini-3.8-flash-low --repeat 2 --only critical   # shows how many runs; sends nothing
```

## Step 1: upload the tests (no model cost, creates 19 test definitions)
```bash
python3 run.py create --yes
```

## Step 2: text tests, one candidate at a time (this spends credits)
Start small, then read what it actually cost before scaling up:
```bash
python3 run.py run --candidate gemini-3.8-flash-low --repeat 2 --only critical --yes
```
The saved file `results/<candidate>.json` includes `credits_used` per run, and the script prints the total. If one candidate used
more than you expected, stop. Candidates (chosen Oct 3): `gemini-3.8-flash-low` (what the agent uses today, so the baseline), `claude-sonnet-5-5-low`, `gpt-5.6-terra-high`, `deepseek-v41-flash`, `glm-52-medium`. **GLM 5.3 is not on ElevenLabs' model list, only 5.2**, so GLM is tested as 5.2 (5.3 would need a custom-LLM route through OpenRouter with its own key and billing). Model IDs and effort levels were read from ElevenLabs' own list (`GET /v1/convai/llm/list`), and `selfcheck` refuses a model or effort that is not on it. LLM cost estimates from ElevenLabs' calculator for our 2,267-character prompt: Gemini 3.8 Flash $0.011/min, DeepSeek $0.011, Terra (GPT-5.6) $0.026, GLM 5.2 $0.026, Sonnet 5.5 $0.028 (at default effort; high effort thinks more, so Terra high will cost more and be slower). Luna was swapped for Terra on Oct 3. Model cost is pennies; **call minutes are the real budget** (see the Budget section).
A safety cap (`--max-runs`, default 40) refuses oversized runs. Never use `max` reasoning (the script has no such candidate).

```bash
python3 run.py report        # score table; applies the rule: at least 95% on the demo-critical tests
```

## Step 3 (P3.7): real voice latency
**Update Oct 3: this is now scripted.** `node voice_call.mjs 5` (in this folder) makes real calls with a synthetic caller, no headphones or phone needed. **It spends real usage: about 480 credits per minute of call on the meter**, so keep it to a handful of calls. Then `python3 latency.py <ids>` reads ElevenLabs' own numbers. The manual method below still works for a human-voice check.

(Original manual method, about 5 calls per finalist)
Text tests cannot measure speech latency. On the technician page (`/field/<id>`, over the public HTTPS URL) with **headphones**, make 5 calls per
finalist saying "not before Friday". Then:
```bash
python3 latency.py <conversation ids from ElevenLabs > Conversations>      # read-only
```
Targets: median reply at most 1.5 s, p95 at most 3 s, tool round trip at most 3 s. About 5 calls x 2 candidates x 60 s is roughly 10 agent minutes.

## Step 4 (P3.8): decide
The cheapest candidate that passes the text rule **and** meets the latency targets wins. Set it in `agent_configs/PipeGuard-Dispatcher.json`
(`conversation_config.agent.prompt.llm`, plus `reasoning_effort`), then `elevenlabs agents push`, and write the scores and the choice into `docs/llm_test_results.md`.
Do not invent numbers: `run.py report` only prints what was measured.

## Note: guardrails and test 10 (prompt injection)
Once the staged **Manipulation** guardrail is pushed, test 10 may end the call (the guardrail's default action) instead of the agent politely refusing. Judge it as a pass if the call ends safely with no engineering advice, and note which happened. Run the suite on the staging agent before enabling guardrails on the demo agent.

## Budget: measured Oct 3 (this replaces the earlier guesses)
**Balance at the start:** 131,000 credits, all remaining (Creator plan). **Measured:** text tests are billed **only as credits for the model's tokens, not as call minutes**. A normal test run is about 25 to 130 credits depending on the model; **the three simulated conversations (12, 13, 14) cost 250 to 590 credits per run**. The 8 demo-critical tests x 2 repeats cost 370 to 670 credits per model. The whole session (five models, two flawed first runs included) used **6,061 credits, 4.6%**, by ElevenLabs' own meter. Results: `docs/llm_test_results.md`. Real voice calls (steps below) are different: they use call minutes (275 included).

**Lessons from the first real runs (so nobody repeats them):**
1. The API wants `success_examples` and `failure_examples` as `{response, type}` objects, not plain strings.
2. `agent_config_override` must be a **full** config (`conversation_config` and `platform_settings`). `run.py` now fetches the live agent (read-only) and swaps only the model and effort, so tests run on our real prompt.
3. A tool-call test must **not** check `unit_id` or `technician_id`: the platform fills those in from the call's variables and the model never types them (proven by the real runs, which is the design working).
4. A parameter path is `body.<name>`, for example `body.earliest_day_text`. A bare name is reported "not found".
5. `run.py sync --yes` pushes edited definitions to the existing tests for free.
The first two real runs (25%) were test definitions that were wrong, not the model. They are excluded from `report`.

**Rules:** do not run the simulations (12 to 14) on every model; they are the expensive ones. Keep at least 60% of the month for rehearsals and the demo. Real voice calls cost minutes: 3 per finalist for 2 finalists is about 6 minutes; guardrail staging calls about 5 minutes. 15% of the allowance is about 41 minutes or 19,650 credits.
