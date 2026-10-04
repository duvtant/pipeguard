#!/usr/bin/env node
// A REAL voice session with the agent, driven by a synthetic caller (plan P3.7). It connects the same way the phone page does (signed URL,
// WebSocket, 16 kHz audio), plays a recorded voice saying what a technician would say, and times how long the agent takes to start speaking.
//
//   node voice_call.mjs 1            make 1 call
//   node voice_call.mjs 5            make 5 calls, one after another
//
// THIS SPENDS REAL ELEVENLABS USAGE (call minutes, about 0.5 minute per call). Hard limits: at most 6 calls per run, 75 s per call.
// The key comes from the repo's .env and is never printed. The caller's voice is macOS `say` (free); nothing is sent to any other service.
// Latency here = from the last moment of the caller's speech to the first audio from the agent, so it INCLUDES the agent's end-of-turn
// detection wait, which a real person also experiences. ElevenLabs' own per-turn numbers are read afterwards with `latency.py --latest N`.
import { execFileSync } from "node:child_process"
import { readFileSync, writeFileSync, mkdirSync, existsSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const HERE = dirname(fileURLToPath(import.meta.url))
const ROOT = join(HERE, "..", "..", "..")
const OUT = join(HERE, "results", "voice")
mkdirSync(OUT, { recursive: true })

const env = Object.fromEntries(readFileSync(join(ROOT, ".env"), "utf8").split("\n").filter((l) => l.includes("=") && !l.startsWith("#")).map((l) => [l.split("=")[0], l.slice(l.indexOf("=") + 1).trim().replace(/^"|"$/g, "")]))
const KEY = process.env.ELEVENLABS_API_KEY || env.ELEVENLABS_API_KEY
if (!KEY) { console.error("ELEVENLABS_API_KEY is not set"); process.exit(1) }
const AGENT = JSON.parse(readFileSync(join(HERE, "..", "agents.json"), "utf8")).agents[0].id

const N = Math.min(Number(process.argv[2] ?? 1), 6)
// The same variables a real call has (see suite.py VARIABLES).
const VARIABLES = { technician_id: "1", technician_name: "Aiden", unit_id: "EDS-07", station_name: "Edson", rul_low: "14", rul_high: "35", reason: "High-pressure compressor outlet temperature has risen for 6 days", proposed_day: "Thursday", call_request_id: "41", sim_today: "Tuesday, November 3" }
const TURNS = ["Yes, go ahead.", "Not before Friday."]

// Caller audio: macOS `say`, converted to raw 16 kHz mono 16-bit PCM (what the agent expects).
function speech(text, name) {
  const aiff = join(OUT, `${name}.aiff`), pcm = join(OUT, `${name}.pcm`)
  if (!existsSync(pcm)) {
    execFileSync("say", ["-v", "Samantha", "-o", aiff, text])
    execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-i", aiff, "-ar", "16000", "-ac", "1", "-f", "s16le", pcm])
  }
  return readFileSync(pcm)
}
const CHUNK_MS = 100, CHUNK_BYTES = 16000 * 2 * CHUNK_MS / 1000
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const now = () => performance.now()

async function oneCall(n) {
  const res = await fetch(`https://api.elevenlabs.io/v1/convai/conversation/get-signed-url?agent_id=${AGENT}`, { headers: { "xi-api-key": KEY } })
  if (!res.ok) throw new Error(`signed url: HTTP ${res.status}`)
  const ws = new WebSocket((await res.json()).signed_url)
  const log = { call: n, conversation_id: null, turns: [], agent_said: [], heard: [] }
  let lastAudioAt = 0, audioCount = 0, firstAudioAfterUser = null, userEnd = null, done = false
  // The server sends the agent's audio faster than real time, so 'no audio lately' does not mean it has finished talking. Track how much speech
  // it has sent (bytes / 32000 = seconds at 16 kHz 16-bit) and when that much playback time has passed since the first chunk.
  let spokenSecs = 0, speechStart = 0
  const send = (o) => ws.readyState === 1 && ws.send(JSON.stringify(o))

  ws.onmessage = (ev) => {
    const m = JSON.parse(ev.data)
    if (m.type === "ping") send({ type: "pong", event_id: m.ping_event.event_id })
    else if (m.type === "conversation_initiation_metadata") log.conversation_id = m.conversation_initiation_metadata_event.conversation_id
    else if (m.type === "audio") { lastAudioAt = now(); if (audioCount === 0) speechStart = lastAudioAt; audioCount++; spokenSecs += Buffer.from(m.audio_event.audio_base_64, "base64").length / 32000; if (userEnd !== null && firstAudioAfterUser === null) firstAudioAfterUser = lastAudioAt }
    else if (m.type === "agent_response") log.agent_said.push(m.agent_response_event.agent_response)
    else if (m.type === "user_transcript") log.heard.push(m.user_transcription_event.user_transcript)
  }
  ws.onclose = () => { done = true }
  await new Promise((ok, bad) => { ws.onopen = ok; ws.onerror = () => bad(new Error("websocket error")) })
  send({ type: "conversation_initiation_client_data", dynamic_variables: VARIABLES })
  const started = now()
  const hard = () => now() - started > 75000

  // Wait until the agent has finished speaking: audio has arrived and then 1.2 s of quiet.
  const agentQuiet = async (what) => { while (!done && !hard()) { await sleep(100); if (audioCount > 0 && now() - lastAudioAt > 800 && now() - speechStart > spokenSecs * 1000 + 500) return true } throw new Error(`timeout waiting for the agent (${what})`) }
  await agentQuiet("greeting")

  for (const [i, text] of TURNS.entries()) {
    const pcm = speech(text, `turn${i + 1}`)
    firstAudioAfterUser = null; userEnd = null; audioCount = 0; spokenSecs = 0
    // Speak in real time, 100 ms at a time, then keep sending silence (so the agent can tell the turn has ended) until it answers.
    for (let off = 0; off < pcm.length && !done; off += CHUNK_BYTES) { send({ user_audio_chunk: pcm.subarray(off, off + CHUNK_BYTES).toString("base64") }); await sleep(CHUNK_MS) }
    userEnd = now()
    const silence = Buffer.alloc(CHUNK_BYTES).toString("base64")
    while (!done && !hard() && firstAudioAfterUser === null) { send({ user_audio_chunk: silence }); await sleep(CHUNK_MS) }
    if (firstAudioAfterUser === null) throw new Error(`no reply to turn ${i + 1}`)
    log.turns.push({ said: text, reply_latency_s: +((firstAudioAfterUser - userEnd) / 1000).toFixed(2) })
    await agentQuiet(`reply ${i + 1}`)
  }
  ws.close(); await sleep(300)
  log.call_seconds = +((now() - started) / 1000).toFixed(1)
  const norm = (t) => t.toLowerCase().replace(/[^a-z ]/g, "").trim()
  log.valid = TURNS.every((t, i) => norm(log.heard[i] ?? "") === norm(t))  // the agent must have heard each line word for word, or the timing means nothing
  return log
}

const all = []
for (let n = 1; n <= N; n++) {
  try { const l = await oneCall(n); all.push(l); console.log(`call ${n} ${l.valid ? "VALID" : "INVALID (agent did not hear us properly: ignore its timing)"}: ${l.conversation_id} | ${l.call_seconds}s | latency ${l.turns.map((t) => t.reply_latency_s + "s").join(", ")} | heard: ${JSON.stringify(l.heard)} | agent: ${JSON.stringify(l.agent_said.slice(0, 3)).slice(0, 260)}`) }
  catch (e) { console.error(`call ${n} FAILED: ${e.message}. Stopping, so nothing more is spent.`); break }
}
writeFileSync(join(OUT, `calls-${Date.now()}.json`), JSON.stringify(all, null, 1))
const lat = all.filter((l) => l.valid).flatMap((l) => l.turns.map((t) => t.reply_latency_s)).sort((a, b) => a - b)
if (lat.length) console.log(`\n${all.length} calls (${all.filter((l) => l.valid).length} valid), ${lat.length} replies from valid calls | client-side latency: median ${lat[Math.floor(lat.length / 2)]}s, max ${lat[lat.length - 1]}s, total call time ${all.reduce((s, l) => s + l.call_seconds, 0).toFixed(0)}s`)
