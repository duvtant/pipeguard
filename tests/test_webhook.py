import hashlib
import hmac
import json
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from api.routers import webhooks
from core import alerts, call_records
from core.replan import replan
from tests.conftest import predict

SECRET = "whsec_test"
app = FastAPI()
app.include_router(webhooks.router)
client = TestClient(app)
URL = "/api/webhooks/elevenlabs/post-call"


@pytest.fixture(autouse=True)
def secret(monkeypatch):
    monkeypatch.setattr(webhooks.settings, "elevenlabs_webhook_secret", SECRET)


def sign(body: str, t=None, secret=SECRET):
    t = int(time.time()) if t is None else t
    return f"t={t},v0=" + hmac.new(secret.encode(), f"{t}.{body}".encode(), hashlib.sha256).hexdigest()


def post(payload, **kw):
    body = json.dumps(payload)
    headers = {"elevenlabs-signature": kw.pop("sig", None) or sign(body), "content-type": "application/json"}
    return client.post(URL, content=body, headers=headers)


def transcript(tool_ok=None):
    turns = [{"role": "agent", "message": "Hi Anna, can your crew service EDS-01?", "time_in_call_secs": 0,
              "tool_calls": [], "tool_results": [], "triggered_guardrails": []},
             {"role": "user", "message": "Not before Friday.", "time_in_call_secs": 6}]
    if tool_ok is not None:
        turns.append({"role": "agent", "message": "", "time_in_call_secs": 9, "tool_calls": [
            {"request_id": "r1", "tool_name": "submit_availability", "params_as_json": "{}",
             "tool_has_been_called": True}],
            "tool_results": [{"request_id": "r1", "tool_name": "submit_availability", "is_error": False,
                              "result_value": json.dumps({"ok": tool_ok, "say": "x"}), "tool_latency_secs": 0.2}]})
    return turns


def event(conv="conv_1", cr=None, day="Friday", verdict="", tool_ok=None, **over):
    data = {"agent_id": "agent_x", "conversation_id": conv, "status": "done",
            "transcript": transcript(tool_ok),
            "metadata": {"call_duration_secs": 24},
            "analysis": {"transcript_summary": "Anna cannot service EDS-01 before Friday.",
                         "call_successful": "success",
                         "data_collection_results": {
                             "available_day": {"value": day, "rationale": "said so"},
                             "verdict": {"value": verdict},
                             "unit_mentioned": {"value": "EDS-01"},
                             "english_summary": {"value": "Anna is free from Friday."}},
                         "evaluation_criteria_results_list": [
                             {"criteria_id": "greeted", "result": "success", "rationale": "yes"}]},
            "conversation_initiation_client_data": {"dynamic_variables": (
                {"call_request_id": str(cr), "unit_id": "EDS-01"} if cr else {})}}
    data.update(over)
    return {"type": "post_call_transcription", "event_timestamp": int(time.time()), "data": data}


def count(db, sql):
    return db.execute(text(sql)).scalar()


@pytest.fixture
def ringing(db):
    """Three at-risk units, a baseline plan, and an answered call for EDS-01 (Anna)."""
    for u, p in (("EDS-01", .95), ("EDS-02", .90), ("EDS-03", .85)):
        predict(db, u, p)
    replan(db, emit=False)
    alerts.create_call_requests(db)
    db.commit()
    cid = count(db, "SELECT id FROM call_requests WHERE unit_id = 'EDS-01'")
    assert alerts.answer_call(db, cid)
    db.commit()
    return cid


# ---------------------------------------------------------------- signature
def test_bad_or_missing_signature_is_401_and_stores_nothing(db):
    body = json.dumps(event())
    assert client.post(URL, content=body).status_code == 401
    assert client.post(URL, content=body, headers={"elevenlabs-signature": "t=1,v0=abc"}).status_code == 401
    assert client.post(URL, content=body, headers={"elevenlabs-signature": sign(body, secret="other")}).status_code == 401
    assert client.post(URL, content=body, headers={"elevenlabs-signature": sign(body, t=int(time.time()) - 7200)}).status_code == 401
    assert count(db, "SELECT count(*) FROM calls") == 0


def test_tampered_body_is_rejected(db):
    body = json.dumps(event())
    sig = sign(body)
    assert client.post(URL, content=body.replace("Friday", "Monday"), headers={"elevenlabs-signature": sig}).status_code == 401


def test_without_a_configured_secret_everything_is_rejected(db, monkeypatch):
    monkeypatch.setattr(webhooks.settings, "elevenlabs_webhook_secret", "")
    assert post(event()).status_code == 401


