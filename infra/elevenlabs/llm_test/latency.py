#!/usr/bin/env python3
"""Voice latency from real calls (plan P3.7). READ-ONLY: it fetches finished conversations; it starts nothing and spends nothing.

  python3 latency.py conv_abc conv_def ...       (conversation ids: ElevenLabs dashboard > Conversations)
  python3 latency.py --latest 5                  (the 5 newest calls of our agent: no ids to copy)

For each conversation it reports, per technician turn, the time until the agent starts replying, using ElevenLabs' own per-turn
metrics when present and otherwise the gap between message start times (an upper bound, because it includes the technician's own speaking time).
Targets: median at most 1.5 s, p95 at most 3 s, tool round trip at most 3 s.
"""
from __future__ import annotations

import json, os, statistics, sys, urllib.request
from pathlib import Path

env = Path(__file__).resolve().parents[3] / ".env"
key = os.environ.get("ELEVENLABS_API_KEY", "")
if not key and env.exists():
    key = next((l.split("=", 1)[1].strip().strip('"') for l in env.read_text().splitlines() if l.startswith("ELEVENLABS_API_KEY=")), "")
if not key: sys.exit("ELEVENLABS_API_KEY is not set.")


def fetch(cid: str) -> dict:
    req = urllib.request.Request(f"https://api.elevenlabs.io/v1/convai/conversations/{cid}", headers={"xi-api-key": key})
    with urllib.request.urlopen(req, timeout=60) as r: return json.load(r)


def turn_latencies(conv: dict) -> tuple[list[float], list[float], bool]:
    """(response latencies, tool round trips, used_exact_metrics)"""
    tr = conv.get("transcript", []); resp, tool, exact = [], [], False
    for i, m in enumerate(tr):
        if m.get("role") != "agent" or i == 0: continue
        met = (m.get("conversation_turn_metrics") or {}).get("metrics") or {}
        ttfb = (met.get("convai_llm_service_ttfb") or {}).get("elapsed_time")
        tts = (met.get("convai_tts_service_ttfb") or {}).get("elapsed_time")
        prev = tr[i - 1]
        if ttfb is not None:
            exact = True; v = ttfb + (tts or 0)
        elif prev.get("role") == "user": v = m["time_in_call_secs"] - prev["time_in_call_secs"]
        else: continue
        (tool if m.get("tool_calls") or prev.get("tool_results") else resp).append(v)
    return resp, tool, exact


def pct(xs: list[float], q: float) -> float:
    xs = sorted(xs); return xs[min(len(xs) - 1, int(round(q * (len(xs) - 1))))]


def latest(n: int) -> list[str]:
    """The n newest conversations of our agent (read-only), so nobody has to copy ids by hand."""
    agent = json.loads((Path(__file__).resolve().parents[1] / "agents.json").read_text())["agents"][0]["id"]
    req = urllib.request.Request(f"https://api.elevenlabs.io/v1/convai/conversations?agent_id={agent}&page_size={n}", headers={"xi-api-key": key})
    with urllib.request.urlopen(req, timeout=60) as r: items = json.load(r).get("conversations", [])
    return [c["conversation_id"] for c in items]


def main() -> None:
    ids = sys.argv[1:]
    if len(ids) == 2 and ids[0] == "--latest": ids = latest(int(ids[1]))
    if not ids: sys.exit(__doc__)
    allr, allt = [], []
    for cid in ids:
        r, t, exact = turn_latencies(fetch(cid)); allr += r; allt += t
        print(f"{cid}: {len(r)} replies, {len(t)} tool turns ({'ElevenLabs turn metrics' if exact else 'estimated from message times: includes speaking time'})")
    if allr:
        print(f"\nresponse latency: median {statistics.median(allr):.2f}s  p95 {pct(allr, .95):.2f}s  (targets 1.5 / 3.0)  n={len(allr)}")
    if allt:
        print(f"tool round trip:  median {statistics.median(allt):.2f}s  max {max(allt):.2f}s  (target 3.0)  n={len(allt)}")


if __name__ == "__main__":
    main()
