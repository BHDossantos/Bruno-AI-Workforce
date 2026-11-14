"""Existing outbound AMD flow: recorded messages unchanged, live AI opt-in."""
from concurrent.futures import ThreadPoolExecutor
from xml.etree import ElementTree as ET

import pytest
from sqlalchemy.orm import Session
from twilio.request_validator import RequestValidator

from app.config import settings
from app.models import OutboundAssistantCall, Setting
from app.routers import calls, outbound_assistant as outbound
from app.routers import inbound_assistant as shared
from tests.test_inbound_assistant import setup, BASE, NUMBER, TARGET, SID

LEAD = '+15550003333'
PARAMS = dict(AccountSid='ACfixture', CallSid=SID, From=NUMBER, To=LEAD,
              Direction='outbound-api')


@pytest.fixture
def outgoing(setup, monkeypatch):
    setup[0].app.include_router(calls.router)
    setup[0].app.include_router(outbound.router)
    OutboundAssistantCall.__table__.create(setup[1])
    for name, value in dict(outbound_assistant_enabled=True,
            outbound_assistant_from_number=NUMBER,
            outbound_assistant_verified_transfer_number=TARGET,
            outbound_assistant_verified_caller_id=NUMBER,
            auto_dial_transfer_enabled=True, producer_cell=TARGET,
            producer_callback='', twilio_voice_number=NUMBER, twilio_from_number=NUMBER,
            twilio_insurance_number='', transfer_caller_id=NUMBER, local_presence_numbers='',
            producer_voicemail_url='https://audio.example.com/existing.mp3').items():
        monkeypatch.delenv(name.upper(), raising=False)
        monkeypatch.setattr(settings, name, value)
    return setup


def post(outgoing, path='/calls/twiml/amd', **params):
    data = {**PARAMS, **params}
    signature = RequestValidator('fixture-token').compute_signature(BASE + path, data)
    return outgoing[0].post(path, data=data, headers={'x-twilio-signature': signature})


def start(outgoing):
    result = post(outgoing, AnsweredBy='human')
    assert result.status_code == 200, result.text
    return ET.fromstring(result.text)


def test_existing_outbound_live_answer_gets_ai_before_personal_phone(outgoing):
    greeting = start(outgoing)
    assert greeting.find('Dial') is None
    assert 'AI assistant' in greeting.find('Gather/Say').text
    assert '/outbound-assistant/turn' in greeting.find('Gather').attrib['action']
    result = post(outgoing, '/calls/outbound-assistant/turn?turn=1', Digits='1')
    dial = ET.fromstring(result.text).find('Dial')
    assert dial.text == TARGET
    assert dial.attrib['callerId'] == NUMBER
    assert '/outbound-assistant/result' in dial.attrib['action']


@pytest.mark.parametrize('answer', ['machine_start', 'machine_end_beep', 'machine_end_silence',
                                    'machine_end_other', 'fax'])
@pytest.mark.parametrize('recorded', [True, False])
def test_nonhuman_twiml_byte_for_byte_unchanged(outgoing, monkeypatch, answer, recorded):
    if not recorded:
        monkeypatch.setattr(settings, 'producer_voicemail_url', '')
    expected = calls.voice.amd_twiml(answer or None, None)
    result = post(outgoing, AnsweredBy=answer)
    assert result.status_code == 200
    assert result.text == expected
    with Session(outgoing[1]) as db:
        assert db.get(OutboundAssistantCall, SID) is None


@pytest.mark.parametrize('flag', ['outbound_assistant_enabled', 'auto_dial_transfer_enabled'])
def test_disabled_preserves_legacy_human_behavior(outgoing, monkeypatch, flag):
    monkeypatch.setattr(settings, flag, False)
    expected = calls.voice.amd_twiml('human', None)
    assert post(outgoing, AnsweredBy='human').text == expected


def test_signed_only_and_no_direct_start_bypass(outgoing):
    assert outgoing[0].post('/calls/twiml/amd', data={**PARAMS, 'AnsweredBy': 'human'}).status_code == 403
    assert post(outgoing, '/calls/outbound-assistant/start', AnsweredBy='human').text == shared.finish()
    assert '<Dial' not in post(outgoing, '/calls/outbound-assistant/turn?turn=1', Digits='1').text