def test_manual_verifier_matches_the_sdk_rules():
    body = json.dumps({"type": "x"})
    assert webhooks._manual_verify(body, sign(body), SECRET) == {"type": "x"}
    for bad in ("nope", sign(body, secret="other"), sign(body, t=int(time.time()) - 7200)):
        with pytest.raises(ValueError):
            webhooks._manual_verify(body, bad, SECRET)


# ---------------------------------------------------------------- storing
def test_call_is_stored_exactly_as_sent_and_linked(db, ringing):
    ev = event(cr=ringing, tool_ok=True)
    r = post(ev)
    assert r.status_code == 200 and r.json() == {"ok": True, "stored": True}
    row = db.execute(text("SELECT call_request_id, language, transcript, summary, data_collection, evaluation, "
                          "duration_secs, received_via FROM calls WHERE conversation_id = 'conv_1'")).mappings().one()
    assert row["transcript"] == ev["data"]["transcript"]  # untouched: tool_calls and tool_results included
    assert row["evaluation"] == [{"criteria_id": "greeted", "result": "success", "rationale": "yes"}]
    assert row["summary"] == "Anna cannot service EDS-01 before Friday."
    assert row["data_collection"]["available_day"] == "Friday" and row["data_collection"]["english_summary"]
    assert (row["call_request_id"], row["language"], row["duration_secs"], row["received_via"]) == (ringing, "en", 24, "webhook")
    assert count(db, f"SELECT state FROM call_requests WHERE id = {ringing}") == "done"


def test_retry_changes_nothing_twice(db, ringing):
    ev = event(cr=ringing, tool_ok=True)
    for _ in range(3):
        assert post(ev).status_code == 200
    assert count(db, "SELECT count(*) FROM calls") == 1
    assert count(db, "SELECT count(*) FROM events WHERE type = 'call_summary'") == 1
    detail, unit = db.execute(text("SELECT detail, unit_id FROM events WHERE type = 'call_summary'")).one()
    assert detail == "Anna is free from Friday." and unit == "EDS-01"  # the English summary wins


def test_unknown_event_types_are_acknowledged_and_ignored(db):
    assert post({"type": "post_call_audio", "data": {"conversation_id": "x"}}).json()["ignored"] == "post_call_audio"
    assert count(db, "SELECT count(*) FROM calls") == 0


@pytest.mark.parametrize("data", [{"conversation_id": "conv_min"},
                                  {"conversation_id": "conv_min", "analysis": None, "metadata": None,
                                   "transcript": None, "conversation_initiation_client_data": None,
                                   "brand_new_field": {"a": 1}},
                                  {"conversation_id": "conv_min", "analysis": {"evaluation_criteria_results": {
                                      "greeted": {"result": "success", "rationale": "ok"}}}}])
def test_missing_or_new_fields_never_reject_a_webhook(db, data):
    assert post({"type": "post_call_transcription", "data": data}).status_code == 200
    assert count(db, "SELECT count(*) FROM calls WHERE conversation_id = 'conv_min'") == 1


def test_payload_with_no_conversation_id_is_acknowledged_not_stored(db):
    r = post({"type": "post_call_transcription", "data": {"transcript": []}})
    assert r.status_code == 200 and r.json()["stored"] is False


def test_dict_style_report_card_is_normalised_to_a_list(db):
    post({"type": "post_call_transcription", "data": {"conversation_id": "conv_min", "analysis": {
        "evaluation_criteria_results": {"greeted": {"result": "failure", "rationale": "no"}}}}})
    assert count(db, "SELECT evaluation FROM calls") == [{"criteria_id": "greeted", "result": "failure", "rationale": "no"}]


def test_call_linked_earlier_by_the_phone_keeps_its_request_when_the_webhook_has_no_variables(db, ringing):
    db.execute(text("INSERT INTO calls (call_request_id, conversation_id, language) VALUES (:c, 'conv_1', 'en')"), {"c": ringing})
    db.commit()
    post(event(cr=None, tool_ok=True))
    assert count(db, "SELECT call_request_id FROM calls") == ringing
    assert count(db, f"SELECT state FROM call_requests WHERE id = {ringing}") == "done"
    assert count(db, "SELECT unit_id FROM events WHERE type = 'call_summary'") == "EDS-01"


def test_french_call_stores_french_language(db, ringing):
    db.execute(text("UPDATE call_requests SET technician_id = 2 WHERE id = :c"), {"c": ringing})
    db.commit()
    post(event(cr=ringing, tool_ok=True))
    assert count(db, "SELECT language FROM calls") == "fr"


