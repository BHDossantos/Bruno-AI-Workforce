import pytest
from types import SimpleNamespace
from app import outreach
from app.outbound_guard import RejectedDelivery
from app.integrations import gmail

def esp(send):
    return SimpleNamespace(from_for=lambda _: "sender", replyto_for=lambda *_: "sender", send_with_error=send)

def test_unknown_stops_fallback(monkeypatch):
    called = []
    monkeypatch.setattr(outreach, "_configured_esps", lambda: [esp(lambda *a, **k: (None, "timeout")), esp(lambda *a, **k: called.append("second"))])
    monkeypatch.setattr(gmail, "is_configured", lambda *_: True)
    monkeypatch.setattr(gmail, "send_with_error", lambda *a, **k: called.append("gmail"))
    assert outreach._deliver_once("person@realmail.co", "s", "message", "insurance")[0] is None
    assert called == []

def test_rejection_allows_overflow(monkeypatch):
    monkeypatch.setattr(outreach, "_configured_esps", lambda: [esp(lambda *a, **k: (None, RejectedDelivery("429"))), esp(lambda *a, **k: ("second", None))])
    assert outreach._send_via_esps("person@realmail.co", "s", "h", "insurance") == ("second", None)

def test_gmail_timeout_never_retries_smtp(monkeypatch):
    class Service:
        def users(self): return self
        def messages(self): return self
        def send(self, **kwargs): return self
        def execute(self): raise TimeoutError()
    monkeypatch.setattr(gmail, "_service", lambda *_: Service())
    monkeypatch.setattr(gmail, "_raw", lambda *a: {})
    called = []
    monkeypatch.setattr(gmail, "_send_smtp_verbose", lambda *a: called.append("smtp"))
    assert "unknown" in gmail.send_with_error("person@realmail.co", "s", "b")[1]
    assert called == []

def test_voice_paths_share_recipient_day_guard(monkeypatch):
    from app.integrations import voice
    captured = []
    monkeypatch.setattr(voice, "is_configured", lambda: True)
    monkeypatch.setattr(voice.outbound_guard, "invoke", lambda *args, **kw: (captured.append((args[:5], kw)) or (None, "held")))
    voice.place_auto_call("(212) 555-0100", "lead-one")
    voice.place_auto_call("+1 212-555-0100", "lead-two")
    assert captured[0] == captured[1]
    assert captured[0][1] == {"replay_accepted": False}


@pytest.mark.parametrize("provider", ["resend", "sendgrid"])
@pytest.mark.parametrize("status", [202, 408, 409, 500, 429])
def test_provider_receipt_and_rejection_classification(monkeypatch, provider, status):
    from app.integrations import resend, sendgrid
    module = {"resend": resend, "sendgrid": sendgrid}[provider]
    monkeypatch.setattr(module, "has_key", lambda: True)
    response = SimpleNamespace(status_code=status, headers={}, text="uncertain",
                               json=lambda: {"message": "response"})
    monkeypatch.setattr(module.httpx, "post", lambda *args, **kwargs: response)
    receipt, error = module.send_with_error("recipient@realmail.co", "subject", "body",
                                           from_email="sender@realmail.co")
    assert receipt is None
    assert isinstance(error, RejectedDelivery) == (status == 429)
