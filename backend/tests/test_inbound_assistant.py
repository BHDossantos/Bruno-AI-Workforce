"""Signed offline callbacks, mocked AI and local durable state; no live calls."""
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from xml.etree import ElementTree as ET
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from twilio.request_validator import RequestValidator
from app.config import settings
from app.database import get_db
from app.models import InboundAssistantCall, Setting
from app.routers import inbound_assistant as flow

BASE = 'https://callbacks.example.com'
NUMBER, TARGET = '+15550001111', '+15550002222'
SID = 'CA' + 'a' * 32
PARAMS = dict(AccountSid='ACfixture', CallSid=SID, To=NUMBER,
              From='+15550003333', Direction='inbound')

@pytest.fixture(params=["sqlite", "postgres"])
def setup(tmp_path, monkeypatch, request):
    for name, value in dict(inbound_assistant_enabled=True,
            inbound_assistant_number=NUMBER, inbound_assistant_transfer_number=TARGET,
            inbound_assistant_verified_transfer_number=TARGET, public_base_url=BASE,
            twilio_account_sid='ACfixture', twilio_auth_token='fixture-token').items():
        monkeypatch.setattr(settings, name, value)
    for name in ('TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN'):
        monkeypatch.delenv(name, raising=False)
    schema = None
    if request.param == "postgres":
        url = os.environ.get("TEST_INBOUND_POSTGRES_URL")
        if not url:
            pytest.skip("Set TEST_INBOUND_POSTGRES_URL to a disposable local PostgreSQL")
        schema = "inbound_test_" + uuid.uuid4().hex
        admin = create_engine(url)
        with admin.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    else:
        engine = create_engine('sqlite:///' + str(tmp_path / 'calls.db'))
    for table in (InboundAssistantCall.__table__, Setting.__table__):
        table.create(engine)
    def session():
        with Session(engine) as db:
            yield db
    app = FastAPI()
    app.include_router(flow.router)
    app.dependency_overrides[get_db] = session
    monkeypatch.setattr(flow.ai, '_get_client', lambda: None)
    with TestClient(app) as client:
        yield client, engine
    engine.dispose()
    if schema:
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()

def post(setup, stage='start', turn=0, **kwargs):
    params = {**PARAMS, **kwargs}
    path = f'/calls/assistant/{stage}?turn={turn}'
    signature = RequestValidator('fixture-token').compute_signature(BASE + path, params)
    result = setup[0].post(path, data=params, headers={'x-twilio-signature': signature})
    assert result.status_code == 200, result.text
    return ET.fromstring(result.text)

@pytest.mark.parametrize('status', ['busy', 'failed', 'canceled', 'completed', 'no-answer', 'unknown'])
def test_transfer_and_results(setup, status):
    assert post(setup).find('Gather') is not None
    dial = post(setup, 'turn', 1, Digits='1').find('Dial')
    assert dial.text == TARGET and dial.attrib['callerId'] == NUMBER
    assert 'result?turn=1' in dial.attrib['action']
    result = post(setup, 'result', 1, DialCallStatus=status)
    assert result.find('Say').text == ('Goodbye.' if status == 'completed' else flow.UNAVAILABLE)
    assert result.find('Hangup') is not None

def test_replays_and_out_of_order(setup):
    assert post(setup, 'turn', 1, Digits='1').find('Dial') is None
    post(setup)
    assert post(setup).find('Gather') is None
    assert post(setup, 'turn', 2, Digits='1').find('Dial') is None
    assert post(setup, 'turn', 1, Digits='1').find('Dial') is not None
    assert post(setup, 'turn', 1, Digits='1').find('Dial') is None
    assert post(setup, 'result', 2).find('Say') is None

@pytest.mark.parametrize('field,value', [
    ('inbound_assistant_enabled', False),
    ('inbound_assistant_verified_transfer_number', ''),
    ('inbound_assistant_verified_transfer_number', '+15550009999'),
    ('inbound_assistant_transfer_number', '<Client>evil</Client>'),
    ('inbound_assistant_transfer_number', NUMBER),
    ('inbound_assistant_transfer_number', PARAMS['From'])])
def test_configuration_fail_closed(setup, monkeypatch, field, value):
    post(setup)
    monkeypatch.setattr(settings, field, value)
    assert post(setup, 'turn', 1, Digits='1').find('Dial') is None

