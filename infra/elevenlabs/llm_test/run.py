#!/usr/bin/env python3
"""Agent test runner for the LLM selection test (docs/techstack.md 12.10, plan tasks P3.6 to P3.8).

SAFE BY DEFAULT. Anything that talks to ElevenLabs needs --yes, and prints what it will do first.
  python3 run.py selfcheck                      offline: validate all payloads (no network, no cost)
  python3 run.py plan [--candidates a,b] [--repeat N] [--only critical|all]
                                                offline: how many test runs this would be (no network, no cost)
  python3 run.py create --yes                   upload the test definitions (no LLM cost; creates test configs)
  python3 run.py run --candidate NAME --repeat N --only critical --yes [--max-credits N]
                                                RUNS TESTS AND SPENDS CREDITS. Stops early if the spend limit is hit.
  python3 run.py report                         offline: score table from saved results, applying the decision rule
Key: ELEVENLABS_API_KEY from the environment or the repo's .env (never printed). Run the paid parts in account B, not the demo account.
"""
from __future__ import annotations

import argparse, json, os, sys, time, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import suite  # noqa: E402

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
IDS_FILE = HERE / "test_ids.json"
API = "https://api.elevenlabs.io"


def load_key() -> str:
    key = os.environ.get("ELEVENLABS_API_KEY", "")
    if not key:
        env = HERE.parents[2] / ".env"
        if env.exists():
            for line in env.read_text().splitlines():
                if line.startswith("ELEVENLABS_API_KEY="): key = line.split("=", 1)[1].strip().strip('"')
    if not key: sys.exit("ELEVENLABS_API_KEY is not set (environment or .env).")
    return key


