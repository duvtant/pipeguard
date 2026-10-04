# LLM test results (text evals): Oct 3, 2026

**Read this first.** These are the results of the **final run**, done with the prompt and all tests frozen beforehand (rules in `docs/llm_test_protocol.md`). Earlier in the day tests and the prompt were changed after seeing results; the protocol file lists every change and why. This is the text half. **Voice speed is measured at the end of this file (Gemini meets the target).**

## Ranking (Gemini confirmed on reply speed; tool-turn speed waits for the live backend)
| # | Model | Gate: 8 critical x2 | Held-out and extras | Simulations | Cost of the 16 gate runs | Verdict |
|---|---|---|---|---|---|---|
| 1 | **Gemini 3.8 Flash** (low) | **16/16** | 16/18 (the 2 misses are the ambiguous test h3, below) | **3/3** | 403 credits | Best all round. Cheapest, already the agent's model |
| 2 | **Claude Sonnet 5.5** (low) | **16/16** | 8/9 (same h3 miss) | not run | 849 credits (2.1x) | Best judgment in replies; costs twice as much |
| 3 | **GPT-5.6 Terra** (high) | **16/16** | 7/9 (h3, plus a double tool call on h2) | not run | 680 credits (1.7x) | Two real slips; high effort is a latency risk |
| 4 | GLM 5.2 (medium) | 15/16 (94%) | not run | not run | 645 | **Out** in round 1: missed the pitch-line tool call once |
| 5 | DeepSeek Flash 4.1 | 8/16 (50%) | not run | not run | 370 | **Out** in round 1: often made no tool call at all |

**Confidence is limited.** Each test ran only 1 to 2 times, so a gap of one or two tests between the top three is noise. What is solid: all three finalists book the right day, with the right IDs, on 16 of 16 critical runs; DeepSeek and GLM do not clear the bar. The grader is an LLM and its calls were checked by reading the actual replies, not trusted blindly (see below).

## What the models actually said (read by hand)
- **Brevity and tone:** all five stay within one or two short sentences and re-ask the day, as instructed. Sonnet is the most natural ("Between 14 and 35 days. What's the earliest day your crew can service it?"). Gemini and Terra spell numbers as words ("fourteen and thirty-five"), which suits speech.
- **Honesty and focus (tests 10, 15, 17):** every model says it is PipeGuard's automated assistant, declines engineering advice and other units, and steers back. No differences.
- **"Last Tuesday" (test 16), the one real separator:** Sonnet: "last Tuesday has already passed. Did you mean next Tuesday?" (best). Gemini: "Did you mean next Tuesday, November tenth?" (fine) or, earlier, "did you mean today?" (missed it). **Terra: "So you mean Tuesday, October twenty-seventh, correct?", which confirms a date in the past: a real mistake.** The grader marked Sonnet's good reply a fail (it counted offering "next Tuesday" as guessing), so this test's wording is flawed and its scores are noisy. Not demo-critical.

## Every failure, with the reason
- **h3 "We swapped out that part this morning", all three models:** each called `field_report` instead of `feedback(part_replaced)`. **This test is ambiguous and the prompt's own rule says a work note that mentions replacing something is not a verdict**, so the models behaved as instructed. It stays counted as a fail for everyone, so it does not change the ranking. It should be replaced with a clearer test.
- **Terra, h2 "You called it, the bearings are going":** sent the right verdict **and** a duplicate `field_report`. Gemini and Sonnet sent exactly one call.
- **Test 16:** see above (grader noise plus one real Terra mistake).
- **DeepSeek and GLM:** round-1 failures listed in the table; they ran on the earlier prompt. Stricter checks cannot turn a fail into a pass, so they were not re-run.

## Corrections made during testing
1. **The `unit_id` and `technician_id` checks were removed after the first failing run** on the assumption that the model never types them. The real cause was a missing `body.` path prefix. **Restored**: the webhook body must carry the right IDs, and all three finalists still pass.
2. **My prompt fix quoted the tests' own words**, so passing proved little. **Prompt v4 removes every test phrase**, and seven new **held-out tests** use wording that appears nowhere in the prompt. The models still pass them (except ambiguous h3), so the fix generalises.
3. **The three simulations were first excluded as "untrustworthy", which was only half right.** The cause was a real test bug: the tool-mock settings had the wrong shape, so the agent hit our undeployed server (HTTP 500). Fixed, and with the mocks applied the agent saw our mocked replies and **Gemini passes all three**. The evidence should have been shown before excluding them.
4. **The field-report bug was a real agent bug** (an unasked `feedback` verdict, which resets a unit). It was fixed in the prompt, not by loosening the test. Prompt v2 broke Sonnet; v3 and v4 fixed it; v4 is the final, **not pushed** (the live agent still has the original prompt).
5. Test 16 was first called a grader quirk. The replies show a real difference between the models.

## Cost
Credits used so far per ElevenLabs' meter: **15616 of 131,000 (11.9%)**, including two flawed first runs and the prompt iterations. Text tests bill in credits for the model's tokens, not minutes. Raw per-run results are kept locally and are not part of the repository.

## Voice speed (real calls, Gemini 3.8 Flash): measured Oct 3
**How:** `infra/elevenlabs/llm_test/voice_call.mjs` makes a real voice session the same way the phone page does (signed URL, WebSocket, 16 kHz audio). A synthetic caller (macOS voice) says "Yes, go ahead." then "Not before Friday." and the script times the agent. **It spends real usage.** Our backend is not deployed yet, so the agent's tool calls fail (HTTP 500) and it ends with "A manager will follow up". That is expected and is only used to measure the model.

**Only 5 calls count.** Five more calls were thrown away: the first version of the script started talking while the agent's greeting was still playing, so the agent heard nothing ("are you still there?"). That was fixed, and the script now marks any call where the agent did not hear both lines word for word as INVALID and excludes it.

| Measure (ElevenLabs' own per-turn numbers, 5 valid calls) | Result | Target |
|---|---|---|
| **Normal reply: caller stops talking to agent audio starts** | **median 1.20 s, worst 1.54 s** | median 1.5 s, p95 3 s: **met** |
| Model alone (first answer token) | about 0.8 to 1.0 s each call | n/a |
| Speech synthesis start | about 0.13 s | n/a |
| Turn that calls a tool (client side, end of caller speech to first agent audio) | 2.5 to 5.5 s | tool round trip 3 s: **not judgeable yet** |

**What the tool-turn number means:** those turns include the agent calling the missing server and retrying (two failed tool calls and three model calls in a row). With a live backend there is one tool call, so expect roughly 2.5 to 3 s, which is right at the target. **This must be re-measured once Ebube's backend is live.**

**Limits of this test:** the caller is a clean synthetic voice, not a person on a noisy phone, so speech recognition is easier than in real life, and real pauses make the agent wait longer. Treat 1.2 s as a good-case number.

**Decision:** Gemini 3.8 Flash meets the reply-speed target, so there is **no reason to voice-test Sonnet or Terra** (it would cost more usage). Gemini stays. The evals ran Gemini at **low** reasoning effort but the live agent had none set, so `reasoning_effort: low` is now written into both config files (staged, not pushed).

**Cost of the voice test:** the credit meter went from 15,660 to 18,050 (**2,390 credits for about 5 minutes of calls, roughly 480 credits per minute**). That is far more than the model cost alone, so voice calls are the expensive part of this project. Meter at the end: **18,050 of 131,000 (13.8%)**.
