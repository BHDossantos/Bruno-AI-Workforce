"""One business phone number drives texting, caller-ID, transfers and the number
printed on outreach. Per-channel fields are overrides, and saving a new business
number clears them so a stale copy can't keep the old number ringing."""
import pytest

from .conftest import requires_db

NEW = "+18575551011"   # synthetic
OLD = "+18335550100"   # synthetic


@pytest.fixture
def numbers(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "business_phone", NEW)
    for f in ("twilio_from_number", "twilio_insurance_number", "twilio_voice_number",
              "transfer_caller_id", "producer_office_phone", "local_presence_numbers"):
        monkeypatch.setattr(settings, f, "")
    monkeypatch.setattr(settings, "voice_provider", "twilio")
    monkeypatch.setattr(settings, "twilio_account_sid", "AC_fixture")
    monkeypatch.setattr(settings, "twilio_auth_token", "fixture")
    return settings


def test_every_channel_uses_the_business_number(numbers):
    from app import phone_numbers
    from app.integrations import sms, twilio_voice
    assert sms.number_for("personal", "twilio") == NEW
    assert sms.number_for("insurance", "twilio") == NEW
    assert twilio_voice._voice_number() == NEW
    assert twilio_voice.bridge_caller_id("+16175551212") == NEW
    assert phone_numbers.office_phone() == "(857) 555-1011"


def test_a_per_channel_override_still_wins(numbers):
    from app.integrations import twilio_voice
    numbers.twilio_voice_number = "+16035550100"
    assert twilio_voice._voice_number() == "+16035550100"


def test_signature_and_email_show_the_business_number(numbers):
    from app import email_template, everquote
    assert "phone# (857) 555-1011" in everquote._signature()
    assert "tel:+18575551011" in email_template._phone_line()


def test_display_and_e164_formats():
    from app import phone_numbers
    assert phone_numbers.e164("(857) 555-1011") == NEW
    assert phone_numbers.e164("18575551011") == NEW
    assert phone_numbers.display(NEW) == "(857) 555-1011"
    assert phone_numbers.display("+390612345678") == "+390612345678"


def test_env_var_pins_are_reported(monkeypatch):
    from app import phone_numbers
    monkeypatch.setenv("TWILIO_VOICE_NUMBER", OLD)
    assert "TWILIO_VOICE_NUMBER" in phone_numbers.pinned_by_env()


@requires_db
def test_saving_business_phone_clears_stale_overrides(client, numbers):  # client → schema
    from app import runtime_config
    from app.database import SessionLocal
    from app.models import Setting
    db = SessionLocal()
    try:
        runtime_config.save(db, "twilio_voice_number", OLD)
        runtime_config.save(db, "producer_office_phone", "(833) 555-0100")
        assert numbers.twilio_voice_number == OLD
        runtime_config.save(db, "business_phone", NEW)
        assert numbers.business_phone == NEW
        assert numbers.twilio_voice_number == "" and numbers.producer_office_phone == ""
        assert (db.get(Setting, "cfg:twilio_voice_number").value or "") == ""
        runtime_config.apply_to_settings(db)          # survives a reload
        assert numbers.twilio_voice_number == ""
    finally:
        db.close()
        _forget("business_phone", "twilio_voice_number", "producer_office_phone")


def _forget(*fields):
    from app.database import SessionLocal
    from app.models import Setting
    db = SessionLocal()
    try:
        for f in fields:
            row = db.get(Setting, "cfg:" + f)
            if row is not None:
                db.delete(row)
        db.commit()
    finally:
        db.close()


@requires_db
def test_setup_saves_business_phone_before_overrides(client, auth_headers, numbers):
    try:
        r = client.post("/setup", headers=auth_headers,
                        json={"twilio_voice_number": "+16035550100", "business_phone": NEW})
        assert r.status_code == 200
        assert numbers.twilio_voice_number == "+16035550100"   # typed override kept
        phone = r.json()["status"]["phone"]
        assert phone["business_phone"] == NEW and phone["caller_id"] == "+16035550100"
        client.post("/setup", headers=auth_headers, json={"business_phone": NEW})  # reset
        assert numbers.twilio_voice_number == ""
    finally:
        _forget("business_phone", *__import__("app.phone_numbers").phone_numbers.OVERRIDES)
