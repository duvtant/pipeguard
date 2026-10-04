# ElevenLabs agent as code

Source of truth for the **PipeGuard Dispatcher** voice agent. Managed with the ElevenLabs CLI
(`@elevenlabs/cli`, installed globally). Run all commands from this folder.

| File | What |
|---|---|
| `pipeguard_dispatcher.config.json` | Our target agent config: prompt, language, first message, dynamic-variable defaults, signed-URL auth, override switches, data collection, 120 s cap |
| `agents.json`, `tools.json`, `tests.json` | CLI registry (ids appear after the first upload) |
| `agent_configs/`, `tool_configs/`, `test_configs/` | Per-item JSON the CLI pushes and pulls |
| `.env` | `ELEVENLABS_API_KEY` for this folder. **Git-ignored. Never commit.** |

## One-time setup (needs you: login or API key)
```bash
cd infra/elevenlabs
elevenlabs auth login                 # or: export ELEVENLABS_API_KEY=...   (use `! elevenlabs auth login` inside Claude Code)
elevenlabs auth status                # logged_in: true

elevenlabs agents add "PipeGuard Dispatcher" --template minimal   # creates agent_configs/<file>.json, uploads, saves the id
cp pipeguard_dispatcher.config.json agent_configs/<the-file-add-created>.json
elevenlabs agents push --dry-run      # preview the diff
elevenlabs agents push
elevenlabs agents status
```
`--template`/NAME order: `elevenlabs agents add --template <TEMPLATE> <NAME>`. There is no local-only flag for `add`, so it uploads.

## Notes
- **LLM is a placeholder** (`gemini-3.8-flash`). The LLM test (`docs/techstack.md` 12.10, plan task P3.8) picks the real one. Never `reasoning_effort: max` on a live call.
- **TTS model is `eleven_flash_v2` (English only) on purpose.** ElevenLabs rejects the multilingual `eleven_flash_v2_5` for an English-only agent ("English Agents must use turbo or flash v2"). French needs a `language_presets` entry for `fr`, which switches the agent to a multilingual model. That config shape is not in the docs: get it from `elevenlabs agents create --schema` or by adding French once in the dashboard and running `elevenlabs agents pull`.
- **Voice** is the template default. Choose the voice by ear in the dashboard (a taste decision), then `agents pull` to capture it.
- **French first message / voice per language** use `language_presets` (not written here because the exact shape is unconfirmed). Until then the `/field` page passes the first message for the technician's language as a session override.
- **Tools, secret, environment variable, webhook** are created through the CLI (`tools add`, `agents secrets`, `environment-variables create`, `webhooks create`) or the dashboard. After creating them, `agents pull` and `tools pull` so the repo reflects reality, and set `prompt.tool_ids` and `platform_settings.workspace_overrides.webhooks.post_call_webhook_id`.
- Never put a secret value in these JSON files. Tool auth headers reference a workspace **secret** by id.

## Staged in the config, NOT pushed yet (Track D)
`platform_settings` now also holds **guardrails** (Focus + Manipulation), a **4-rule call report card** (`evaluation.criteria`) and **30-day retention**, identical in both config files. They change the live agent only on `agents push`.
- **Do not push without David's go-ahead.** A guardrail's default action is to end the call, so a false positive on stage would kill the demo.
- Order: push to a spare/staging agent, make ~5 real calls with the demo script, check the report card and that no guardrail fires wrongly, then push to the demo agent. If anything misfires, leave guardrails off (our rules code is the real gate).
- Never set `retention_days` to `0`. Keep both config files identical in `platform_settings`.
- Impact notes: `docs/delegation/05_CHANGE_IMPACT_agent_hardening.md`.

## What is live (created by the CLI, read back and verified)
| Thing | Value |
|---|---|
| Agent | `agent_0201m40dhg4pfdqaq537zb3ckdrv` ("PipeGuard Dispatcher") |
| Workspace secret | `pipeguard_voice_tool_auth` (id `nJXCAQXdMQPBMKVITm5F`). Its value is `Bearer <VOICE_TOOL_SECRET>`: ElevenLabs sends the stored value as the whole `Authorization` header, so the `Bearer ` prefix is part of the secret and our backend checks `Authorization: Bearer <VOICE_TOOL_SECRET>` |
| Environment variable | `api_host` (`production` = `pipeguard.blunelabs.com`); tool URLs are `https://{{system__env_api_host}}/api/voice/tools/<name>` |
| Tools | `submit_availability`, `get_unit_status`, `field_report`, `feedback` (ids in `tools.json`); `end_call` is a built-in tool on the agent. `unit_id` and `technician_id` come from dynamic variables, never from the model |
| Webhook | `PipeGuard post-call` (id `55747635d4fb4759a145bf85dd33de51`), HMAC; signing secret is in `.env` as `ELEVENLABS_WEBHOOK_SECRET` |

Re-apply after any edit: `elevenlabs tools push && elevenlabs agents push` (run from this folder with the key exported from `.env`).
Tool parameter rule: a parameter takes **either** a description (the model fills it) **or** a `dynamic_variable`, never both.
