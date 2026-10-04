# LLM test protocol (fixed before the final run, Oct 3)

**Why this file exists:** earlier in the day tests and the prompt were changed after seeing results. Some changes were right (the API shape was wrong), but a test must not be bent until the model passes. This protocol was written **before** the final run. If a test turns out to be broken, it is reported and rerun, not quietly dropped.

## What changed since the first comparison, and why (all before the final run)
| Change | Kind | Honest note |
|---|---|---|
| `success_examples` as `{response, type}` objects; parameter path `body.<name>` | API format | Required by the API. No effect on strictness |
| Removed, then **restored**, the `unit_id` and `technician_id` checks | Strictness | They were wrongly removed, blaming the model; the real cause was the missing `body.` prefix. Restored: the webhook body must carry the right IDs |
| Simulation tool mocks rewritten to the shape the API uses | Test bug | The old shape was silently ignored, so the agent hit our real, undeployed server (HTTP 500). The three simulations (12, 13, 14) now mock all three tools |
| Prompt: unasked `feedback` call after a work note (field report) | **Agent bug** | Found by a failing test, fixed in the **prompt**, not the test. v2 broke Sonnet, v3 fixed it, but v3 quoted the test's own words, so **v4 removes every test phrase from the prompt** ("replaced the seal", "looks fine", "part replaced", "not before Friday", "So Friday, correct?") |
| 7 **held-out tests** (h1 to h7) | New evidence | Wording that appears nowhere in the prompt: three verdicts in other words, two work notes that must not create a verdict (one mentions a replacement), another day phrase, another French phrase |

## Rules
1. Prompt v4 and all 26 tests are **frozen** for the final run. No edits after seeing scores.
2. **Gate (decides who qualifies):** the 8 demo-critical tests x 2 repeats, at least 95%. Applies to the finalists from round 1 (Gemini 3.8 Flash, Claude Sonnet 5.5, GPT-5.6 Terra).
3. **DeepSeek and GLM** were eliminated in round 1 (50% and 94%). Stricter checks cannot turn a failure into a pass, so they are not re-run (saves credits). The prompt did change, so this is stated, not hidden.
4. **Held-out and extras:** the 7 held-out tests plus test 8 (field report) and test 10 (prompt injection): Gemini 2 repeats, the others 1 repeat. **Simulations (12 to 14):** Gemini once, to check the mocks and the prompt.
5. **Ranking** uses, in order: gate result, held-out and extras results, quality of the actual replies (read by hand, not only pass/fail), cost, then voice latency (still to be measured). A model that fails the gate is out whatever its other scores.
6. Every failure is listed with its reason. Raw results stay in `infra/elevenlabs/llm_test/results/`.
