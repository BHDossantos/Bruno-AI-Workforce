"""No credentials, provider requests, writes or activation in staging reports."""
import json
from types import SimpleNamespace

import pytest

from app.config import settings
from app.scripts import stage_inbound_assistant as staging


class DB:
    def __init__(self, values=None, fail=False):
        self.values = values or {}
        self.fail = fail
    def get(self, model, key):
        if self.fail:
            raise RuntimeError('secret-db-url-must-not-leak')
        return SimpleNamespace(value=self.values[key]) if key in self.values else None


@pytest.fixture
def config(monkeypatch):
    keys = dict(twilio_account_sid='secret-sid', twilio_auth_token='secret-token',
                twilio_voice_number='+15550001111', twilio_from_number='+15550001111',
                twilio_insurance_number='', producer_cell='15550002222', producer_callback='',
                inbound_assistant_number='', inbound_assistant_transfer_number='',
                inbound_assistant_verified_transfer_number='', inbound_assistant_enabled=False)
    for key, value in keys.items():
        monkeypatch.delenv(key.upper(), raising=False)
        monkeypatch.setattr(settings, key, value)


def test_reuses_existing_configuration_without_secrets_or_activation(config):
    result = staging.stage(DB())
    assert result['existing_credentials_configured'] is True
    assert result['account_verified'] is False
    assert result['balance_verified'] is False
    assert result['ready_for_activation'] is False
    assert result['proposed_environment'] == {
        'INBOUND_ASSISTANT_ENABLED': 'false',
        'INBOUND_ASSISTANT_NUMBER': '+15550001111',
        'INBOUND_ASSISTANT_TRANSFER_NUMBER': '+15550002222',
        'INBOUND_ASSISTANT_VERIFIED_TRANSFER_NUMBER': '',
    }
    assert 'secret-' not in json.dumps(result)
    assert settings.inbound_assistant_number == ''
    assert settings.inbound_assistant_enabled is False


def test_stored_configuration_and_env_precedence(config, monkeypatch):
    db = DB({'cfg:twilio_voice_number': '+15550004444', 'cfg:producer_cell': '+15550005555',
             'cfg:twilio_auth_token': ''})
    report = staging.stage(db)
    assert report['existing_credentials_configured'] is False
    assert report['proposed_environment']['INBOUND_ASSISTANT_NUMBER'] == '+15550004444'
    monkeypatch.setenv('TWILIO_AUTH_TOKEN', 'env-secret')
    monkeypatch.setenv('TWILIO_VOICE_NUMBER', '+15550006666')
    report = staging.stage(db)
    assert report['existing_credentials_configured'] is True
    assert report['proposed_environment']['INBOUND_ASSISTANT_NUMBER'] == '+15550006666'
    assert 'env-secret' not in json.dumps(report)


def test_config_failure_never_proposes_defaults_or_prints_errors(config):
    result = staging.stage(DB(fail=True))
    assert result['configuration_readable'] is False
    assert result['proposed_environment']['INBOUND_ASSISTANT_NUMBER'] == ''
    assert 'secret-db' not in json.dumps(result)


@pytest.mark.parametrize('target', ['+15550001111', '+15550007777'])
def test_direct_and_other_public_number_loops(config, monkeypatch, target):
    monkeypatch.setattr(settings, 'twilio_insurance_number', '+15550007777')
    monkeypatch.setattr(settings, 'inbound_assistant_transfer_number', target)
    result = staging.stage(DB())
    assert result['proposed_environment']['INBOUND_ASSISTANT_TRANSFER_NUMBER'] == ''
    assert any('loop' in item for item in result['blockers'])


def test_existing_enablement_and_verification_never_copied_to_proposal(config, monkeypatch):
    monkeypatch.setattr(settings, 'inbound_assistant_enabled', True)
    monkeypatch.setattr(settings, 'inbound_assistant_verified_transfer_number', '+15550002222')
    result = staging.stage(DB())
    assert result['currently_enabled'] is True
    assert result['proposed_environment']['INBOUND_ASSISTANT_ENABLED'] == 'false'
    assert result['proposed_environment']['INBOUND_ASSISTANT_VERIFIED_TRANSFER_NUMBER'] == ''
    assert settings.inbound_assistant_enabled is True


@pytest.mark.parametrize('value', ['phone12345678901', '1555', '0115550002222', '<Dial>15550002222</Dial>'])
def test_ambiguous_phone_rejected(value):
    assert staging.phone(value) == ''
