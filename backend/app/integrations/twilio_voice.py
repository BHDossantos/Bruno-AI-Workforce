"""Twilio Voice — place + record calls.

Two ways to call a lead, both bridged through Twilio so the lead sees your
business caller-ID and the call is recorded (with a spoken consent notice for
two-party-consent states like MA/FL):

  • Bridge: Twilio rings YOUR phone first; when you answer it dials the lead and
    connects you. Works from any device — no browser needed.
  • Browser softphone: the Twilio Voice JS SDK calls out from the browser using
    a short-lived access token (for when your phone's dead).

Raw REST + a hand-rolled access-token JWT (PyJWT) — no Twilio SDK dependency.
No-ops cleanly when unconfigured.
"""
from __future__ import annotations

import logging
import time

import httpx
import jwt

from ..config import settings

log = logging.getLogger("bruno.voice")

_CONSENT = ("This call is with a licensed insurance producer and may be "
            "recorded for quality and training purposes.")


def _voice_number() -> str:
    return (settings.twilio_voice_number or settings.twilio_insurance_number
            or settings.twilio_from_number or "")


def is_configured() -> bool:
    """Bridge calling: account creds + a caller-ID number + your callback phone."""
    return bool(settings.twilio_account_sid and settings.twilio_auth_token
                and _voice_number() and settings.producer_callback)


def browser_configured() -> bool:
    """Browser softphone: also needs an API Key + a TwiML App SID."""
    return bool(settings.twilio_account_sid and _voice_number()
                and settings.twilio_api_key_sid and settings.twilio_api_key_secret
                and settings.twilio_twiml_app_sid)


def _base_url() -> str:
    return (settings.public_base_url or "").rstrip("/")


def _xml(body: str) -> str:
    return f'<?xml version="1.0" encoding="UTF-8"?><Response>{body}</Response>'


def _dial_lead(lead_phone: str, lead_id: str | None) -> str:
    """TwiML that dials the lead with our caller-ID, plays the consent notice TO
    the lead when they answer, and records the bridged call."""
    base, rec = _base_url(), settings.call_recording_enabled
    announce = (f'<Number url="{base}/calls/twiml/announce">{lead_phone}</Number>'
                if (rec and base) else f'<Number>{lead_phone}</Number>')
    attrs = f' callerId="{_voice_number()}"'
    if rec and base:
        attrs += (' record="record-from-answer-dual"'
                  f' recordingStatusCallback="{base}/calls/recording'
                  f'{("?lead_id=" + lead_id) if lead_id else ""}"')
    return _xml(f'<Dial{attrs}>{announce}</Dial>')


def announce_twiml() -> str:
    """Played to the lead on answer, before bridging — the recording consent."""
    return _xml(f'<Say>{_CONSENT}</Say>')


def bridge_twiml(lead_phone: str, lead_id: str | None) -> str:
    return _dial_lead(lead_phone, lead_id)


def outbound_twiml(to: str, lead_id: str | None) -> str:
    """TwiML for a browser-softphone outbound call (Twilio hits the TwiML App)."""
    return _dial_lead(to, lead_id)


def place_bridge_call(lead_phone: str, lead_id: str | None) -> tuple[str | None, str | None]:
    """Ring the producer's phone; on answer, Twilio bridges to the lead. Returns
    (call_sid, error)."""
    if not is_configured():
        return None, "Calling not connected — add Twilio + your callback number on Setup."
    base = _base_url()
    if not base:
        return None, "PUBLIC_BASE_URL is not set, so Twilio can't reach the call webhooks."
    url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Calls.json"
    data = {
        "To": settings.producer_callback,   # ring YOU first
        "From": _voice_number(),
        "Url": f"{base}/calls/twiml/bridge?lead_phone={lead_phone}"
               + (f"&lead_id={lead_id}" if lead_id else ""),
        "StatusCallback": f"{base}/calls/status" + (f"?lead_id={lead_id}" if lead_id else ""),
        "StatusCallbackEvent": "completed",
    }
    try:
        r = httpx.post(url, data=data, auth=(settings.twilio_account_sid, settings.twilio_auth_token), timeout=20)
        if r.status_code >= 400:
            return None, f"Twilio {r.status_code}: {(r.text or '')[:160]}"
        return r.json().get("sid"), None
    except Exception as exc:  # pragma: no cover - network guard
        return None, f"Call failed: {str(exc)[:160]}"


def access_token(identity: str) -> str | None:
    """Mint a Twilio Voice access token (JWT) for the browser softphone."""
    if not browser_configured():
        return None
    now = int(time.time())
    payload = {
        "jti": f"{settings.twilio_api_key_sid}-{now}",
        "iss": settings.twilio_api_key_sid,
        "sub": settings.twilio_account_sid,
        "iat": now, "exp": now + 3600,
        "grants": {
            "identity": identity,
            "voice": {
                "outgoing": {"application_sid": settings.twilio_twiml_app_sid},
                "incoming": {"allow": True},
            },
        },
    }
    return jwt.encode(payload, settings.twilio_api_key_secret, algorithm="HS256",
                      headers={"cty": "twilio-fpa;v=1", "typ": "JWT"})
