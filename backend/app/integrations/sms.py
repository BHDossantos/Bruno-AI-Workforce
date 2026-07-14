"""Two-way SMS via Twilio.

Sends are triggered when a lead becomes *warm* (replies to our email) and from
the in-app conversation thread. Inbound texts arrive via a Twilio webhook. All
no-ops cleanly when Twilio isn't configured.
"""
from __future__ import annotations

import logging

import httpx

from ..config import settings

log = logging.getLogger("bruno.sms")


def _sid() -> str:
    """Twilio Account SID, whitespace-stripped. A stray space/newline (from an env
    var or a paste) in the SID or token makes Twilio reject the Basic-auth with a
    20003 'Authenticate' 401 even though the characters are correct."""
    return (settings.twilio_account_sid or "").strip()


def _token() -> str:
    return (settings.twilio_auth_token or "").strip()


def _compat_configured() -> bool:
    """A Twilio-COMPATIBLE SMS transport (Twilio or SignalWire) with a from-number."""
    from . import telco
    return bool(telco.configured() and number_for("personal"))


def _use_plivo() -> bool:
    """Route texts through the Plivo backup when it's the selected provider, or —
    in 'auto' mode — whenever Plivo is connected and no Twilio-compatible carrier is."""
    from . import plivo
    provider = (settings.sms_provider or "auto").strip().lower()
    if provider == "plivo":
        return plivo.is_configured()
    if provider in ("twilio", "signalwire"):
        return False
    return plivo.is_configured() and not _compat_configured()  # auto: Plivo as fallback


def is_configured() -> bool:
    # Texting is available if ANY provider is connected — SignalWire or Twilio (the
    # Twilio-compatible transports) OR the Plivo backup. So a deactivated Twilio no
    # longer silently disables SMS.
    from . import plivo
    return _compat_configured() or plivo.is_configured()


def active_provider() -> str | None:
    """Which SMS provider a send would use right now — for status/UI."""
    from . import plivo, telco
    if _use_plivo():
        return "plivo"
    if telco.configured():
        return telco.provider()   # "signalwire" | "twilio"
    return "plivo" if plivo.is_configured() else None


def number_for(account: str) -> str:
    from . import telco
    if telco.provider() == "signalwire":
        if account == "insurance" and settings.signalwire_insurance_number:
            return settings.signalwire_insurance_number
        return settings.signalwire_from_number or settings.signalwire_insurance_number
    if account == "insurance" and settings.twilio_insurance_number:
        return settings.twilio_insurance_number
    # Fall back to whichever number IS set, so a send never goes out with an empty
    # From (which the carrier rejects) just because one field was left blank.
    return settings.twilio_from_number or settings.twilio_insurance_number


def send_with_error(to: str, body: str, account: str = "personal") -> tuple[str | None, str | None]:
    """Send an SMS, returning (message_sid, error_reason). Surfaces the REAL Twilio
    error (e.g. trial-account 'unverified number', invalid recipient, non-SMS
    number) instead of a bare None, so failures aren't all mislabeled 'not connected'."""
    from . import telco
    if _use_plivo():
        from . import plivo
        return plivo.send_with_error(to, body, account)
    if not telco.configured():
        return None, "No SMS provider connected — add SignalWire or Twilio, or the Plivo backup, in Setup."
    if not to:
        return None, "no recipient phone"
    if not body:
        return None, "empty message"
    if not number_for(account):
        return None, f"no {telco.label()} 'from' number set"
    url = telco.api_url("Messages.json")
    data = {"To": to, "From": number_for(account), "Body": body}
    # Ask the carrier to report the REAL delivery outcome (delivered/undelivered/
    # failed) to our webhook, so the app can show whether the text actually landed —
    # not just that it was accepted. No callback set → we'd only ever know "handed off".
    base = (settings.public_base_url or "").rstrip("/")
    if base:
        data["StatusCallback"] = f"{base}/sms/status"
    try:
        resp = httpx.post(url, data=data, auth=telco.auth(), timeout=20)
        if resp.status_code >= 400:
            try:
                j = resp.json()
                code, msg = j.get("code"), j.get("message", "")
            except Exception:
                code, msg = resp.status_code, (resp.text or "")[:160]
            hint = ""
            if code == 20003:
                hint = (f" (authentication failed — {telco.label()} is rejecting the credentials. "
                        "Re-check for a stray space/newline, or a mismatched/rotated token.)")
            elif code == 21608:
                hint = " (Twilio TRIAL account — you can only text numbers you've verified. Upgrade the account to text leads.)"
            elif code in (21211, 21214):
                hint = " (invalid recipient number)"
            elif code == 21606:
                hint = " (your 'from' number can't send SMS — use an SMS-capable number)"
            return None, f"{telco.label()} {code}: {msg}{hint}"
        return resp.json().get("sid"), None
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("SMS send failed (%s): %s", to, exc)
        return None, f"{telco.label()} error: {str(exc)[:160]}"


def send_sms(to: str, body: str, account: str = "personal") -> str | None:
    """Send an SMS. Returns the Twilio message SID, or None if unconfigured/failed."""
    return send_with_error(to, body, account)[0]


def _twilio_whatsapp_configured() -> bool:
    return bool(settings.twilio_account_sid and settings.twilio_auth_token
                and settings.twilio_whatsapp_number)


def whatsapp_configured() -> bool:
    """WhatsApp via a legitimate official channel — Meta's own Cloud API or
    Twilio's WhatsApp Business API (unlike unofficial consumer-WhatsApp
    automation, which risks account bans)."""
    from . import whatsapp_cloud
    return whatsapp_cloud.is_configured() or _twilio_whatsapp_configured()


def send_whatsapp(to: str, body: str) -> str | None:
    """Send a WhatsApp message. Prefers Meta's Cloud API (no reseller markup,
    reuses the connected Facebook app) when configured; falls back to Twilio's
    WhatsApp Business API. Returns a message id/SID, or None if unconfigured/
    failed. `to` should be a plain E.164 phone number."""
    from . import whatsapp_cloud
    if whatsapp_cloud.is_configured():
        return whatsapp_cloud.send(to, body)
    if not _twilio_whatsapp_configured() or not to or not body:
        return None
    to_wa = to if to.startswith("whatsapp:") else f"whatsapp:{to}"
    from_wa = f"whatsapp:{settings.twilio_whatsapp_number}"
    url = f"https://api.twilio.com/2010-04-01/Accounts/{_sid()}/Messages.json"
    try:
        resp = httpx.post(
            url, data={"To": to_wa, "From": from_wa, "Body": body},
            auth=(_sid(), _token()), timeout=20,
        )
        resp.raise_for_status()
        return resp.json().get("sid")
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("Twilio WhatsApp send failed (%s): %s", to, exc)
        return None