@pytest.mark.parametrize('params', [{'Direction': 'inbound'}, {'From': '+15550009999'}, {'CallSid': 'bad'}])
def test_wrong_call_scope_cannot_start(outgoing, params):
    assert '<Gather' not in post(outgoing, AnsweredBy='human', **params).text


@pytest.mark.parametrize('target', [NUMBER, LEAD, '+15550007777'])
def test_transfer_loops_rejected(outgoing, monkeypatch, target):
    monkeypatch.setattr(settings, 'producer_cell', target)
    monkeypatch.setattr(settings, 'outbound_assistant_verified_transfer_number', target)
    monkeypatch.setattr(settings, 'twilio_insurance_number', '+15550007777')
    start(outgoing)
    assert '<Dial' not in post(outgoing, '/calls/outbound-assistant/turn?turn=1', Digits='1').text


@pytest.mark.parametrize('field', ['outbound_assistant_verified_transfer_number', 'outbound_assistant_verified_caller_id'])
def test_unverified_transfer_blocked(outgoing, monkeypatch, field):
    monkeypatch.setattr(settings, field, '')
    start(outgoing)
    assert '<Dial' not in post(outgoing, '/calls/outbound-assistant/turn?turn=1', Digits='1').text


def test_duplicate_callbacks_emit_only_one_transfer(outgoing):
    start(outgoing)
    assert '<Gather' not in post(outgoing, AnsweredBy='human').text
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: post(outgoing, '/calls/outbound-assistant/turn?turn=1', Digits='1'), range(2)))
    assert sum('<Dial' in result.text for result in results) == 1


def test_speech_then_confirmed_transfer_and_no_answer(outgoing, monkeypatch):
    start(outgoing)
    monkeypatch.setattr(shared, 'answer', lambda _: 'Press 1 to speak to Bruno.')
    result = post(outgoing, '/calls/outbound-assistant/turn?turn=1', SpeechResult='Please connect me')
    assert '<Dial' not in result.text
    assert '<Gather' in result.text
    assert '<Dial' in post(outgoing, '/calls/outbound-assistant/turn?turn=2', Digits='1').text
    result = post(outgoing, '/calls/outbound-assistant/result?turn=2', DialCallStatus='no-answer')
    assert shared.UNAVAILABLE in result.text
    assert '<Play' not in result.text


def test_pause_or_cleared_cell_blocks_transfer(outgoing):
    start(outgoing)
    with Session(outgoing[1]) as db:
        db.add(Setting(key='cfg:producer_cell', value=''))
        db.commit()
    assert '<Dial' not in post(outgoing, '/calls/outbound-assistant/turn?turn=1', Digits='1').text


def test_missing_state_table_never_falls_back_to_direct_bridge(outgoing):
    OutboundAssistantCall.__table__.drop(outgoing[1])
    result = post(outgoing, AnsweredBy='human')
    assert '<Dial' not in result.text
    assert shared.UNAVAILABLE in result.text


def test_emergency_stop_after_ai_greeting(outgoing):
    start(outgoing)
    with Session(outgoing[1]) as db:
        db.add(Setting(key='agents_paused', value='true'))
        db.commit()
    assert '<Dial' not in post(outgoing, '/calls/outbound-assistant/turn?turn=1', Digits='1').text


def test_signed_get_amd_uses_existing_callback(outgoing):
    from urllib.parse import urlencode
    path = '/calls/twiml/amd?' + urlencode({**PARAMS, 'AnsweredBy': 'human'})
    signature = RequestValidator('fixture-token').compute_signature(BASE + path, {})
    response = outgoing[0].get(path, headers={'x-twilio-signature': signature})
    assert response.status_code == 200
    assert '/outbound-assistant/turn' in response.text


def test_missing_twilio_credentials_do_not_direct_bridge(outgoing, monkeypatch):
    monkeypatch.setattr(settings, 'twilio_auth_token', '')
    result = post(outgoing, AnsweredBy='human')
    assert result.status_code == 503
    assert '<Dial' not in result.text


@pytest.mark.parametrize('classification', ['unknown', ''])
def test_legacy_live_classification_cannot_bypass_ai(outgoing, classification):
    result = post(outgoing, AnsweredBy=classification)
    assert result.status_code == 200
    assert '<Gather' in result.text
    assert '<Dial' not in result.text
