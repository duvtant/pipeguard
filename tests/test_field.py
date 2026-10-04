import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from api.routers import field
from core import alerts
from tests.conftest import predict
from tests.test_alerts import expire, ring_one, states

app = FastAPI()
app.include_router(field.router)
client = TestClient(app)


def test_unknown_slug_is_404(db):
    assert client.post("/api/field/nope/answer").status_code == 404


def test_answer_returns_signed_url_and_string_variables(db, monkeypatch):
    monkeypatch.setattr(field, "_signed_url", lambda: ("wss://x/y?conversation_id=conv_1", "conv_1"))
    db.execute(text("INSERT INTO plan_items (unit_id, planned_day, crew, expected_saving, reason, state) VALUES ('EDS-01', 11, 0, 0, '', 'planned')"))
    db.commit()
    ring_one(db)
    r = client.post("/api/field/slug-anna/answer")
    assert r.status_code == 200
    body = r.json()
    assert body["language"] == "en" and body["signed_url"].startswith("wss://")
    dv = body["dynamic_variables"]
    assert all(isinstance(v, str) for v in dv.values())
    assert dv["unit_id"] == "EDS-01" and dv["station_name"] == "Edson" and dv["proposed_day"] == "Friday"
    assert dv["sim_today"] == "Thursday, October 15" and dv["rul_low"] == "6"
    assert states(db)[0][4] == "answered"
    assert db.execute(text("SELECT conversation_id FROM calls")).scalar() == "conv_1"


def test_french_technician_gets_french(db, monkeypatch):
    monkeypatch.setattr(field, "_signed_url", lambda: ("wss://x", None))
    ring_one(db)
    db.execute(text("UPDATE call_requests SET technician_id = 2"))
    db.commit()
    assert client.post("/api/field/slug-marc/answer").json()["language"] == "fr"


def test_answer_with_nothing_ringing_or_after_expiry_is_410(db, monkeypatch):
    monkeypatch.setattr(field, "_signed_url", lambda: ("wss://x", None))
    assert client.post("/api/field/slug-anna/answer").status_code == 410
    cid = ring_one(db)
    expire(db, cid)
    assert client.post("/api/field/slug-anna/answer").status_code == 410


def test_signed_url_failure_keeps_the_ring_alive(db, monkeypatch):
    from fastapi import HTTPException

    def boom():
        raise HTTPException(502, "x")
    monkeypatch.setattr(field, "_signed_url", boom)
    ring_one(db)
    assert client.post("/api/field/slug-anna/answer").status_code == 502
    assert states(db)[0][4] == "ringing"


def test_no_api_key_gives_mock_url(db):
    assert field._signed_url()[0] == field.MOCK_SIGNED_URL


def test_decline_rings_backup_and_second_decline_is_410(db):
    ring_one(db)
    assert client.post("/api/field/slug-anna/decline").json() == {"ok": True}
    assert [r[4] for r in states(db)] == ["missed", "ringing"]
    assert client.post("/api/field/slug-anna/decline").status_code == 410
    assert client.post("/api/field/slug-bo/decline").json() == {"ok": True}
    assert states(db)[1][4] == "escalated"


def test_poll_rings_sends_each_ring_once(db):
    ring_one(db)
    sent = set()
    frames = field._poll_rings(1, sent)
    assert len(frames) == 1 and frames[0].startswith("event: ring\ndata: ")
    assert '"expires_at"' in frames[0] and '"technician_name": "Anna Primary"' in frames[0]
    assert field._poll_rings(1, sent) == []
    assert field._poll_rings(2, set()) == []  # someone else's phone


def test_feedback_is_idempotent_and_part_replaced_restarts_life(db):
    body = {"unit_id": "EDS-01", "verdict": "part_replaced", "note": "new bearing"}
    assert client.post("/api/field/slug-anna/feedback", json=body).json()["threshold"] == 0.5
    client.post("/api/field/slug-anna/feedback", json=body)
    assert db.execute(text("SELECT count(*) FROM feedback")).scalar() == 1
    assert db.execute(text("SELECT count(*) FROM events WHERE type = 'feedback_received'")).scalar() == 1
    assert db.execute(text("SELECT life_start_day, serviced_count FROM units WHERE id = 'EDS-01'")).first() == (11, 1)
    assert client.post("/api/field/slug-anna/feedback", json={**body, "verdict": "meh"}).status_code == 422
    assert client.post("/api/field/slug-anna/feedback", json={**body, "unit_id": "XXX-99"}).status_code == 422


def test_conversation_link_is_idempotent_and_hangup_finishes_call(db, monkeypatch):
    monkeypatch.setattr(field, "_signed_url", lambda: ("wss://x", None))
    ring_one(db)
    client.post("/api/field/slug-anna/answer")
    for ended in (False, False, True, True):
        assert client.post("/api/field/slug-anna/conversation",
                           json={"conversation_id": "conv_9", "ended": ended}).json() == {"ok": True}
    assert db.execute(text("SELECT count(*) FROM calls")).scalar() == 1
    assert states(db)[0][4] == "done"
