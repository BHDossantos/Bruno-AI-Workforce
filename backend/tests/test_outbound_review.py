"""Independent-review regressions; real PostgreSQL, fake provider boundaries."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from uuid import uuid4
import pytest
from app import outbound_guard as guard, outreach, sms_engine
from app.database import Base, SessionLocal
from app.models import Message, Lead, OutboundAttempt, OutboundHold
from .conftest import requires_db

pytestmark = requires_db

@pytest.fixture(autouse=True)
def tables():
    Base.metadata.create_all(guard.engine)

@pytest.fixture
def owned():
    ids, leads = [], []
    yield ids, leads
    with SessionLocal() as db:
        db.query(Message).filter(Message.id.in_(ids)).delete(synchronize_session=False)
        db.query(Lead).filter(Lead.id.in_(leads)).delete(synchronize_session=False)
        db.commit()

@pytest.fixture
def clock(monkeypatch):
    class Clock(datetime):
        current = datetime(2200 + uuid4().int % 5000, 1, 1, tzinfo=timezone.utc)
        @classmethod
        def now(cls, tz=None): return cls.current
    monkeypatch.setattr(guard, "datetime", Clock)
    return Clock


def target(channel):
    return f"{uuid4()}@realmail.co" if channel == "email" else "+1202" + str(uuid4().int % 10000000).zfill(7)


def batch_setup(monkeypatch, channel, calls):
    from app.integrations import sms, telco
    monkeypatch.setattr(outreach, "can_deliver", lambda *_: True)
    monkeypatch.setattr(outreach, "_email_sent_today", lambda *_: 0)
    monkeypatch.setattr(outreach, "daily_send_cap", lambda: 100)
    monkeypatch.setattr(outreach, "_deliver_once", lambda *a: (calls.append(1) or ("receipt", None)))
    monkeypatch.setattr(sms_engine, "_refresh_config", lambda *_: None)
    monkeypatch.setattr(sms_engine, "sms_block_reason", lambda *a, **k: None)
    monkeypatch.setattr(sms, "is_configured", lambda: True)
    monkeypatch.setattr(sms, "_use_plivo", lambda: False)
    monkeypatch.setattr(telco, "sms_providers", lambda: ["fake"])
    monkeypatch.setattr(sms, "_send_once", lambda *a: (calls.append(1) or ("receipt", None)))
    def batch(account):
        with SessionLocal() as db:
            fn = outreach.send_email_drafts if channel == "email" else sms_engine.send_sms_drafts
            return fn(db, limit=1, account=account)
    return batch


def draft(channel, account, status, owned):
    with SessionLocal() as db:
        m = Message(channel=channel, direction="outbound", to_email=target(channel),
                    from_account=account, subject="subject", body="body", status=status)
        db.add(m); db.commit(); owned[0].append(m.id)
        return m.id


@pytest.mark.parametrize("channel,status", [("email", "Drafted"), ("email", "Approved"), ("sms", "Drafted")])
def test_quota_loser_remains_retryable_next_day(monkeypatch, owned, clock, channel, status):
    calls = []
    batch = batch_setup(monkeypatch, channel, calls)
    monkeypatch.setattr(guard, "quota_limit", lambda _: 1)
    accounts = [str(uuid4()), str(uuid4())]
    ids = [draft(channel, account, status, owned) for account in accounts]
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(batch, accounts))
    assert sum(r["sent"] for r in results) == len(calls) == 1
    with SessionLocal() as db:
        states = [db.get(Message, mid).status for mid in ids]
        assert sorted(states) == sorted([status, "Sent"])
        loser = ids[states.index(status)]
        assert not db.query(OutboundAttempt).filter(OutboundAttempt.operation_ref == f"message:{loser}").first()
    denied = next(r for r in results if not r["sent"])
    error = (denied.get("errors") or denied.get("reasons"))[0]
    assert error.kind == "not_attempted" and error.code == "quota_exhausted"
    clock.current += timedelta(days=1)
    assert batch(accounts[states.index(status)])["sent"] == 1
    assert len(calls) == 2


@pytest.mark.parametrize("channel", ["email", "sms"])
def test_transient_reservation_failure_preserves_draft(monkeypatch, owned, clock, channel):
    calls, account = [], str(uuid4())
    batch = batch_setup(monkeypatch, channel, calls)
    mid = draft(channel, account, "Drafted", owned)
    engine = guard.engine
    class Unavailable:
        def begin(self): raise OSError("temporary reservation outage")
    monkeypatch.setattr(guard, "engine", Unavailable())
    result = batch(account)
    assert result["sent"] == 0 and calls == []
    error = (result.get("errors") or result.get("reasons"))[0]
    assert error.code == "reservation_unavailable" and guard.retryable_without_reconciliation(error)
    monkeypatch.setattr(guard, "engine", engine)
    with SessionLocal() as db:
        assert db.get(Message, mid).status == "Drafted"
        assert not db.query(OutboundAttempt).filter(OutboundAttempt.operation_ref == f"message:{mid}").first()
    assert batch(account)["sent"] == 1 and calls == [1]
    assert not guard.retryable_without_reconciliation("no provider call made")


@pytest.mark.parametrize("name", ["sms", "plivo", "whatsapp_cloud", "whatsapp_dispatch"])
@pytest.mark.parametrize("body", ["", "   "])
def test_empty_then_corrected_text_never_fences_recipient(monkeypatch, name, body):
    from app.integrations import sms, plivo, whatsapp_cloud, telco
    calls = []
    for module in (sms, plivo, whatsapp_cloud): monkeypatch.setattr(module, "is_configured", lambda: True)
    monkeypatch.setattr(sms, "_use_plivo", lambda: False)
    monkeypatch.setattr(telco, "sms_providers", lambda: ["fake"])
    monkeypatch.setattr(sms, "_send_once", lambda *a: (calls.append(1) or ("receipt", None)))
    response = SimpleNamespace(status_code=200, json=lambda: {"message_uuid": ["receipt"], "messages": [{"id": "receipt"}]})
    monkeypatch.setattr(plivo.httpx, "post", lambda *a, **k: (calls.append(1) or response))
    fn = {"sms": sms.send_with_error, "plivo": plivo.send_with_error,
          "whatsapp_cloud": whatsapp_cloud.send, "whatsapp_dispatch": sms.send_whatsapp}[name]
    phone = target("sms")
    fn(phone, body)
    scope = guard.recipient_scope("sms", phone)
    with SessionLocal() as db:
        assert db.query(OutboundAttempt).filter(OutboundAttempt.scope == scope).count() == 0
        assert db.get(OutboundHold, scope) is None
    assert calls == []
    value = fn(phone, "corrected")
    assert (value[0] if isinstance(value, tuple) else value) == "receipt"
    assert calls == [1]


@pytest.mark.parametrize("fn_name", ["send_with_error", "send_message"])
def test_gmail_backup_resolved_before_guard(monkeypatch, fn_name):
    from app.integrations import gmail
    seen = []
    class Service:
        def users(self): return self
        def messages(self): return self
        def send(self, **kw): return self
        def execute(self): return {"id": "receipt"}
    monkeypatch.setattr(gmail, "is_configured", lambda account=gmail.PERSONAL: account == gmail.INSURANCE_BACKUP)
    monkeypatch.setattr(gmail, "_service", lambda account: (seen.append(account) or Service()))
    monkeypatch.setattr(gmail, "_raw", lambda *a: {})
    to = target("email")
    value = getattr(gmail, fn_name)(to, "subject", "body", account="insurance")
    assert (value[0] if isinstance(value, tuple) else value) == "receipt"
    assert seen == [gmail.INSURANCE_BACKUP]
    with SessionLocal() as db:
        row = db.query(OutboundAttempt).filter(OutboundAttempt.scope == guard.recipient_scope("email", to)).one()
        assert row.account == gmail.INSURANCE_BACKUP


@pytest.mark.parametrize("name", ["twilio_voice", "plivo_voice", "vonage_voice"])
@pytest.mark.parametrize("method", ["place_auto_call", "place_bridge_call"])
def test_voice_config_denial_before_reservation(monkeypatch, name, method):
    import importlib
    from app.config import settings
    module = importlib.import_module("app.integrations." + name)
    calls = []
    monkeypatch.setattr(module, "is_configured", lambda: True)
    monkeypatch.setattr(settings, "public_base_url", "")
    monkeypatch.setattr(settings, "producer_callback", "+12025550100")
    response = SimpleNamespace(status_code=201, json=lambda: {"sid": "receipt", "request_uuid": "receipt", "uuid": "receipt"})
    monkeypatch.setattr(module.httpx, "post", lambda *a, **k: (calls.append(1) or response))
    if name == "vonage_voice": monkeypatch.setattr(module, "_jwt", lambda: "test-only")
    phone = target("sms")
    value = getattr(module, method)(phone, "lead")
    assert value.outcome == "not_attempted" and value.error.code == "configuration"
    with SessionLocal() as db:
        assert db.get(OutboundHold, guard.recipient_scope("call", phone)) is None
    assert calls == []
    monkeypatch.setattr(settings, "public_base_url", "https://callback.test")
    assert getattr(module, method)(phone, "lead")[0] == "receipt"
    assert calls == [1]


@pytest.mark.parametrize("name", ["plivo_voice", "vonage_voice"])
@pytest.mark.parametrize("invalid", ["malformed", "empty", "whitespace"])
def test_voice_missing_receipt_retains_hold(monkeypatch, name, invalid):
    import importlib
    from app.config import settings
    module = importlib.import_module("app.integrations." + name)
    monkeypatch.setattr(module, "is_configured", lambda: True)
    monkeypatch.setattr(settings, "public_base_url", "https://callback.test")
    if name == "vonage_voice": monkeypatch.setattr(module, "_jwt", lambda: "test-only")
    calls = []
    def json():
        if invalid == "malformed": raise ValueError("bad JSON")
        return {"uuid": "   ", "request_uuid": "   "} if invalid == "whitespace" else {}
    response = SimpleNamespace(status_code=201, json=json)
    monkeypatch.setattr(module.httpx, "post", lambda *a, **k: (calls.append(1) or response))
    phone = target("sms")
    result = module.place_auto_call(phone, "lead")
    assert result.outcome == "uncertain"
    assert module.place_auto_call(phone, "different-lead")[0] is None
    assert calls == [1]
    with SessionLocal() as db:
        assert db.get(OutboundHold, guard.recipient_scope("call", phone)) is not None


@pytest.mark.parametrize("explicit", [False, True])
def test_retried_sms_enqueue_only_one_bridge_delivery(client, auth_headers, monkeypatch, owned, explicit):
    from app.config import settings
    from app import runtime_config
    from app.integrations import sms
    monkeypatch.setattr(runtime_config, "apply_to_settings", lambda *_: None)
    monkeypatch.setattr(sms, "is_configured", lambda: False)
    monkeypatch.setattr(sms_engine, "sms_block_reason", lambda *a, **k: None)
    monkeypatch.setattr(settings, "bridge_token", "review-bridge-only")
    headers = {"X-Bridge-Token": "review-bridge-only"}
    payload = {"to": target("sms"), "message": "one intended message", "account": "insurance"}
    if explicit: payload["idempotency_key"] = str(uuid4())
    with ThreadPoolExecutor(2) as pool:
        responses = list(pool.map(lambda _: client.post("/sms/send", json=payload, headers=auth_headers), range(2)))
    assert all(r.status_code == 200 for r in responses)
    ids = {r.json()["message_id"] for r in responses}
    assert len(ids) == 1
    owned[0].extend(ids)
    claim = next(item for item in client.get("/bridge/outbox", headers=headers).json() if item["id"] in ids)
    ack = {"id": claim["id"], "claim_token": claim["claim_token"]}
    assert client.post("/bridge/sent", json=ack, headers=headers).status_code == 200
    assert client.post("/sms/send", json=payload, headers=auth_headers).json()["status"] == "Sent"
    assert not any(item["id"] in ids for item in client.get("/bridge/outbox", headers=headers).json())
    # Explicit new intent supports a legitimate identical second message.
    distinct = {**payload, "idempotency_key": str(uuid4())}
    new = client.post("/sms/send", json=distinct, headers=auth_headers).json()
    assert new["message_id"] not in ids
    owned[0].append(new["message_id"])
    claim2 = next(item for item in client.get("/bridge/outbox", headers=headers).json() if item["id"] == new["message_id"])
    assert client.post("/bridge/sent", json={"id": claim2["id"], "claim_token": claim2["claim_token"]}, headers=headers).status_code == 200
    conflict = {**distinct, "message": "changed payload"}
    assert client.post("/sms/send", json=conflict, headers=auth_headers).status_code == 409


@pytest.mark.parametrize("body", ["", "   "])
def test_empty_sms_api_does_not_enqueue(client, auth_headers, body):
    phone = target("sms")
    response = client.post("/sms/send", json={"to": phone, "message": body}, headers=auth_headers)
    assert response.status_code == 422
    with SessionLocal() as db:
        assert not db.query(Message).filter(Message.to_email == phone).first()
        assert db.get(OutboundHold, guard.recipient_scope("sms", phone)) is None


def accepted_evidence():
    return {"decision": "accepted", "expected_state": "unknown", "evidence": "Provider support confirmed the original request was accepted.",
            "provider_reference": "case-review-confirmed", "provider_id": "verified-receipt"}


def test_manual_sms_reconciliation_updates_original_intent(client, auth_headers, monkeypatch, owned):
    from app import runtime_config
    from app.integrations import sms, telco
    calls = []
    monkeypatch.setattr(runtime_config, "apply_to_settings", lambda *_: None)
    monkeypatch.setattr(sms, "is_configured", lambda: True)
    monkeypatch.setattr(sms, "_use_plivo", lambda: False)
    monkeypatch.setattr(telco, "sms_providers", lambda: ["fake"])
    monkeypatch.setattr(sms, "_send_once", lambda *a: (calls.append(1) or (None, "timeout")))
    payload = {"to": target("sms"), "message": "original text", "account": "insurance", "idempotency_key": str(uuid4())}
    response = client.post("/sms/send", json=payload, headers=auth_headers).json()
    mid = response["message_id"]; owned[0].append(mid)
    assert response["status"] == "Needs Review"
    with SessionLocal() as db:
        attempt = db.query(OutboundAttempt).filter(OutboundAttempt.operation_ref == f"message:{mid}").one()
        key = attempt.key
    assert client.post(f"/messages/delivery-attempts/{key}/resolve", json=accepted_evidence(), headers=auth_headers).status_code == 200
    replay = client.post("/sms/send", json=payload, headers=auth_headers).json()
    assert replay["message_id"] == mid and replay["status"] == "Sent"
    assert calls == [1]


@pytest.mark.parametrize("campaign", [False, True])
def test_stable_first_touch_reconciliation_prevents_next_day_resend(client, auth_headers, monkeypatch, owned, clock, campaign):
    from app import control, runtime_config, bulk_outreach
    from app.integrations import sender, resend, sendgrid, gmail
    from app.config import settings
    segment = str(uuid4())
    with SessionLocal() as db:
        lead = Lead(segment=segment, owner_name="Review lead", email=target("email"),
                    cold_email="Original first touch", status="New")
        db.add(lead); db.commit(); lid, to = lead.id, lead.email; owned[1].append(lid)
    configured = {"campaign": campaign}
    calls = {"email": 0, "campaign": 0}
    monkeypatch.setattr(runtime_config, "apply_to_settings", lambda *_: None)
    monkeypatch.setattr(control, "is_paused_safe", lambda *_: False)
    monkeypatch.setattr(control, "get_mode", lambda *_: "auto")
    monkeypatch.setattr(control, "outreach_autopilot", lambda *_: True)
    monkeypatch.setattr(sender, "is_configured", lambda: configured["campaign"])
    monkeypatch.setattr(sender, "name", lambda: "fake-campaign")
    monkeypatch.setattr(resend, "is_configured", lambda: True)
    monkeypatch.setattr(sendgrid, "is_configured", lambda: False)
    monkeypatch.setattr(gmail, "is_configured", lambda *_: False)
    monkeypatch.setattr(outreach, "effective_cap", lambda *a: 1000)
    monkeypatch.setattr(outreach, "sent_today_count", lambda *a: 0)
    monkeypatch.setattr(settings, "gmail_outbound_mode", "send")
    def enroll(**kwargs): calls["campaign"] += 1; return False
    def email_send(*args): calls["email"] += 1; return None, "timeout"
    monkeypatch.setattr(sender, "add_lead", enroll)
    monkeypatch.setattr(outreach, "_deliver_once", email_send)
    def dispatch():
        with SessionLocal() as db:
            msg = outreach.dispatch_email(db, entity_type="lead", entity_id=lid, to_email=to,
                                         subject="subject", body="Original first touch", account="insurance", autonomous=False)
            db.commit()
            return str(msg.id), msg.status
    mid, status = dispatch(); owned[0].append(mid)
    assert status == "Needs Review"
    # Even a manual email retry cannot bypass unresolved campaign enrollment.
    assert client.post(f"/messages/{mid}/send", headers=auth_headers).status_code == 409
    configured["campaign"] = False
    clock.current += timedelta(days=1)
    monkeypatch.setattr(outreach, "_day_start", lambda: clock.current)
    assert dispatch() == (mid, "Needs Review")
    with SessionLocal() as db:
        key = db.query(OutboundAttempt).filter(OutboundAttempt.operation_ref == f"message:{mid}").one().key
    assert client.post(f"/messages/delivery-attempts/{key}/resolve", json=accepted_evidence(), headers=auth_headers).status_code == 200
    clock.current += timedelta(days=1)
    assert dispatch() == (mid, "Sent")
    with SessionLocal() as db:
        lead = db.get(Lead, lid)
        assert lead.status == "Sent" and lead.times_contacted == 1
        assert bulk_outreach.dispatch_leads(db, segment=segment, autonomous=False)["pending"] == 0
    assert calls == {"email": 0 if campaign else 1, "campaign": 1 if campaign else 0}


def test_lost_reservation_commit_ack_never_bypasses_pending(monkeypatch):
    engine, to, operation = guard.engine, target("email"), str(uuid4())
    class CommitAckLost:
        def begin(self):
            inner = engine.begin()
            class Transaction:
                def __enter__(self): return inner.__enter__()
                def __exit__(self, typ, value, tb):
                    result = inner.__exit__(typ, value, tb)
                    if typ is None: raise OSError("commit acknowledgement lost")
                    return result
            return Transaction()
    monkeypatch.setattr(guard, "engine", CommitAckLost())
    denied = guard.invoke("email", to, "test", operation, [], lambda: pytest.fail("called before commit ack"))
    assert denied.outcome == "not_attempted"
    monkeypatch.setattr(guard, "engine", engine)
    retried = guard.invoke("email", to, "test", operation, [], lambda: pytest.fail("pending action bypassed"))
    assert retried.outcome == "held" and retried.error.code == "pending"
    with SessionLocal() as db:
        assert db.get(OutboundHold, guard.recipient_scope("email", to)) is not None


def test_dispatch_acceptance_survives_caller_rollback(monkeypatch, owned, clock):
    from app import control, runtime_config
    from app.integrations import sender, resend, gmail
    from app.config import settings
    monkeypatch.setattr(runtime_config, "apply_to_settings", lambda *_: None)
    monkeypatch.setattr(control, "is_paused_safe", lambda *_: False)
    monkeypatch.setattr(sender, "is_configured", lambda: False)
    monkeypatch.setattr(resend, "is_configured", lambda: True)
    monkeypatch.setattr(gmail, "is_configured", lambda *_: False)
    monkeypatch.setattr(outreach, "effective_cap", lambda *a: 100)
    monkeypatch.setattr(outreach, "sent_today_count", lambda *a: 0)
    monkeypatch.setattr(settings, "gmail_outbound_mode", "send")
    calls = []
    monkeypatch.setattr(outreach, "_deliver_once", lambda *a: (calls.append(1) or ("receipt", None)))
    args = dict(entity_type="reply", entity_id=None, to_email=target("email"),
                subject="subject", body="body", account="insurance", autonomous=False)
    with SessionLocal() as db:
        msg = outreach.dispatch_email(db, **args)
        mid = msg.id; owned[0].append(mid)
        assert msg.status == "Sent"
        db.rollback()
    with SessionLocal() as db:
        assert db.get(Message, mid).status == "Drafted"  # durable intent survives its caller
        msg = outreach.dispatch_email(db, **args)
        assert msg.id == mid and msg.status == "Sent"
        db.commit()
    assert calls == [1]


def test_brief_followup_and_review_are_distinct_stable_intents(monkeypatch, owned, clock):
    from app import actions, control, runtime_config
    from app.agents.review_referral import ReviewReferralAgent
    from app.integrations import sender, resend, gmail
    from app.config import settings
    from app.models import ActionLog
    monkeypatch.setattr(runtime_config, "apply_to_settings", lambda *_: None)
    monkeypatch.setattr(control, "is_paused_safe", lambda *_: False)
    monkeypatch.setattr(control, "get_mode", lambda *_: "auto")
    monkeypatch.setattr(sender, "is_configured", lambda: False)
    monkeypatch.setattr(resend, "is_configured", lambda: True)
    monkeypatch.setattr(gmail, "is_configured", lambda *_: False)
    monkeypatch.setattr(outreach, "effective_cap", lambda *a: 100)
    monkeypatch.setattr(outreach, "sent_today_count", lambda *a: 0)
    monkeypatch.setattr(settings, "gmail_outbound_mode", "send")
    # Simulate distinct business days without changing the shared daily safety gate.
    monkeypatch.setattr(outreach, "_day_start", lambda: clock.current)
    monkeypatch.setattr(actions.skills, "system_prompt", lambda *_: "test")
    monkeypatch.setattr(actions.memory, "entity_context", lambda *a, **k: "")
    copy = iter(range(20))
    monkeypatch.setattr(actions.client, "complete_json", lambda *a, **k:
                        {"subject": "subject", "body": f"Generated copy {next(copy)}"})
    calls = []
    monkeypatch.setattr(outreach, "_deliver_once", lambda *a: (calls.append(a) or (f"receipt-{len(calls)}", None)))
    with SessionLocal() as db:
        lead = Lead(segment="intent-test", email=target("email"), company_name="Intent test", status="New")
        db.add(lead); db.commit(); owned[1].append(lead.id)
        initial = outreach.dispatch_email(db, entity_type="lead", entity_id=lead.id,
                    to_email=lead.email, subject="Initial", body="First touch", account="insurance")
        db.commit()
        assert initial.status == "Sent"
        clock.current += timedelta(days=1)
        assert actions._send_followup(db, "lead", lead, "insurance")["status"] == "Sent"
        assert actions._send_followup(db, "lead", lead, "insurance")["status"] == "Sent"
        assert len(calls) == 2
        lead.status = "Closed Won"; db.commit()
        clock.current += timedelta(days=1)
        agent = ReviewReferralAgent(db)
        assert agent.execute()["asked"] == 1
        assert len(calls) == 3
        # Lose the ancillary action log: durable purpose identity must still dedupe.
        db.query(ActionLog).filter(ActionLog.entity_id == str(lead.id),
                                  ActionLog.action == "review_requested").delete()
        lead.status = "Closed Won"; db.commit()
        agent.execute()
        assert len(calls) == 3
        messages = db.query(Message).filter(Message.entity_id == lead.id).all()
        owned[0].extend(m.id for m in messages)
        assert len(messages) == 3 and all(m.status == "Sent" for m in messages)
        db.query(ActionLog).filter(ActionLog.entity_id == str(lead.id)).delete()
        db.commit()


def test_first_touch_duplicate_entities_before_caller_commit(monkeypatch, owned, clock):
    from app import actions, control, runtime_config
    from app.agents.review_referral import ReviewReferralAgent
    from app.integrations import sender, resend, gmail
    from app.config import settings
    from app.models import ActionLog
    monkeypatch.setattr(runtime_config, "apply_to_settings", lambda *_: None)
    monkeypatch.setattr(control, "is_paused_safe", lambda *_: False)
    monkeypatch.setattr(control, "get_mode", lambda *_: "auto")
    monkeypatch.setattr(sender, "is_configured", lambda: False)
    monkeypatch.setattr(resend, "is_configured", lambda: True)
    monkeypatch.setattr(gmail, "is_configured", lambda *_: False)
    monkeypatch.setattr(outreach, "effective_cap", lambda *a: 100)
    monkeypatch.setattr(outreach, "sent_today_count", lambda *a: 0)
    monkeypatch.setattr(settings, "gmail_outbound_mode", "send")
    # Simulate distinct business days without changing the shared daily safety gate.
    monkeypatch.setattr(outreach, "_day_start", lambda: clock.current)
    monkeypatch.setattr(actions.skills, "system_prompt", lambda *_: "test")
    monkeypatch.setattr(actions.memory, "entity_context", lambda *a, **k: "")
    copy = iter(range(20))
    monkeypatch.setattr(actions.client, "complete_json", lambda *a, **k:
                        {"subject": "subject", "body": f"Generated copy {next(copy)}"})
    calls = []
    monkeypatch.setattr(outreach, "_deliver_once", lambda *a: (calls.append(a) or (f"receipt-{len(calls)}", None)))
    to = target("email")
    with SessionLocal() as db:
        rows = [Lead(segment="intent-test", email=to, company_name="Duplicate", status="New") for _ in range(2)]
        db.add_all(rows); db.commit()
        ids = [r.id for r in rows]; owned[1].extend(ids)
    with SessionLocal() as first, SessionLocal() as second:
        a = outreach.dispatch_email(first, entity_type="lead", entity_id=ids[0],
                to_email=to, subject="Initial A", body="First body", account="insurance")
        assert a.status == "Sent"
        # A's Message is still only Drafted to other sessions, and its recipient
        # hold has been released after acceptance. B has a different entity/intent.
        assert second.get(Message, a.id).status == "Drafted"
        b = outreach.dispatch_email(second, entity_type="lead", entity_id=ids[1],
                to_email=to.upper(), subject="Initial B", body="Other body", account="insurance")
        assert b.status == "Drafted"
        assert len(calls) == 1
        owned[0].extend([a.id, b.id])
        second.commit(); first.commit()


@pytest.mark.parametrize("caller", ["profile", "automation"])
def test_lead_sms_intent_survives_bridge_ack(client, auth_headers, monkeypatch, owned, caller):
    from app.config import settings
    from app import runtime_config
    from app.integrations import sms
    monkeypatch.setattr(runtime_config, "apply_to_settings", lambda *_: None)
    monkeypatch.setattr(sms, "is_configured", lambda: False)
    monkeypatch.setattr(sms_engine, "sms_block_reason", lambda *a, **k: None)
    monkeypatch.setattr(settings, "bridge_token", "review-bridge-only")
    headers = {"X-Bridge-Token": "review-bridge-only"}
    with SessionLocal() as db:
        lead = Lead(segment="intent-test", phone=target("sms"), company_name="Bridge intent")
        db.add(lead); db.commit(); lid, phone = lead.id, lead.phone; owned[1].append(lid)
    def send(intent):
        if caller == "profile":
            result = client.post(f"/leads/{lid}/send-text", json={"message": "same text", "idempotency_key": intent}, headers=auth_headers)
            assert result.status_code == 200, result.text
        else:
            with SessionLocal() as db:
                assert sms_engine.send_text(db, entity_type="lead", entity_id=lid, phone=phone,
                    body="same text", intent_key=intent)
    first, distinct = str(uuid4()), str(uuid4())
    with ThreadPoolExecutor(2) as pool:
        list(pool.map(send, [first, first]))
    with SessionLocal() as db:
        rows = db.query(Message).filter(Message.entity_id == lid).all()
        assert len(rows) == 1
        mid = str(rows[0].id); owned[0].append(mid)
    claim = next(x for x in client.get("/bridge/outbox", headers=headers).json() if x["id"] == mid)
    assert client.post("/bridge/sent", json={"id": mid, "claim_token": claim["claim_token"]}, headers=headers).status_code == 200
    send(first)
    assert not any(x["id"] == mid for x in client.get("/bridge/outbox", headers=headers).json())
    send(distinct)
    with SessionLocal() as db:
        rows = db.query(Message).filter(Message.entity_id == lid).all()
        assert len(rows) == 2
        second = next(str(m.id) for m in rows if str(m.id) != mid); owned[0].append(second)
    claim = next(x for x in client.get("/bridge/outbox", headers=headers).json() if x["id"] == second)
    assert client.post("/bridge/sent", json={"id": second, "claim_token": claim["claim_token"]}, headers=headers).status_code == 200
    send(distinct)
    assert not any(x["id"] in (mid, second) for x in client.get("/bridge/outbox", headers=headers).json())


def test_vonage_local_signing_failure_has_no_hold(monkeypatch):
    from app.integrations import vonage_voice
    from app.config import settings
    phone = target("sms")
    monkeypatch.setattr(vonage_voice, "is_configured", lambda: True)
    monkeypatch.setattr(settings, "public_base_url", "https://callback.invalid")
    monkeypatch.setattr(settings, "vonage_application_id", "test-app")
    monkeypatch.setattr(settings, "vonage_private_key", "invalid-test-key")
    monkeypatch.setattr(vonage_voice.httpx, "post", lambda *a, **k: pytest.fail("HTTP called with invalid signing config"))
    result = vonage_voice.place_auto_call(phone, "test-lead")
    assert result.outcome == "not_attempted" and result.error.code == "configuration"
    with SessionLocal() as db:
        assert db.get(OutboundHold, guard.recipient_scope("call", phone)) is None
        assert not db.query(OutboundAttempt).filter(OutboundAttempt.scope == guard.recipient_scope("call", phone)).first()
