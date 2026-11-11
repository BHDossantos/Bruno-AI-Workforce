"""Actual PostgreSQL serialization; all provider callbacks are test doubles."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4
from datetime import datetime, timezone
import pytest
from sqlalchemy.orm import Session
from app import outbound_guard as guard, suppression_boundary
from app.database import Base
from app.models import DoNotContact, Message
from .conftest import requires_db
pytestmark = requires_db

@pytest.fixture(autouse=True)
def tables(monkeypatch):
    Base.metadata.create_all(guard.engine)
    monkeypatch.setattr(guard, "quota_limit", lambda _: None)

@pytest.mark.parametrize('channel', ['email','campaign','sms','whatsapp','call','auto-call'])
def test_every_boundary_suppression_means_zero_provider_calls(channel):
    email = channel in ('email', 'campaign')
    recipient = f'{uuid4()}@realbiz.co' if email else '+1603' + str(uuid4().int % 10000000).zfill(7)
    kind, value = suppression_boundary.identity(channel, recipient)
    with Session(guard.engine) as db:
        db.add(DoNotContact(kind=kind, value=value)); db.commit()
    calls = []
    result = guard.invoke(channel, recipient, 'test', uuid4().hex, [], lambda: (calls.append(1) or ('receipt', None)))
    assert result.provider_id is None and not calls
    assert result.error.code == 'do_not_contact'


def test_bounce_after_draft_blocks_provider():
    recipient = f'{uuid4()}@realbiz.co'
    with Session(guard.engine) as db:
        db.add(Message(channel='email', direction='outbound', to_email=recipient,
                       status='Sent', sent_at=datetime.now(timezone.utc), delivery_status='bounced'))
        db.commit()
    result = guard.invoke('email', recipient, 'test', uuid4().hex, [], lambda: pytest.fail('provider called'))
    assert result.error.code == 'bounce_or_suppression'


def test_optout_transaction_wins_race_before_handoff(monkeypatch):
    recipient = f'{uuid4()}@realbiz.co'
    ready, release, at_boundary = Event(), Event(), Event()
    from contextlib import contextmanager
    real_boundary = suppression_boundary.boundary
    @contextmanager
    def observed_boundary(*args):
        at_boundary.set()
        with real_boundary(*args) as reason:
            yield reason
    monkeypatch.setattr(suppression_boundary, 'boundary', observed_boundary)
    def optout():
        with Session(guard.engine) as db:
            db.add(DoNotContact(kind='email', value=recipient))
            db.flush()  # listener holds the same recipient lock until commit
            ready.set()
            assert release.wait(5)
            db.commit()
    with ThreadPoolExecutor(2) as pool:
        writer = pool.submit(optout)
        assert ready.wait(5)
        sender = pool.submit(guard.invoke, 'email', recipient, 'test', uuid4().hex, [],
                             lambda: pytest.fail('provider called after optout'))
        try:
            assert at_boundary.wait(5)  # reservation succeeded while opt-out was uncommitted
            assert not sender.done()
        finally:
            release.set()
        writer.result(timeout=5)
        assert sender.result(timeout=5).error.code == 'do_not_contact'


def test_suppression_database_failure_is_closed(monkeypatch):
    from contextlib import contextmanager
    @contextmanager
    def unavailable(*args):
        raise OSError('unavailable')
        yield
    monkeypatch.setattr(suppression_boundary, 'boundary', unavailable)
    result = guard.invoke('email', f'{uuid4()}@realbiz.co', 'test', uuid4().hex, [],
                          lambda: pytest.fail('provider called with missing suppression'))
    assert result.provider_id is None
    assert result.error.kind in ('held','uncertain','not_attempted')

@pytest.mark.parametrize('provider_name', ['instantly', 'smartlead'])
def test_direct_campaign_adapter_cannot_bypass_dnc(provider_name, monkeypatch):
    from importlib import import_module
    provider = import_module('app.integrations.' + provider_name)
    recipient = f'{uuid4()}@realbiz.co'
    with Session(guard.engine) as db:
        db.add(DoNotContact(kind='email', value=recipient)); db.commit()
    monkeypatch.setattr(provider, 'is_configured', lambda: True)
    monkeypatch.setattr(provider.httpx, 'post', lambda *a, **kw: pytest.fail('provider called'))
    assert provider.add_lead(recipient) is False


def test_duplicate_webhook_does_not_process_twice(client, monkeypatch):
    from app.config import settings
    from app import inbound
    from app.models import Message
    monkeypatch.setattr(settings, 'resend_webhook_secret', '')
    monkeypatch.setattr(settings, 'environment', 'development')
    recipient = f'{uuid4()}@realbiz.co'
    payload={'type':'inbound.email.received','data':{'id':uuid4().hex, 'from':recipient,
              'to':'business@realbiz.co','subject':'Reply','text':'Please remove me from your list'}}
    monkeypatch.setattr(inbound, '_draft_reply', lambda *a, **kw: pytest.fail('draft/send ran during ingestion'))
    first=client.post('/resend/inbound', json=payload)
    assert first.status_code == 200
    second=client.post('/resend/inbound', json=payload)
    assert second.status_code == 200 and second.json()['duplicate']
    with Session(guard.engine) as db:
        assert db.query(Message).filter(Message.direction=='inbound', Message.to_email==recipient).count() == 1
    payload['data']['text']='changed'
    assert client.post('/resend/inbound', json=payload).status_code == 409


def test_legacy_stop_blocks_call_and_sms_without_dnc_table_entry():
    phone='+1603'+str(uuid4().int % 10000000).zfill(7)
    with Session(guard.engine) as db:
        db.add(Message(channel='sms', direction='inbound', to_email=phone, body='STOP', status='Received'))
        db.commit()
    for channel in ('sms','call'):
        result=guard.invoke(channel, phone, 'test', uuid4().hex, [], lambda: pytest.fail('opted-out provider call'))
        assert result.error.code == 'inbound_opt_out'