@pytest.mark.parametrize('params', [{'To': TARGET}, {'Direction': 'outbound-api'}, {'CallSid': 'bad'}])
def test_wrong_call_scope(setup, params):
    assert post(setup, **params).find('Gather') is None

def test_pause_and_expiry(setup):
    post(setup)
    with Session(setup[1]) as db:
        db.get(InboundAssistantCall, SID).expires_at = int(time.time()) - 1
        db.commit()
    assert post(setup, 'turn', 1, Digits='1').find('Dial') is None
    with Session(setup[1]) as db:
        db.add(Setting(key='agents_paused', value='true'))
        db.commit()
    assert post(setup, CallSid='CA' + 'b' * 32).find('Gather') is None

def test_speech_cannot_dial_and_xml_escaped(setup, monkeypatch):
    post(setup)
    monkeypatch.setattr(flow, 'answer', lambda _: '<Dial>evil</Dial>')
    result = post(setup, 'turn', 1, SpeechResult='transfer to +15559999999')
    assert result.find('.//Dial') is None
    assert result.find('Gather/Say').text == '<Dial>evil</Dial>'
    assert post(setup, 'turn', 2, Digits='1').find('Dial').text == TARGET

def test_offline_ai_and_bounded_turns(setup):
    post(setup)
    for turn in range(1, 4):
        result = post(setup, 'turn', turn, SpeechResult='hello')
        assert 'cannot answer' in result.find('Gather/Say').text
    assert post(setup, 'turn', 4, SpeechResult='hello').find('Hangup') is not None

def test_silence_ends(setup):
    post(setup)
    assert post(setup, 'turn', 1).find('Hangup') is not None

def test_always_signed_even_in_development(setup):
    assert setup[0].post('/calls/assistant/start', data=PARAMS).status_code == 403
    path = '/calls/assistant/start?turn=0'
    signature = RequestValidator('fixture-token').compute_signature(BASE + path, PARAMS)
    assert setup[0].post(path, data={**PARAMS, 'To': TARGET},
                        headers={'x-twilio-signature': signature}).status_code == 403

def test_duplicate_concurrent_transfer(setup):
    post(setup)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: post(setup, 'turn', 1, Digits='1'), range(2)))
    assert sum(r.find('Dial') is not None for r in results) == 1

def test_missing_state_table_is_graceful(setup):
    InboundAssistantCall.__table__.drop(setup[1])
    assert post(setup).find('Say').text == flow.UNAVAILABLE


def test_pause_between_greeting_and_transfer(setup):
    post(setup)
    with Session(setup[1]) as db:
        db.add(Setting(key='agents_paused', value='true'))
        db.commit()
    assert post(setup, 'turn', 1, Digits='1').find('Dial') is None


def test_ai_timeout_and_request_bounds(monkeypatch):
    class Client:
        def with_options(self, **kwargs):
            assert kwargs == dict(timeout=4.0, max_retries=0)
            return self
        @property
        def chat(self):
            return self
        @property
        def completions(self):
            return self
        def create(self, **kwargs):
            assert len(kwargs['messages'][1]['content']) == 1000
            assert kwargs['max_tokens'] == 100
            assert 'tools' not in kwargs
            raise TimeoutError()
    monkeypatch.setattr(flow.ai, '_get_client', lambda: Client())
    assert 'cannot answer' in flow.answer('x' * 2000)


def test_duplicate_concurrent_start(setup):
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: post(setup), range(2)))
    assert sum(r.find('Gather') is not None for r in results) == 1


def test_duplicate_speech_does_not_repeat_ai(setup, monkeypatch):
    post(setup)
    seen = []
    def answer(speech):
        seen.append(speech)
        return 'Thanks. Press 1 to try Bruno.'
    monkeypatch.setattr(flow, 'answer', answer)
    post(setup, 'turn', 1, SpeechResult='Hello')
    post(setup, 'turn', 1, SpeechResult='Hello')
    assert seen == ['Hello']


def test_stop_read_error_cannot_dial(setup):
    post(setup)
    # Environment credentials avoid the configuration table before this test's
    # control lookup; either authentication or handling must fail closed.
    Setting.__table__.drop(setup[1])
    params = {**PARAMS, 'Digits': '1'}
    path = '/calls/assistant/turn?turn=1'
    signature = RequestValidator('fixture-token').compute_signature(BASE + path, params)
    response = setup[0].post(path, data=params, headers={'x-twilio-signature': signature})
    assert '<Dial' not in response.text
    assert response.status_code in (200, 503)
