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


def is_configured() -> bool:
    return bool(settings.twilio_account_sid and settings.twilio_auth_token and settings.twilio_from_number)


def number_for(account: str) -> str:
    if account == "insurance" and settings.twilio_insurance_number:
        return settings.twilio_insurance_number
    return settings.twilio_from_number


def send_sms(to: str, body: str, account: str = "personal") -> str | None:
    """Send an SMS. Returns the Twilio message SID, or None if unconfigured/failed."""
    if not is_configured() or not to or not body:
        return None
    url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Messages.json"
    try:
        resp = httpx.post(
            url,
            data={"To": to, "From": number_for(account), "Body": body},
            auth=(settings.twilio_account_sid, settings.twilio_auth_token),
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json().get("sid")
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("Twilio send failed (%s): %s", to, exc)
        return None


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
    url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Messages.json"
    try:
        resp = httpx.post(
            url, data={"To": to_wa, "From": from_wa, "Body": body},
            auth=(settings.twilio_account_sid, settings.twilio_auth_token), timeout=20,
        )
        resp.raise_for_status()
        return resp.json().get("sid")
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("Twilio WhatsApp send failed (%s): %s", to, exc)
        return None