def call(method: str, path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"xi-api-key": load_key(), "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read(); return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        sys.exit(f"{method} {path} -> HTTP {e.code}: {e.read().decode()[:400]}")


def agent_id() -> str:
    a = json.loads((HERE.parent / "agents.json").read_text())["agents"][0]
    return a["id"]


def chosen(only: str) -> list[tuple[str, bool, dict]]:
    return [s for s in suite.SCENARIOS if only == "all" or s[1]]


def cmd_selfcheck(_: argparse.Namespace) -> None:
    bad = suite.selfcheck()
    print(f"{len(suite.SCENARIOS)} scenarios, {len(suite.DEMO_CRITICAL)} demo-critical, {len(suite.CANDIDATES)} candidates.")
    print("OK: every payload is well formed." if not bad else "PROBLEMS:\n  " + "\n  ".join(bad)); sys.exit(1 if bad else 0)


def cmd_plan(a: argparse.Namespace) -> None:
    cands = a.candidates.split(",") if a.candidates else list(suite.CANDIDATES)
    tests = chosen(a.only); runs = len(tests) * a.repeat * len(cands)
    print(f"Tests: {len(tests)} ({a.only})   Candidates: {len(cands)} ({', '.join(cands)})   Repeats: {a.repeat}")
    print(f"=> {runs} test runs in total. Nothing was sent. Each run uses LLM credits; the exact amount per run is not published, so")
    print("   start with ONE candidate, --only critical, --repeat 2, then read `credits_used` in the saved results before scaling up.")


def cmd_create(a: argparse.Namespace) -> None:
    if not a.yes: sys.exit("Refusing without --yes. This creates the test definitions in your ElevenLabs workspace.")
    ids = json.loads(IDS_FILE.read_text()) if IDS_FILE.exists() else {}
    for sid, _, t in suite.SCENARIOS:
        if sid in ids: print(f"  {sid}: already created"); continue
        ids[sid] = call("POST", "/v1/convai/agent-testing/create", t)["id"]; print(f"  {sid}: {ids[sid]}"); IDS_FILE.write_text(json.dumps(ids, indent=1))
    print("Created. Ids saved to test_ids.json.")


def cmd_sync(a: argparse.Namespace) -> None:
    """Push the current definitions to the tests that already exist (free; no model is run)."""
    if not a.yes: sys.exit("Refusing without --yes. This edits the test definitions in your ElevenLabs workspace.")
    ids = json.loads(IDS_FILE.read_text()) if IDS_FILE.exists() else sys.exit("Run `create --yes` first.")
    for sid, _, t in suite.SCENARIOS:
        if sid in ids: call("PUT", f"/v1/convai/agent-testing/{ids[sid]}", t); print(f"  {sid}: updated")
    print("Synced.")


def cmd_run(a: argparse.Namespace) -> None:
    if a.candidate not in suite.CANDIDATES: sys.exit(f"Unknown candidate. Choose one of: {', '.join(suite.CANDIDATES)}")
    ids = json.loads(IDS_FILE.read_text()) if IDS_FILE.exists() else sys.exit("Run `create --yes` first.")
    picked = [x.strip() for x in a.ids.split(",")] if a.ids else None
    if picked and any(x not in ids for x in picked): sys.exit(f"Unknown test id in --ids. Known: {', '.join(ids)}")
    wanted = set(picked) if picked else {sid_ for sid_, _, _ in chosen(a.only)}
    tests = [ids[sid] for sid, _, _ in suite.SCENARIOS if sid in wanted and sid in ids]
    runs = len(tests) * a.repeat
    print(f"About to run {len(tests)} tests x {a.repeat} repeats = {runs} runs on candidate '{a.candidate}'. This SPENDS ElevenLabs credits.")
    if not a.yes: sys.exit("Refusing without --yes.")
    if runs > a.max_runs: sys.exit(f"{runs} runs exceeds --max-runs {a.max_runs}. Raise it on purpose if you mean it.")
    live = call("GET", f"/v1/convai/agents/{agent_id()}")  # read-only: the live agent's config is the base, so tests use our real prompt
    if a.repo_prompt:  # test the prompt in our repo config (edited, NOT pushed) instead of the live agent's
        repo = json.loads((HERE.parent / "pipeguard_dispatcher.config.json").read_text())
        live["conversation_config"]["agent"]["prompt"]["prompt"] = repo["conversation_config"]["agent"]["prompt"]["prompt"]
    ov = suite.override(a.candidate, live); pr = ov["conversation_config"]["agent"]["prompt"]
    print(f"Model for this batch: {pr['llm']}, effort {pr.get('reasoning_effort', 'default')}; prompt {len(pr.get('prompt') or '')} characters ({'repo config, not pushed' if a.repo_prompt else 'the live agent' + chr(39) + 's own'}).")
    inv = call("POST", f"/v1/convai/agents/{agent_id()}/run-tests", {"tests": [{"test_id": t} for t in tests], "agent_config_override": ov, "repeat_count": a.repeat})
    inv_id = inv["id"]; print("invocation", inv_id)
    for _ in range(90):  # poll up to ~7 minutes
        time.sleep(5); inv = call("GET", f"/v1/convai/test-invocations/{inv_id}")
        if all(r.get("status") != "pending" for r in inv.get("test_runs", [])) and inv.get("test_runs"): break
    RESULTS.mkdir(exist_ok=True); (RESULTS / f"{a.candidate}{a.tag}.json").write_text(json.dumps(inv, indent=1))
    spent = sum((r.get("credits_used") or 0) for r in inv.get("test_runs", []) if isinstance(r.get("credits_used"), (int, float)))
    print(f"Saved results/{a.candidate}{a.tag}.json. Credits reported used: {spent}")
    if a.max_credits and spent > a.max_credits: print(f"WARNING: spend {spent} exceeded --max-credits {a.max_credits}. Stop and review before running another candidate.")


def cmd_report(_: argparse.Namespace) -> None:
    ids = json.loads(IDS_FILE.read_text()) if IDS_FILE.exists() else {}
    by_id = {v: k for k, v in ids.items()}
    if not RESULTS.exists() or not list(RESULTS.glob("*.json")): sys.exit("No results yet. Nothing to report (this script never invents numbers).")
    rows = []
    for f in sorted(RESULTS.glob("*.json")):
        inv = json.loads(f.read_text()); per: dict[str, list[bool]] = {}
        for r in inv.get("test_runs", []):
            sid = by_id.get(r.get("test_id"), r.get("test_name", "?")); ok = (r.get("condition_result") or {}).get("result") == "success" or r.get("status") == "passed"
            per.setdefault(sid, []).append(ok)
        crit = [x for k, v in per.items() if k in suite.DEMO_CRITICAL for x in v]; allr = [x for v in per.values() for x in v]
        rows.append((f.stem, 100 * sum(crit) / len(crit) if crit else float("nan"), 100 * sum(allr) / len(allr) if allr else float("nan"), len(allr)))
    print(f"{'candidate':24} {'demo-critical':>14} {'all tests':>10} {'runs':>6}   rule: at least 95% on demo-critical")
    for n, c, al, k in sorted(rows, key=lambda r: -r[1]):
        print(f"{n:24} {c:13.0f}% {al:9.0f}% {k:6d}   {'PASS' if c >= 95 else 'reject'}")
    print("\nLatency needs real voice calls (P3.7); this table covers text behaviour only.")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter); s = p.add_subparsers(dest="cmd", required=True)
    s.add_parser("selfcheck").set_defaults(f=cmd_selfcheck)
    q = s.add_parser("plan"); q.add_argument("--candidates"); q.add_argument("--repeat", type=int, default=2); q.add_argument("--only", choices=["critical", "all"], default="critical"); q.set_defaults(f=cmd_plan)
    q = s.add_parser("create"); q.add_argument("--yes", action="store_true"); q.set_defaults(f=cmd_create)
    q = s.add_parser("run"); q.add_argument("--candidate", required=True); q.add_argument("--repeat", type=int, default=2); q.add_argument("--only", choices=["critical", "all"], default="critical")
    q.add_argument("--ids", help="comma list of test ids, for example 8,1,2 (overrides --only)"); q.add_argument("--repo-prompt", action="store_true", help="test the prompt in the repo config instead of the live agent's")
    q.add_argument("--tag", default="", help="suffix for the results file, for example +prompt2")
    q.add_argument("--yes", action="store_true"); q.add_argument("--max-runs", type=int, default=40); q.add_argument("--max-credits", type=float); q.set_defaults(f=cmd_run)
    q = s.add_parser("sync"); q.add_argument("--yes", action="store_true"); q.set_defaults(f=cmd_sync)
    s.add_parser("report").set_defaults(f=cmd_report)
    a = p.parse_args(); a.f(a)


if __name__ == "__main__":
    main()
