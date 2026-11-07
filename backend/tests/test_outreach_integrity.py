"""No provider calls: pagination, durable ingestion, eligibility and honest windows."""
import base64
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import pytest
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB
from app.models import Message, Lead, Restaurant, Contact, DoNotContact, ActionLog, MailboxSyncHealth, FollowUp
from app import inbound, followups, outreach_performance, suppression_boundary
from app.integrations import gmail

@compiles(JSONB, 'sqlite')
def json_sqlite(element, compiler, **kw): return 'JSON'

@pytest.fixture
def db():
    engine = create_engine('sqlite://')
    for model in (Message, Lead, Restaurant, Contact, DoNotContact, ActionLog, MailboxSyncHealth, FollowUp):
        model.__table__.create(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def record(**kwargs):
    return dict(mailbox='owner@real.test', message_id='one', received_at=datetime.now(timezone.utc),
                from_email='prospect@real.test', subject='Re: insurance', snippet='Please unsubscribe', **kwargs)


def test_paginated_fetch_duplicate_ids_actual_dates_and_health():
    now = datetime.now(timezone.utc)
    raw = base64.urlsafe_b64encode(b'From: Prospect <prospect@real.test>\r\nSubject: Hello\r\n\r\nHello').decode()
    svc = MagicMock()
    svc.users().getProfile().execute.return_value = {'emailAddress':'owner@real.test'}
    svc.users().messages().list().execute.side_effect = [
        {'messages':[{'id':'1'}], 'nextPageToken':'page2'}, {'messages':[{'id':'1'},{'id':'2'}]}]
    svc.users().messages().get().execute.side_effect = [
        {'id':'1','internalDate':str(int(now.timestamp()*1000)-1000),'raw':raw},
        {'id':'2','internalDate':str(int((now-timedelta(days=9)).timestamp()*1000)),'raw':raw}]
    with patch.object(gmail, '_service', return_value=svc):
        batch = gmail.list_replies()
    assert batch.status == 'complete' and len(batch) == 1
    assert svc.users().messages().get().execute.call_count == 2
    queries = svc.users().messages().list.call_args_list
    assert any(c.kwargs.get('pageToken') == 'page2' for c in queries)
    assert all('in:inbox' not in c.kwargs.get('q','') for c in queries)


def test_fetch_failure_is_not_healthy_zero():
    with patch.object(gmail, '_service', side_effect=TimeoutError):
        batch = gmail.list_replies()
    assert batch.status == 'failed' and batch.error_code == 'fetch_failed'


def test_duplicate_ingestion_and_optout_never_send(db):
    item = record()
    batch = gmail.InboundBatch([item], through=item['received_at'])
    with patch.object(inbound, 'ACCOUNTS', ['personal']), patch('app.runtime_config.apply_to_settings'), \
         patch.object(gmail, 'list_replies', return_value=batch), \
         patch.object(inbound.classify, 'classify_reply', return_value={'intent':'unsubscribe','status':'Replied'}), \
         patch.object(inbound, '_draft_reply') as draft, patch.object(inbound.sms_engine, 'maybe_warm_text') as sms:
        assert inbound.sync_replies(db)['scanned'] == 1
        assert inbound.sync_replies(db)['duplicates'] == 1
        draft.assert_not_called(); sms.assert_not_called()
    assert db.scalar(select(func.count()).select_from(Message)) == 1
    assert db.scalar(select(DoNotContact)).value == item['from_email']
    assert db.get(MailboxSyncHealth, 'personal').status == 'complete'


def test_bounce_is_suppressed_not_a_reply(db):
    item = record(bounce_to='bad@real.test')
    db.add(Message(channel='email', direction='outbound', from_account='personal',
                   to_email='bad@real.test', status='Sent', sent_at=item['received_at']-timedelta(days=1)))
    db.commit()
    with patch.object(inbound, 'ACCOUNTS', ['personal']), patch('app.runtime_config.apply_to_settings'), \
         patch.object(gmail, 'list_replies', return_value=gmail.InboundBatch([item], through=item['received_at'])), \
         patch.object(inbound.classify, 'classify_reply') as classify:
        inbound.sync_replies(db)
        classify.assert_not_called()
    assert db.scalar(select(DoNotContact)).value == 'bad@real.test'
    totals = outreach_performance.report(db, 7)['totals']
    assert totals['replies'] == 0 and totals['delivery_confirmed'] == 0


def test_old_draft_sent_today_is_in_window_legacy_reply_not_dated(db):
    now = datetime.now(timezone.utc)
    db.add_all([Message(channel='email', direction='outbound', to_email='one@realbiz.co', status='Replied',
                        created_at=now-timedelta(days=40), sent_at=now),
                Message(channel='sms', direction='outbound', status='Sent', sent_at=now, delivery_status='delivered'),
                Message(channel='email', direction='inbound', created_at=now-timedelta(days=40))])
    db.commit()
    report = outreach_performance.report(db, 7)
    assert report['totals']['sent'] == 2
    assert report['totals']['replies'] == 0
    assert report['totals']['legacy_replied_outbound_undated'] == 1
    assert report['totals']['delivery_confirmed'] == 1
    assert report['totals']['delivery_unconfirmed'] == 1
    assert report['reply_count_complete'] is False


def test_suppression_after_draft_and_bounce_eligibility(db):
    import uuid
    lead = Lead(id=uuid.uuid4(), segment='commercial', email='one@realbiz.co', phone='+16035550123', status='New')
    db.add(lead); db.commit()
    fu = FollowUp(entity_type='lead', entity_id=lead.id, step=1, due_date=datetime.now().date(), channel='email')
    msg = Message(channel='email', direction='outbound', entity_type='lead', entity_id=lead.id,
                  to_email=lead.email, status='Drafted')
    db.add(msg); db.commit()
    assert followups.eligibility(db, fu) == 'eligible'
    msg.delivery_status='bounced'; db.commit()
    assert followups.eligibility(db, fu) == 'bounced_or_suppressed'
    msg.delivery_status=None
    db.add(DoNotContact(kind='email', value=lead.email)); db.commit()
    assert followups.eligibility(db, fu) == 'suppressed'
    with suppression_boundary.boundary(db.get_bind(), 'email', lead.email) as reason:
        assert reason == 'do_not_contact'


def test_partial_ingestion_never_advances_coverage(db):
    previous = datetime.now(timezone.utc)-timedelta(days=7)
    db.add(MailboxSyncHealth(account='personal', status='complete', checked_at=previous,
                             completed_through=previous, scanned=0)); db.commit()
    with patch.object(inbound, 'ACCOUNTS', ['personal']), patch('app.runtime_config.apply_to_settings'), \
         patch.object(gmail, 'list_replies', return_value=gmail.InboundBatch(status='partial', error_code='page_limit')) as fetch:
        result = inbound.sync_replies(db)
    health = db.get(MailboxSyncHealth, 'personal')
    assert health.status == 'partial'
    assert health.completed_through.replace(tzinfo=timezone.utc) == previous
    assert fetch.call_args.kwargs['since'] == previous-timedelta(minutes=5)
    assert result['health']['personal']['error_code'] == 'page_limit'


def test_permanent_dsn_is_parsed_from_machine_fields():
    now = datetime.now(timezone.utc)
    raw = b'From: Mailer <mailer-daemon@real.test>\r\nSubject: Failure\r\nMIME-Version: 1.0\r\nContent-Type: multipart/report; boundary="x"; report-type=delivery-status\r\n\r\n--x\r\nContent-Type: message/delivery-status\r\n\r\nReporting-MTA: dns; real.test\r\n\r\nFinal-Recipient: rfc822; failed@real.test\r\nAction: failed\r\nStatus: 5.1.1\r\n\r\n--x--\r\n'
    svc = MagicMock()
    svc.users().getProfile().execute.return_value={'emailAddress':'owner@real.test'}
    svc.users().messages().list().execute.return_value={'messages':[{'id':'dsn'}]}
    svc.users().messages().get().execute.return_value={'id':'dsn','internalDate':str(int(now.timestamp()*1000)-1000),
                                                       'raw':base64.urlsafe_b64encode(raw).decode()}
    with patch.object(gmail, '_service', return_value=svc):
        batch=gmail.list_replies()
    assert batch.status == 'complete'
    assert batch[0]['bounce_recipients'] == ['failed@real.test']


def test_replied_candidates_never_generate_or_dispatch(db):
    import uuid
    lid=uuid.uuid4()
    db.add(Lead(id=lid, segment='commercial', email='reply@realbiz.co', status='New'))
    db.add(Message(channel='email', direction='outbound', entity_type='lead', entity_id=lid,
                   to_email='reply@realbiz.co', status='Replied'))
    db.add(FollowUp(entity_type='lead', entity_id=lid, step=1, due_date=datetime.now().date(), channel='email'))
    db.commit()
    with patch.object(followups.client, 'complete_json') as ai, patch.object(followups.outreach, 'dispatch_email') as send:
        result=followups.process_due_followups(db)
    ai.assert_not_called(); send.assert_not_called()
    assert result['due'] == 1 and result['eligible'] == 0
    assert result['eligibility'] == {'replied':1}


def test_stop_ingestion_does_not_forward_or_draft(db):
    from app import sms_engine
    with patch.object(sms_engine, '_forward_reply_to_owner') as forward, \
         patch.object(inbound.classify, 'classify_reply') as classify:
        msg=sms_engine.record_inbound(db, phone='+16035551234', body='STOP please')
    forward.assert_not_called(); classify.assert_not_called()
    assert msg.status == 'Unsubscribed'
    assert db.scalar(select(DoNotContact)).kind == 'phone'


def test_daily_buckets_normalize_timezone():
    from datetime import timezone, timedelta
    stamp=datetime(2026,11,6,23,30,tzinfo=timezone(timedelta(hours=-5)))
    assert outreach_performance._day(stamp) == '2026-11-07'


def test_skipped_pages_do_not_starve_eligible_followups(db):
    import uuid
    today = datetime.now().date()
    blocked = []
    for i in range(401):
        lid = uuid.uuid4()
        email = f'blocked{i}@realbiz.co' if i % 3 else None
        db.add(Lead(id=lid, segment='commercial', email=email, score=100, status='New'))
        fu = FollowUp(entity_type='lead', entity_id=lid, step=1, due_date=today, channel='email')
        blocked.append(fu)
        db.add(fu)
        if i % 3 == 1:
            db.add(DoNotContact(kind='email', value=email))
        elif i % 3 == 2:
            db.add(Message(entity_type='lead', entity_id=lid, channel='email', direction='outbound',
                           to_email=email, status='Sent', delivery_status='bounced'))
    eligible = []
    for i in range(2):
        lid = uuid.uuid4()
        db.add(Lead(id=lid, segment='commercial', email=f'eligible{i}@realbiz.co', score=0, status='New'))
        fu = FollowUp(entity_type='lead', entity_id=lid, step=1, due_date=today, channel='email')
        eligible.append(fu)
        db.add(fu)
    db.commit()
    with patch.object(followups.client, 'complete_json', return_value={'body':'Follow-up'}), \
         patch.object(followups.memory, 'entity_context', return_value=''), \
         patch.object(followups.outreach, 'dispatch_email', return_value=SimpleNamespace(status='Drafted')) as send:
        first = followups.process_due_followups(db, limit=1)
        assert first['eligible'] == 1
        assert first['due'] == 402
        assert send.call_count == 1
        assert sum(f.completed for f in eligible) == 1
        second = followups.process_due_followups(db, limit=1)
        assert second['eligible'] == 1
        assert send.call_count == 2
        assert all(f.completed for f in eligible)
        assert all(not f.completed for f in blocked)
        assert {c.kwargs['to_email'] for c in send.call_args_list} == {
            'eligible0@realbiz.co', 'eligible1@realbiz.co'}


def test_pagination_does_not_skip_after_completed_page_is_flushed(db):
    import uuid
    today = datetime.now().date()
    for i in range(401):
        lid = uuid.uuid4()
        db.add(Lead(id=lid, segment='commercial', email=f'lead{i}@realbiz.co', score=1, status='New'))
        db.add(FollowUp(entity_type='lead', entity_id=lid, step=1,
                        due_date=today-timedelta(days=1) if i < 400 else today, channel='email'))
        if i < 400:
            db.add(Message(entity_type='lead', entity_id=lid, channel='email', direction='outbound',
                           to_email=f'lead{i}@realbiz.co', status='Replied'))
    db.commit()
    with patch.object(followups.client, 'complete_json', return_value={'body':'Follow-up'}), \
         patch.object(followups.memory, 'entity_context', return_value=''), \
         patch.object(followups.outreach, 'dispatch_email', return_value=SimpleNamespace(status='Drafted')) as send:
        assert followups.process_due_followups(db, limit=0)['due'] == 0
        send.assert_not_called()
        result = followups.process_due_followups(db, limit=1)
        assert result['eligibility'] == {'replied':400, 'eligible':1}
        send.assert_called_once()
        assert send.call_args.kwargs['to_email'] == 'lead400@realbiz.co'