# ---------------------------------------------------------------- fallback when a live tool call failed
def test_failed_live_tool_is_applied_from_the_after_call_extraction(db, ringing):
    post(event(cr=ringing, day="Friday", tool_ok=False))
    assert db.execute(text("SELECT earliest_day, call_request_id, source FROM constraints")).one() == (11, ringing, "voice")
    assert db.execute(text("SELECT planned_day FROM plan_items WHERE unit_id = 'EDS-01'")).scalar() == 11
    assert count(db, "SELECT received_via FROM calls") == "webhook_fallback"
    post(event(cr=ringing, day="Friday", tool_ok=False))  # a retried webhook must not apply it twice
    assert count(db, "SELECT count(*) FROM constraints") == 1
    assert count(db, "SELECT count(*) FROM events WHERE type = 'plan_changed'") == 1


def test_tool_that_never_ran_is_also_covered(db, ringing):
    post(event(cr=ringing, day="vendredi", tool_ok=None))
    assert count(db, "SELECT count(*) FROM constraints") == 1


def test_working_live_tool_is_not_applied_again(db, ringing):
    from core import voice_tools
    voice_tools.submit_availability(db, {"unit_id": "EDS-01", "technician_id": 1, "earliest_day_text": "Friday"})
    db.commit()
    post(event(cr=ringing, day="Monday", tool_ok=True))  # extractor heard something different: ignored
    assert count(db, "SELECT count(*) FROM constraints") == 1
    assert count(db, "SELECT received_via FROM calls") == "webhook"


def test_unclear_day_in_extraction_changes_nothing(db, ringing):
    post(event(cr=ringing, day="whenever", tool_ok=False))
    assert count(db, "SELECT count(*) FROM constraints") == 0
    assert count(db, "SELECT received_via FROM calls") == "webhook"


def test_verdict_fallback_records_feedback_once(db, ringing):
    post(event(cr=ringing, day="", verdict="confirmed_wear"))
    post(event(cr=ringing, day="", verdict="confirmed_wear"))
    assert count(db, "SELECT count(*) FROM feedback") == 1


# ---------------------------------------------------------------- pull fallback
def test_hangup_starts_the_timer_and_pull_fills_a_missing_webhook(db, ringing, monkeypatch):
    alerts.link_conversation(db, 1, "conv_9", ended=True)
    db.commit()
    assert count(db, "SELECT ended_at IS NOT NULL FROM calls") is True
    assert call_records.pull_pending() == 0  # hung up a moment ago: still inside the 60 s wait
    db.execute(text("UPDATE calls SET ended_at = now() - interval '2 minutes'"))
    db.commit()
    calls_made = []

    def fake_fetch(conv):
        calls_made.append(conv)
        return {"status": "done", **event("conv_9", cr=ringing, tool_ok=True)["data"]}
    monkeypatch.setattr(call_records, "fetch_conversation", fake_fetch)
    call_records._last_pull.clear()
    assert call_records.pull_pending() == 1
    row = db.execute(text("SELECT received_via, transcript IS NOT NULL AS has FROM calls")).one()
    assert tuple(row) == ("pull", True)
    assert call_records.pull_pending() == 0 and calls_made == ["conv_9"]  # has a transcript now: not asked again


def test_pull_that_is_not_ready_is_retried_but_not_hammered(db, ringing, monkeypatch):
    alerts.link_conversation(db, 1, "conv_9", ended=True)
    db.execute(text("UPDATE calls SET ended_at = now() - interval '2 minutes'"))
    db.commit()
    attempts = []
    monkeypatch.setattr(call_records, "fetch_conversation", lambda c: attempts.append(c))  # returns None
    call_records._last_pull.clear()
    call_records.pull_pending()
    call_records.pull_pending()
    assert len(attempts) == 1  # second pass is inside the retry gap
    call_records._last_pull.clear()
    call_records.pull_pending()
    assert len(attempts) == 2


def test_pull_gives_up_on_very_old_calls(db, ringing, monkeypatch):
    alerts.link_conversation(db, 1, "conv_9", ended=True)
    db.execute(text("UPDATE calls SET ended_at = now() - interval '1 hour'"))
    db.commit()
    monkeypatch.setattr(call_records, "fetch_conversation", lambda c: pytest.fail("should not be asked"))
    call_records._last_pull.clear()
    assert call_records.pull_pending() == 0
