"""Durable boundaries, shared budgets and evidence workflow; no live providers."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4
from types import SimpleNamespace
import pytest
from sqlalchemy import select

from app import outbound_guard as guard
from app.database import Base, SessionLocal
from app.models import OutboundQuota, OutboundAttempt
from .conftest import requires_db

pytestmark = requires_db

@pytest.fixture(autouse=True)
def tables():
    Base.metadata.create_all(guard.engine)


def email(): return f"{uuid4()}@realmail.co"
def phone(): return "+1202" + str(uuid4().int % 10000000).zfill(7)


def test_shared_budget_competing_accounts():
    channel = "budget-" + uuid4().hex[:10]
    calls = []
    def worker(i):
        return guard.invoke(channel, email(), str(i), "intent", [],
                            lambda: (calls.append(i) or (str(i + 1), None)), budget=5)
    with ThreadPoolExecutor(12) as pool:
        results = list(pool.map(worker, range(24)))
    assert sum(bool(r[0]) for r in results) == len(calls) == 5


def test_unknown_rejected_and_replay_never_refund_budget():
    channel = "budget-" + uuid4().hex[:10]
    target = email()
    assert guard.invoke(channel, target, "a", "one", [], lambda: ("receipt", None), budget=3)[0]
    assert guard.invoke(channel, target, "a", "one", [], lambda: pytest.fail("replayed"), budget=3)[0]
    guard.invoke(channel, email(), "b", "two", [], lambda: (None, "timeout"), budget=3)
    guard.invoke(channel, email(), "c", "three", [], lambda: (None, guard.RejectedDelivery("429")), budget=3)
    assert "budget exhausted" in guard.invoke(channel, email(), "d", "four", [], lambda: pytest.fail("over quota"), budget=3)[1]


def test_stale_higher_cap_cannot_reopen_budget():
    channel = "budget-" + uuid4().hex[:10]
    for _ in range(3):
        assert guard.invoke(channel, email(), "a", "one", [], lambda: ("id", None), budget=5)[0]
    assert guard.invoke(channel, email(), "a", "two", [], lambda: pytest.fail("over quota"), budget=2)[0] is None
    assert guard.invoke(channel, email(), "a", "three", [], lambda: pytest.fail("stale cap"), budget=100)[0] is None


def test_nested_provider_reserves_once():
    channel = "nested-" + uuid4().hex[:10]
    calls = []
    @guard.provider(channel)
    def inner(to, body):
        calls.append(1)
        return "receipt", None
    @guard.provider(channel)
    def outer(to, body):
        return inner(to, body)
    target = email()
    assert outer(target, "body", operation_key="one") == ("receipt", None)
    assert outer(target, "body", operation_key="one")[0] is None
    with SessionLocal() as db:
        assert db.query(OutboundAttempt).filter(OutboundAttempt.scope == guard.recipient_scope(channel, target)).count() == 1
    assert calls == [1]


def test_sms_unknown_stops_carriers_and_cross_account_retry(monkeypatch):
    from app.integrations import sms, telco
    calls = []
    monkeypatch.setattr(sms, "is_configured", lambda: True)
    monkeypatch.setattr(sms, "_use_plivo", lambda: False)
    monkeypatch.setattr(telco, "sms_providers", lambda: ["signalwire", "twilio"])
    monkeypatch.setattr(sms, "_send_once", lambda *args: (calls.append(args[0]) or (None, "timeout")))
    target = phone()
    assert sms.send_with_error(target, "hello", account="a")[0] is None
    assert sms.send_with_error(target, "new body", account="b")[0] is None
    assert calls == ["signalwire"]


def test_sms_explicit_rejection_allows_one_fallback(monkeypatch):
    from app.integrations import sms, telco
    calls = []
    monkeypatch.setattr(sms, "is_configured", lambda: True)
    monkeypatch.setattr(sms, "_use_plivo", lambda: False)
    monkeypatch.setattr(telco, "sms_providers", lambda: ["signalwire", "twilio"])
    def send(provider, *args):
        calls.append(provider)
        return (None, guard.RejectedDelivery("429")) if provider == "signalwire" else ("receipt", None)
    monkeypatch.setattr(sms, "_send_once", send)
    assert sms.send_with_error(phone(), "hello")[0] == "receipt"
    assert calls == ["signalwire", "twilio"]


def test_direct_email_provider_change_cannot_bypass_unknown(monkeypatch):
    from app.integrations import resend, sendgrid
    calls = []
    for mod in (resend, sendgrid): monkeypatch.setattr(mod, "has_key", lambda: True)
    def timeout(*a, **kw):
        calls.append(1)
        raise TimeoutError()
    monkeypatch.setattr(resend.httpx, "post", timeout)
    target = email()
    assert resend.send_with_error(target, "subject", "body", from_email="sender@realmail.co")[0] is None
    assert sendgrid.send_with_error(target, "subject", "body", from_email="other@realmail.co")[0] is None
    assert calls == [1]


def test_mailer_never_falls_back_after_gmail_unknown(monkeypatch):
    from app.integrations import gmail, mailer
    monkeypatch.setattr(gmail, "is_configured", lambda *_: True)
    monkeypatch.setattr(gmail, "send_message", lambda *a, **k: None)
    monkeypatch.setattr(mailer.smtplib, "SMTP", lambda *a, **k: pytest.fail("SMTP retry"))
    assert not mailer.send_email(to=email(), subject="subject", html="body")


def unknown(channel="email"):
    recipient = email()
    operation = str(uuid4())
    guard.invoke(channel, recipient, "test", operation, [], lambda: (None, "timeout"))
    return recipient, operation, guard.digest(guard.recipient_scope(channel, recipient), "test", operation)


def resolution(decision="not_accepted", state="unknown"):
    return {"decision": decision, "expected_state": state,
            "evidence": "Provider support confirms request was never accepted.",
            "provider_reference": "support-case-123", "provider_id": "receipt-123" if decision == "accepted" else None}


def test_resolution_records_actor_and_never_retries(client, auth_headers):
    target, op, key = unknown()
    url = f"/messages/delivery-attempts/{key}/resolve"
    assert client.post(url, json=resolution()).status_code == 401
    assert client.post(url, json=resolution(), headers=auth_headers).status_code == 200
    assert client.post(url, json=resolution(), headers=auth_headers).status_code == 409
    assert guard.invoke("email", target, "test", op, [], lambda: pytest.fail("old key retried"))[0] is None
    assert guard.invoke("email", target, "test", "new-intent", [], lambda: ("new", None))[0] == "new"
    history = client.get(f"/messages/delivery-attempts/{key}/history", headers=auth_headers).json()
    assert len(history) == 1 and history[0]["actor"] and history[0]["decision"] == "not_accepted"


def test_pending_worker_cannot_be_released(client, auth_headers):
    target, operation = email(), str(uuid4())
    entered, release = Event(), Event()
    def send():
        entered.set()
        assert release.wait(10)
        return None, "timeout"
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(guard.invoke, "email", target, "test", operation, [], send)
        assert entered.wait(10)
        key = guard.digest(guard.recipient_scope("email", target), "test", operation)
        try:
            url = f"/messages/delivery-attempts/{key}/resolve"
            assert client.post(url, json=resolution(state="pending"), headers=auth_headers).status_code == 409
            assert client.post(url, json=resolution("keep_held", "pending"), headers=auth_headers).status_code == 200
            assert guard.invoke("email", target, "other", "new", [], lambda: pytest.fail("released"))[0] is None
        finally:
            release.set()
        assert future.result(timeout=10)[0] is None


def test_competing_operators_only_one_resolves(client, auth_headers):
    _, _, key = unknown()
    url = f"/messages/delivery-attempts/{key}/resolve"
    with ThreadPoolExecutor(2) as pool:
        outcomes = list(pool.map(lambda _: client.post(url, json=resolution(), headers=auth_headers).status_code, range(2)))
    assert sorted(outcomes) == [200, 409]


def test_accepted_resolution_requires_receipt(client, auth_headers):
    _, _, key = unknown()
    body = resolution("accepted"); body["provider_id"] = None
    url = f"/messages/delivery-attempts/{key}/resolve"
    assert client.post(url, json=body, headers=auth_headers).status_code == 422
    body["provider_id"] = "provider-receipt"
    assert client.post(url, json=body, headers=auth_headers).json()["state"] == "accepted"


def _quota_process(args):
    channel, recipient = args
    return guard.invoke(channel, recipient, "worker", "intent", [], lambda: ("receipt", None), budget=3)


def test_budget_multiple_processes():
    import multiprocessing
    from concurrent.futures import ProcessPoolExecutor
    channel = "budget-" + uuid4().hex[:10]
    with ProcessPoolExecutor(4, mp_context=multiprocessing.get_context("spawn")) as pool:
        results = list(pool.map(_quota_process, [(channel, email()) for _ in range(12)]))
    assert sum(bool(result[0]) for result in results) == 3


def test_sms_unknown_never_queues_mac_bridge(client, auth_headers, monkeypatch):
    from app.integrations import sms
    from app.config import settings
    from app import runtime_config
    from app.models import Message
    target = phone()
    monkeypatch.setattr(runtime_config, "apply_to_settings", lambda _: None)
    monkeypatch.setattr(settings, "bridge_token", "test-bridge-only")
    monkeypatch.setattr(sms, "is_configured", lambda: True)
    monkeypatch.setattr(sms, "send_with_error", lambda *a, **kw: (None, "unknown carrier acceptance"))
    response = client.post("/sms/send", json={"to": target, "message": "test body"}, headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "Needs Review" and not response.json()["ok"]
    with SessionLocal() as db:
        db.query(Message).filter(Message.to_email == target).delete(synchronize_session=False)
        db.commit()


def test_auto_call_direct_provider_shares_dispatcher_key(monkeypatch):
    from app.integrations import voice, twilio_voice
    target = phone()
    calls = []
    monkeypatch.setattr(voice, "is_configured", lambda: True)
    monkeypatch.setattr(voice, "_mod", lambda: twilio_voice)
    monkeypatch.setattr(twilio_voice, "is_configured", lambda: True)
    # Replace transport internals while preserving the public boundary decorator.
    @guard.provider("auto-call", recipient="lead_phone")
    def transport(lead_phone, lead_id):
        calls.append(1)
        return "receipt", None
    monkeypatch.setattr(twilio_voice, "place_auto_call", transport)
    assert voice.place_auto_call(target, "lead-one")[0] == "receipt"
    assert twilio_voice.place_auto_call(target, "lead-two")[0] is None
    assert calls == [1]


@pytest.mark.parametrize("outcome", ["accepted", "unknown"])
def test_bridge_claim_is_exclusive_and_ack_requires_ownership(client, monkeypatch, outcome):
    from app.config import settings
    from app import sms_engine
    from app.models import Message
    monkeypatch.setattr(settings, "bridge_token", "test-bridge-only")
    monkeypatch.setattr(sms_engine, "sms_block_reason", lambda *a, **k: None)
    headers = {"X-Bridge-Token": "test-bridge-only"}
    with SessionLocal() as db:
        m = Message(channel="sms", direction="outbound", to_email=phone(), body="bridge text",
                    from_account="bridge-test", status="Queued")
        db.add(m); db.commit(); message_id = str(m.id)
    try:
        with ThreadPoolExecutor(2) as pool:
            pages = list(pool.map(lambda _: client.get("/bridge/outbox", headers=headers).json(), range(2)))
        claims = [item for page in pages for item in page if item["id"] == message_id]
        assert len(claims) == 1
        assert not any(item["id"] == message_id for item in client.get("/bridge/outbox", headers=headers).json())
        data = {"id": message_id, "claim_token": "incorrect-claim-token-value", "outcome": outcome}
        assert client.post("/bridge/sent", json=data, headers=headers).status_code == 403
        data["claim_token"] = claims[0]["claim_token"]
        assert client.post("/bridge/sent", json=data, headers=headers).status_code == 200
        assert client.post("/bridge/sent", json=data, headers=headers).status_code == (200 if outcome == "accepted" else 409)
        with SessionLocal() as db:
            assert db.get(Message, message_id).status == ("Sent" if outcome == "accepted" else "Needs Review")
    finally:
        with SessionLocal() as db:
            db.query(Message).filter(Message.id == message_id).delete(synchronize_session=False)
            db.commit()


def test_mac_helper_has_one_send_and_unknown_result(monkeypatch):
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("test_bridge_helper", Path(__file__).resolve().parents[2] / "scripts" / "imessage_bridge.py")
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    scripts = []
    monkeypatch.setattr(helper.subprocess, "run", lambda args, **kwargs: (scripts.append(args[2]) or SimpleNamespace(returncode=1, stderr="unknown")))
    assert helper.send_imessage("+12025550100", "test") is False
    assert scripts[0].count("send theText") == 1
    assert scripts[0].index("send theText") > scripts[0].index("end try")
    responses = []
    monkeypatch.setattr(helper, "send_imessage", lambda *args: False)
    def api(path, data=None):
        if data is None: return [{"id": "m", "to": "+12025550100", "body": "test", "claim_token": "claim"}]
        responses.append(data)
    monkeypatch.setattr(helper, "_api", api)
    helper.drain_outbox()
    assert responses == [{"id": "m", "claim_token": "claim", "outcome": "unknown"}]


@pytest.mark.parametrize("decision, status", [("accepted", "Sent"), ("not_accepted", "Not Sent")])
def test_resolution_updates_message_without_reopening_intent(client, auth_headers, monkeypatch, decision, status):
    from app.models import Message
    from app import outreach
    target = email()
    with SessionLocal() as db:
        m = Message(channel="email", direction="outbound", to_email=target, body="body",
                    from_account="test", status="Needs Review")
        db.add(m); db.commit(); message_id = str(m.id)
    operation = f"message:{message_id}"
    guard.invoke("email", target, "test", operation, [], lambda: (None, "timeout"))
    key = guard.digest(guard.recipient_scope("email", target), "test", operation)
    try:
        result = client.post(f"/messages/delivery-attempts/{key}/resolve", json=resolution(decision), headers=auth_headers)
        assert result.status_code == 200
        monkeypatch.setattr(outreach, "deliver", lambda *a, **k: pytest.fail("resolution retried provider"))
        replay = client.post(f"/messages/{message_id}/send", headers=auth_headers)
        assert replay.status_code == (200 if decision == "accepted" else 409)
        with SessionLocal() as db:
            assert db.get(Message, message_id).status == status
    finally:
        with SessionLocal() as db:
            db.query(Message).filter(Message.id == message_id).delete(synchronize_session=False)
            db.commit()
