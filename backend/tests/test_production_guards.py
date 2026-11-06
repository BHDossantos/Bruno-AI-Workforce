"""Offline security regressions; no shared DB, providers or app startup."""
import base64
import hashlib
import hmac

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.database import get_db
from app.routers import resend_webhook as webhook


@pytest.fixture(autouse=True)
def local_environment(monkeypatch):
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("RENDER_EXTERNAL_URL", raising=False)


def config(**overrides):
    return Settings(_env_file=None, **{
        "environment": "production", "secret_key": "fixture-signing-key-for-offline-tests-only",
        "admin_password": "fixture-admin-password", **overrides,
    })


@pytest.mark.parametrize("mode", ["production", " PROD ", "staging", "", "produciton"])
def test_nonlocal_modes_reject_signing_defaults(mode):
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        config(environment=mode, secret_key="dev-secret-change-me")


@pytest.mark.parametrize("key", ["", "  ", "test-secret", "ci-secret", "x" * 31])
def test_short_or_default_signing_keys_rejected(key):
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        config(secret_key=key)


@pytest.mark.parametrize("password", ["", "change-me", "testpass", "x" * 11])
def test_default_or_short_admin_password_rejected(password):
    with pytest.raises(ValidationError, match="ADMIN_PASSWORD"):
        config(admin_password=password)


@pytest.mark.parametrize("marker,value", [("RENDER", "true"), ("RENDER_EXTERNAL_URL", "https://example.invalid")])
def test_render_cannot_silently_keep_development_defaults(monkeypatch, marker, value):
    monkeypatch.setenv(marker, value)
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        config(environment="development", secret_key="dev-secret-change-me")


def test_secure_config_and_local_defaults():
    assert config().secure_runtime
    assert not config(environment="test", secret_key="test-secret", admin_password="testpass").secure_runtime


def test_validation_error_does_not_print_credentials():
    with pytest.raises(ValidationError) as exc:
        config(secret_key="private-short-secret")
    assert "private-short-secret" not in str(exc.value)
    assert "fixture-admin-password" not in str(exc.value)


KEY = b"offline-fixture-key"
SECRET = "whsec_" + base64.b64encode(KEY).decode()
BODY = b'{"type":"unhandled.test.event"}'
NOW = 1800000000


def signed_headers(timestamp=NOW, prefix="svix", version="v1"):
    payload = f"msg_fixture.{timestamp}.".encode() + BODY
    signature = base64.b64encode(hmac.new(KEY, payload, hashlib.sha256).digest()).decode()
    return {f"{prefix}-id": "msg_fixture", f"{prefix}-timestamp": str(timestamp),
            f"{prefix}-signature": f"{version},{signature}"}


@pytest.fixture
def endpoint(monkeypatch):
    monkeypatch.setattr(webhook.time, "time", lambda: NOW)
    monkeypatch.setattr(webhook, "settings", config(resend_webhook_secret=SECRET))
    app = FastAPI()
    app.include_router(webhook.router)
    class NoDatabase:
        def __getattr__(self, name):
            raise AssertionError("Unauthorized or unhandled events must not access the DB")
    app.dependency_overrides[get_db] = lambda: NoDatabase()
    return TestClient(app)


@pytest.mark.parametrize("prefix", ["svix", "webhook"])
def test_valid_signature_reaches_handler(endpoint, prefix):
    assert endpoint.post("/resend/inbound", content=BODY, headers=signed_headers(prefix=prefix)).status_code == 200


@pytest.mark.parametrize("delta", [-301, 301])
def test_correct_but_stale_or_future_signatures_rejected(endpoint, delta):
    assert endpoint.post("/resend/inbound", content=BODY, headers=signed_headers(NOW + delta)).status_code == 401


@pytest.mark.parametrize("headers", [{}, signed_headers(version="v2"), {**signed_headers(), "svix-timestamp": "invalid"}])
def test_missing_invalid_or_wrong_version_signature_rejected(endpoint, headers):
    assert endpoint.post("/resend/inbound", content=BODY, headers=headers).status_code == 401


def test_signed_payload_cannot_be_modified(endpoint):
    assert endpoint.post("/resend/inbound", content=BODY + b" ", headers=signed_headers()).status_code == 401


def test_rotation_signature_list(endpoint):
    headers = signed_headers()
    headers["svix-signature"] = "v1,wrong " + headers["svix-signature"]
    assert endpoint.post("/resend/inbound", content=BODY, headers=headers).status_code == 200


@pytest.mark.parametrize("secret", ["whsec_", "not-base64!"])
def test_malformed_secret_rejects_signed_requests(endpoint, monkeypatch, secret):
    monkeypatch.setattr(webhook.settings, "resend_webhook_secret", secret)
    assert endpoint.post("/resend/inbound", content=BODY, headers=signed_headers()).status_code == 401


def test_unconfigured_production_endpoint_never_reads_payload(endpoint, monkeypatch):
    monkeypatch.setattr(webhook.settings, "resend_webhook_secret", "")
    assert endpoint.post("/resend/inbound", content=b"not-json").status_code == 503


def test_local_unsigned_fixtures_remain_supported(endpoint, monkeypatch):
    monkeypatch.setattr(webhook, "settings", config(environment="test", resend_webhook_secret=""))
    assert endpoint.post("/resend/inbound", content=BODY).status_code == 200


def test_published_svix_signature_vector(monkeypatch):
    # https://docs.svix.com/receiving/verifying-payloads/how-manual
    monkeypatch.setattr(webhook.time, "time", lambda: 1731705121)
    assert webhook._verify_svix(
        "whsec_plJ3nmyCDGBKInavdOK15jsl",
        {"svix-id": "msg_loFOjxBNrRLzqYUf", "svix-timestamp": "1731705121",
         "svix-signature": "v1,rAvfW3dJ/X/qxhsaXPOyyCGmRKsaKWcsNccKXlIktD0="},
        b'{"event_type":"ping","data":{"success":true}}',
    )


def test_invalid_signature_cannot_process_delivery_event(endpoint):
    payload = b'{"type":"email.delivered","data":{"email_id":"provider-fixture"}}'
    assert endpoint.post("/resend/inbound", content=payload, headers=signed_headers()).status_code == 401
