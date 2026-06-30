"""SendGrid integration — reliable email delivery via the SendGrid v3 API.

Unlike Instantly/Smartlead (which run their own campaigns), SendGrid is a pure
delivery channel: the app keeps full control of the copy, sequences, caps and
automation, and just sends THROUGH SendGrid instead of a personal Gmail that
Google revokes at volume. Key-gated: a no-op when not configured.

Requires a VERIFIED sender in SendGrid (Single Sender Verification, or full
domain authentication with SPF/DKIM for best deliverability).
"""
from __future__ import annotations

import logging

import httpx

from ..config import settings

log = logging.getLogger("bruno.sendgrid")
_SEND = "https://api.sendgrid.com/v3/mail/send"


def is_configured() -> bool:
    return bool(settings.sendgrid_api_key and settings.sendgrid_from_email)


def has_key() -> bool:
    return bool(settings.sendgrid_api_key)


def _headers() -> dict:
    return {"Authorization": f"Bearer {settings.sendgrid_api_key}",
            "Content-Type": "application/json"}


def send_email(to: str, subject: str, html: str, *, reply_to: str | None = None) -> str | None:
    """Send one HTML email via SendGrid. Returns a message id on success, else None."""
    if not is_configured() or not to:
        return None
    payload: dict = {
        "personalizations": [{"to": [{"email": to}], "subject": subject or "(no subject)"}],
        "from": {"email": settings.sendgrid_from_email,
                 "name": settings.sender_name or settings.sendgrid_from_email},
        "content": [{"type": "text/html", "value": html or ""}],
    }
    if reply_to:
        payload["reply_to"] = {"email": reply_to}
    try:
        r = httpx.post(_SEND, json=payload, headers=_headers(), timeout=30)
        r.raise_for_status()
        return r.headers.get("X-Message-Id") or "sendgrid"
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("SendGrid send failed (%s): %s", to, exc)
        return None


def verify() -> dict:
    """Check the API key is valid (lists verified senders). For the Connect page."""
    if not has_key():
        return {"ok": False, "reason": "no API key"}
    try:
        r = httpx.get("https://api.sendgrid.com/v3/verified_senders",
                      headers=_headers(), timeout=20)
        r.raise_for_status()
        return {"ok": True, "reason": None}
    except Exception as exc:  # pragma: no cover - network guard
        return {"ok": False, "reason": f"{str(exc)[:100]}"}
