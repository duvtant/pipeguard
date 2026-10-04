#!/usr/bin/env python3
"""Is the demo ready? One command, plain PASS / WARN / FAIL lines, exit code 1 if anything FAILs.

    python scripts/preflight.py --base https://pipeguard.blunelabs.com --prod \
        --admin-token "$ADMIN_TOKEN" --voice-secret "$VOICE_TOOL_SECRET"

Standard library only, so it runs on a laptop, in Codespaces or on the server. It never prints a secret.

--prod     missing secrets and open admin endpoints are FAIL (otherwise WARN)
--full     also plays simulate-call end to end (needs --admin-token). This CHANGES the demo state:
           reset before the real demo.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"
results: list[tuple[str, str, str]] = []


def record(status: str, name: str, detail: str = "") -> None:
    results.append((status, name, detail))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def call(base: str, path: str, method: str = "GET", body=None, headers=None, timeout: float = 10, follow: bool = True):
    """(status, parsed json or text, seconds). status 0 = could not connect."""
    data = json.dumps(body).encode() if isinstance(body, (dict, list)) else body
    hdrs = {"content-type": "application/json", **(headers or {})} if data is not None else dict(headers or {})
    req = urllib.request.Request(base.rstrip("/") + path, data=data, headers=hdrs, method=method)
    opener = urllib.request.build_opener() if follow else urllib.request.build_opener(NoRedirect)
    t0 = time.perf_counter()
    try:
        with opener.open(req, timeout=timeout) as resp:
            raw, status = resp.read().decode("utf-8", "replace"), resp.status
    except urllib.error.HTTPError as exc:
        raw, status = exc.read().decode("utf-8", "replace"), exc.code
    except Exception as exc:
        return 0, f"{type(exc).__name__}: {exc}", time.perf_counter() - t0
    try:
        return status, json.loads(raw), time.perf_counter() - t0
    except ValueError:
        return status, raw, time.perf_counter() - t0


def strict(prod: bool) -> str:
    return FAIL if prod else WARN


def check_health(a) -> dict | None:
    status, h, _ = call(a.base, "/api/health")
    if status == 0:
        record(FAIL, "API reachable", f"{h}. Is the API container running at {a.base}?")
        return None
    if status != 200 or not isinstance(h, dict) or not h.get("ok"):
        record(FAIL, "API health", f"HTTP {status}: {h if isinstance(h, str) else json.dumps(h)[:150]}")
        return None
    record(PASS, "API health", f"database ok, day {h.get('sim_day')}")
    if h.get("mock_api"):
        record(WARN, "Real data", "MOCK_API is on: the API is serving fixtures, not the database")
    return h


def check_pipeline(h: dict) -> None:
    age, running = h.get("simulator_tick_age_secs"), h.get("clock_status") == "running"
    if running:
        ok = age is not None and age < 15
        record(PASS if ok else FAIL, "Simulator ticking", f"last tick {age}s ago" if ok else
               f"clock says running but nothing ticked for {age}s: is the simulator container up?")
    else:
        record(PASS, "Simulator", "clock paused (press play when the demo starts)")
    lag = h.get("engine_lag_days")
    if lag is None:
        record(FAIL, "Engine predictions", "no predictions yet: engine not running, or its model files are missing")
    else:
        record(PASS if lag <= 2 else FAIL, "Engine keeping up", f"{lag} day(s) behind the simulator")
    src = h.get("data_source") or {}
    live, fallback = src.get("live", 0), src.get("fallback", 0)
    if live == 0 and fallback == 0:
        record(FAIL, "Prediction source", "no predictions")
    elif fallback:
        record(WARN, "Prediction source", f"{fallback} unit(s) on backup predictions, {live} live")
    else:
        record(PASS, "Prediction source", f"all {live} live")


def check_secrets(a, h: dict) -> None:
    for key, label in (("admin_token_set", "ADMIN_TOKEN"), ("voice_tool_secret_set", "VOICE_TOOL_SECRET"),
                       ("webhook_secret_set", "ELEVENLABS_WEBHOOK_SECRET"), ("elevenlabs_configured", "ELEVENLABS_API_KEY and AGENT_ID")):
        record(PASS if h.get(key) else strict(a.prod), f"{label} set", "" if h.get(key) else "empty on the server")


def check_reads(a) -> None:
    status, fleet, secs = call(a.base, "/api/fleet")
    if status != 200 or not isinstance(fleet, dict):
        record(FAIL, "Fleet", f"HTTP {status}")
    else:
        n = len(fleet.get("units", []))
        red = sum(1 for u in fleet["units"] if u.get("risk_status") == "at_risk")
        record(PASS if n >= 1 and secs < 2 else FAIL, "Fleet", f"{n} units, {red} at risk, {secs * 1000:.0f} ms")
        if n != 100:
            record(WARN, "Fleet size", f"{n} units (the demo scenario has 100): was the seed run?")
    status, plan, _ = call(a.base, "/api/plan")
    record(PASS if status == 200 and isinstance(plan, list) else FAIL, "Plan", f"{len(plan) if isinstance(plan, list) else '?'} items")
    status, techs, _ = call(a.base, "/api/technicians")
    ok = status == 200 and isinstance(techs, list) and len(techs) >= 2 and all(t.get("field_page_id") for t in techs)
    record(PASS if ok else FAIL, "Technicians", f"{len(techs) if isinstance(techs, list) else '?'} with phone pages")
    status, ev, _ = call(a.base, "/api/events")
    record(PASS if status == 200 and isinstance(ev, list) else FAIL, "Decision log", f"{len(ev) if isinstance(ev, list) else '?'} events")


def check_stream(a) -> None:
    req = urllib.request.Request(a.base.rstrip("/") + "/api/stream")
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            first = resp.readline().decode("utf-8", "replace").strip()
        record(PASS if first.startswith(":") or first.startswith("id:") else FAIL, "Live event stream", f"first line: {first[:40]!r}")
    except Exception as exc:
        record(FAIL, "Live event stream", f"{type(exc).__name__}: {exc}")


def check_impact(a) -> None:
    body = {"crews_per_station": 2, "cost_breakdown": 200000, "cost_service": 20000, "threshold": None, "horizon_days": None}
    status, out, secs = call(a.base, "/api/simulate", "POST", body, timeout=30)
    if status == 503:
        record(FAIL, "Impact tab", "503: ml/artifacts/oof_predictions.parquet is missing in the container")
    elif status != 200 or not isinstance(out, dict) or len(out.get("policies", [])) != 3:
        record(FAIL, "Impact tab", f"HTTP {status}")
    else:
        text = (out.get("headline") or {}).get("text", "")
        record(PASS if secs < 1.5 else WARN, "Impact tab", f"{secs * 1000:.0f} ms. {text[:70]}")


def check_dashboard(a) -> None:
    status, body, _ = call(a.base, "/")
    ok = status == 200 and isinstance(body, str) and "<html" in body.lower()
    record(PASS if ok else WARN, "Dashboard page", "served" if ok else f"HTTP {status}: the web container or Caddy route may be down")


def check_security(a) -> None:
    s = strict(a.prod)
    status, _, _ = call(a.base, "/api/testmode/faults")
    record(PASS if status == 401 else s, "Admin endpoints locked", "401 without a token" if status == 401 else f"HTTP {status} without a token: anyone can use test mode and the reset")
    status, _, _ = call(a.base, "/api/voice/tools/unit-status", "POST", {})
    record(PASS if status == 401 else s, "Voice tools locked", "401 without the secret" if status == 401 else f"HTTP {status} without the secret")
    status, _, _ = call(a.base, "/api/webhooks/elevenlabs/post-call", "POST", {"type": "post_call_transcription"})
    record(PASS if status == 401 else FAIL, "Webhook rejects unsigned posts", f"HTTP {status}")
    if a.base.startswith("https://"):
        status, _, _ = call("http://" + a.base[len("https://"):], "/api/health", follow=False)
        record(PASS if status in (301, 302, 307, 308) else s, "HTTP redirects to HTTPS", f"HTTP {status}")
    else:
        record(WARN, "HTTPS", "base URL is plain http: the microphone needs HTTPS on the phone page")
    if a.admin_token:
        status, _, _ = call(a.base, "/api/testmode/faults", headers={"X-Admin-Token": a.admin_token})
        record(PASS if status == 200 else FAIL, "Admin token works", f"HTTP {status}")
    if a.voice_secret:
        status, out, secs = call(a.base, "/api/voice/tools/unit-status", "POST", {"unit_id": "nope"},
                                 headers={"Authorization": f"Bearer {a.voice_secret}"})
        ok = status == 200 and isinstance(out, dict) and "say" in out
        record(PASS if ok else FAIL, "Voice secret works", f"HTTP {status}, answered in {secs * 1000:.0f} ms" if ok else f"HTTP {status}")


def check_full(a) -> None:
    if not a.admin_token:
        record(WARN, "Simulate-call", "skipped: needs --admin-token")
        return
    hdr = {"X-Admin-Token": a.admin_token}
    _, ev, _ = call(a.base, "/api/events")
    last = max((e["event_id"] for e in ev), default=0) if isinstance(ev, list) else 0
    status, out, _ = call(a.base, "/api/admin/simulate-call", "POST", {}, headers=hdr)
    if status != 200:
        record(FAIL, "Simulate-call", f"HTTP {status}: {out if isinstance(out, str) else json.dumps(out)[:120]}")
        return
    deadline, seen = time.time() + 20, set()
    while time.time() < deadline and "call_summary" not in seen:
        time.sleep(1)
        _, new, _ = call(a.base, f"/api/events?after_id={last}")
        seen = {e["type"] for e in new} if isinstance(new, list) else seen
    want = {"call_requested", "call_answered", "constraint_added", "plan_changed", "call_summary"}
    record(PASS if want <= seen else FAIL, "Simulate-call end to end",
           "all five steps reached the log (now reset before the demo)" if want <= seen else f"missing: {sorted(want - seen)}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default=os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000"))
    ap.add_argument("--admin-token", default=os.environ.get("ADMIN_TOKEN", ""))
    ap.add_argument("--voice-secret", default=os.environ.get("VOICE_TOOL_SECRET", ""))
    ap.add_argument("--prod", action="store_true")
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    h = check_health(a)
    if h:
        check_pipeline(h)
        check_secrets(a, h)
        check_reads(a)
        check_stream(a)
        check_impact(a)
        check_dashboard(a)
        check_security(a)
        if a.full:
            check_full(a)

    if a.json:
        print(json.dumps([{"status": s, "check": n, "detail": d} for s, n, d in results], indent=2))
    else:
        width = max(len(n) for _, n, _ in results)
        for status, name, detail in results:
            print(f"{status:<5} {name:<{width}}  {detail}")
        counts = {k: sum(1 for s, _, _ in results if s == k) for k in (PASS, WARN, FAIL)}
        print(f"\n{counts[PASS]} passed, {counts[WARN]} warnings, {counts[FAIL]} failed against {a.base}")
        print("READY" if not counts[FAIL] else "NOT READY: fix the FAIL lines first")
    return 1 if any(s == FAIL for s, _, _ in results) else 0


if __name__ == "__main__":
    sys.exit(main())
