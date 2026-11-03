"""Real PostgreSQL competing-worker and crash tests; no live providers."""
import multiprocessing
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4
import pytest
from app import outbound_guard as guard
from app.models import OutboundAttempt, OutboundHold
from .conftest import requires_db

pytestmark = requires_db

@pytest.fixture(autouse=True)
def tables():
    OutboundAttempt.__table__.create(guard.engine, checkfirst=True)
    OutboundHold.__table__.create(guard.engine, checkfirst=True)

@pytest.fixture
def outbox_rows():
    """Remove only this test's messages from the suite's shared database."""
    from app.database import SessionLocal
    from app.models import Message
    ids = []
    yield ids
    with SessionLocal() as db:
        db.query(Message).filter(Message.id.in_(ids)).delete(synchronize_session=False)
        db.commit()

def identity():
    return f"{uuid4()}@test.invalid", str(uuid4())

def test_competing_workers_and_replay():
    recipient, key = identity()
    entered, release = Event(), Event()
    calls = []
    def send():
        calls.append(1)
        entered.set()
        assert release.wait(10)
        return "accepted", None
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(guard.invoke, "email", recipient, "test", key, [], send)
        assert entered.wait(10)
        second = pool.submit(guard.invoke, "email", recipient, "test", key, [], send)
        try:
            assert second.result(timeout=10)[0] is None
        finally:
            release.set()
        assert first.result(timeout=10) == ("accepted", None)
    assert guard.invoke("email", recipient, "test", key, [], send) == ("accepted", None)
    assert calls == [1]

def test_payload_change_is_held():
    recipient, key = identity()
    assert guard.invoke("email", recipient, "test", key, ["a"], lambda: ("id", None))[0]
    assert "payload changed" in guard.invoke("email", recipient, "test", key, ["b"], lambda: pytest.fail("resent"))[1]

def test_unknown_fences_new_operation():
    recipient, key = identity()
    def send(): raise TimeoutError()
    assert "unknown" in guard.invoke("email", recipient, "test", key, [], send)[1]
    assert guard.invoke("email", recipient, "test", "new-intent", [], lambda: pytest.fail("resent"))[0] is None

def test_rejected_retains_operation_but_releases_recipient():
    recipient, key = identity()
    assert "rejected" in guard.invoke("email", recipient, "test", key, [], lambda: (None, guard.RejectedDelivery("reject")))[1]
    assert guard.invoke("email", recipient, "test", key, [], lambda: pytest.fail("resent"))[0] is None
    assert guard.invoke("email", recipient, "test", "new-intent", [], lambda: ("id", None))[0] == "id"

def _crash(recipient, key):
    guard.invoke("email", recipient, "test", key, [], lambda: os._exit(17))

def test_process_crash_keeps_reservation_after_restart():
    recipient, key = identity()
    p = multiprocessing.get_context("spawn").Process(target=_crash, args=(recipient, key))
    p.start()
    p.join(20)
    if p.is_alive():
        p.terminate()
        p.join()
        pytest.fail("worker stuck")
    assert p.exitcode == 17
    assert "pending" in guard.invoke("email", recipient, "test", key, [], lambda: pytest.fail("resent"))[1]
    assert guard.invoke("email", recipient, "test", "tomorrow", [], lambda: pytest.fail("resent"))[0] is None

def test_caller_rollback_cannot_erase_acceptance():
    recipient, key = identity()
    with guard.engine.connect() as caller:
        tx = caller.begin()
        assert guard.invoke("email", recipient, "test", key, [], lambda: ("id", None))[0]
        tx.rollback()
    assert guard.invoke("email", recipient, "test", key, [], lambda: pytest.fail("resent"))[0] == "id"

def test_recording_failure_leaves_pending(monkeypatch):
    recipient, key = identity()
    real = guard.engine
    class BrokenStore:
        calls = 0
        def begin(self):
            self.calls += 1
            if self.calls == 2: raise OSError("result store lost")
            return real.begin()
    monkeypatch.setattr(guard, "engine", BrokenStore())
    assert "could not be recorded" in guard.invoke("email", recipient, "test", key, [], lambda: ("accepted", None))[1]
    monkeypatch.setattr(guard, "engine", real)
    assert guard.invoke("email", recipient, "test", key, [], lambda: pytest.fail("resent"))[0] is None

def test_database_failure_prevents_provider_call(monkeypatch):
    class BrokenStore:
        def begin(self): raise OSError("db unavailable")
    monkeypatch.setattr(guard, "engine", BrokenStore())
    assert "no provider call" in guard.invoke("email", "x", "test", "k", [], lambda: pytest.fail("sent"))[1]

def test_scheduler_slots_exclude_and_release():
    with guard.scheduler_slot() as first:
        assert first
        with guard.scheduler_slot() as second: assert not second
    with pytest.raises(RuntimeError):
        with guard.scheduler_slot() as acquired:
            assert acquired
            raise RuntimeError("job failed")
    with guard.scheduler_slot() as acquired: assert acquired

def test_independent_recipients_can_progress():
    recipients = [identity()[0] for _ in range(8)]
    with ThreadPoolExecutor(8) as pool:
        result = list(pool.map(lambda recipient: guard.invoke("email", recipient, "test", "k", [], lambda: (recipient, None)), recipients))
    assert [r[0] for r in result] == recipients

def test_auto_call_replay_does_not_create_another_call_log():
    recipient, key = identity()
    assert guard.invoke("auto-call", recipient, "voice", key, [], lambda: ("sid", None), replay_accepted=False)[0] == "sid"
    assert guard.invoke("auto-call", recipient, "voice", key, [], lambda: pytest.fail("called twice"), replay_accepted=False)[0] is None

def test_delivery_adapter_competing_message_intent(monkeypatch):
    from app import outreach
    recipient = f"{uuid4()}@realmail.co"
    entered, release = Event(), Event()
    calls = []
    def send(*args):
        calls.append(args)
        entered.set()
        assert release.wait(10)
        return "receipt", None
    monkeypatch.setattr(outreach, "can_deliver", lambda *_: True)
    monkeypatch.setattr(outreach, "_deliver_once", send)
    def deliver():
        return outreach.deliver(recipient, "subject", "body", operation_key="message:stable")
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(deliver)
        assert entered.wait(10)
        try:
            assert pool.submit(deliver).result(timeout=10)[0] is None
        finally:
            release.set()
        assert first.result(timeout=10) == ("receipt", None)
    assert deliver() == ("receipt", None)
    assert len(calls) == 1


def test_outbox_unknown_is_visible_and_never_retried(client, auth_headers, monkeypatch, outbox_rows):
    from app import outreach
    from app.database import SessionLocal
    from app.models import Message
    recipient = f"{uuid4()}@realmail.co"
    with SessionLocal() as db:
        msg = Message(channel="email", direction="outbound", to_email=recipient,
                      from_account="insurance", subject="subject", body="body", status="Drafted")
        db.add(msg)
        db.commit()
        message_id = str(msg.id)
        outbox_rows.append(message_id)
    calls = []
    monkeypatch.setattr(outreach, "can_deliver", lambda *_: True)
    monkeypatch.setattr(outreach, "_deliver_once", lambda *args: (calls.append(1) or (None, "timeout")))
    for _ in range(2):
        result = client.post(f"/messages/{message_id}/send", headers=auth_headers)
        assert result.status_code == 409
        assert "unknown" in result.json()["detail"]
    assert calls == [1]
    with SessionLocal() as db:
        assert db.get(Message, message_id).status == "Needs Review"
    assert client.get("/messages/delivery-attempts").status_code == 401
    queue = client.get("/messages/delivery-attempts", headers=auth_headers)
    assert queue.status_code == 200
    key = guard.digest(guard.digest("email", recipient, "insurance"), f"message:{message_id}")
    attempt = next(a for a in queue.json() if a["key"] == key)
    assert attempt["state"] == "unknown"
    assert set(attempt) == {"key", "channel", "state", "created_at", "updated_at"}


@pytest.mark.parametrize("bulk", [False, True])
def test_outbox_workers_preserve_sent_state(monkeypatch, client, bulk, outbox_rows):
    from app import outreach
    from app.database import SessionLocal
    from app.models import Message
    from app.routers.messages import send_message
    account = str(uuid4())
    with SessionLocal() as db:
        msg = Message(channel="email", direction="outbound", to_email=f"{uuid4()}@realmail.co",
                      from_account=account, subject="subject", body="body", status="Drafted")
        db.add(msg)
        db.commit()
        message_id = str(msg.id)
        outbox_rows.append(message_id)
    entered, release = Event(), Event()
    calls = []
    def send(*args):
        calls.append(1)
        entered.set()
        assert release.wait(10)
        return "receipt", None
    monkeypatch.setattr(outreach, "can_deliver", lambda *_: True)
    monkeypatch.setattr(outreach, "daily_send_cap", lambda: 100)
    monkeypatch.setattr(outreach, "_email_sent_today", lambda *_: 0)
    monkeypatch.setattr(outreach, "_deliver_once", send)
    def worker():
        with SessionLocal() as db:
            if bulk:
                return outreach.send_email_drafts(db, limit=1, account=account)
            return send_message(message_id, db, None).status
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(worker)
        assert entered.wait(10)
        second = pool.submit(worker)
        try:
            if bulk:
                assert second.result(timeout=10)["considered"] == 0
        finally:
            release.set()
        assert first.result(timeout=10)
        assert second.result(timeout=10)
    assert calls == [1]
    with SessionLocal() as db:
        assert db.get(Message, message_id).status == "Sent"
