"""Email delivery via Resend (https://resend.com).

A modern transactional-email API with strong deliverability. Same interface as
``integrations.sendgrid`` (``is_configured`` / ``from_for`` / ``send_with_error``)
so ``outreach.deliver`` can prefer it without special-casing. No-ops cleanly when
unconfigured.

Send: POST https://api.resend.com/emails with a Bearer key and JSON
{from, to, subject, html, reply_to}. A 2xx returns an ``id``; anything else carries
Resend's real error so a failure self-diagnoses.
"""
from __future__ import annotations

import logging

import httpx

from ..config import settings

log = logging.getLogger("bruno.resend")

_SEND = "https://api.resend.com/emails"

_ACCOUNT_FROM = {"insurance": "resend_from_insurance"}


def has_key() -> bool:
    return bool((settings.resend_api_key or "").strip())


def is_configured() -> bool:
    """Configured once we have an API key AND a verified sender to send from."""
    return bool(has_key() and (settings.resend_from_insurance or settings.resend_from_email))


def from_for(account: str | None) -> str:
    """The verified sender address for a dispatch account, else the default."""
    attr = _ACCOUNT_FROM.get(account or "")
    return (getattr(settings, attr, "") if attr else "") or settings.resend_from_email \
        or settings.resend_from_insurance


def replyto_for(account: str | None, from_email: str) -> str:
    """Where replies land: the configured monitored inbox, else the from-address."""
    return (settings.resend_reply_to or "").strip() or from_email


def send_with_error(to: str, subject: str, html: str, *, from_email: str | None = None,
                    reply_to: str | None = None) -> tuple[str | None, str | None]:
    """Send one HTML email via Resend. Returns (message_id, error_reason) — exactly
    one is non-None — mirroring sendgrid.send_with_error so callers stay provider-
    agnostic."""
    if not has_key():
        return None, "Resend isn't connected — add your API key in Setup."
    if not to:
        return None, "no recipient email"
    sender = from_email or from_for("insurance")
    if not sender:
        return None, "no Resend sender set — verify a domain and set the from address."
    name = settings.sender_name or ""
    payload: dict = {
        "from": f"{name} <{sender}>" if name else sender,
        "to": [to],
        "subject": subject or "(no subject)",
        "html": html or "",
    }
    if reply_to:
        payload["reply_to"] = reply_to
    headers = {"Authorization": f"Bearer {(settings.resend_api_key or '').strip()}",
               "Content-Type": "application/json"}
    try:
        r = httpx.post(_SEND, json=payload, headers=headers, timeout=30)
        if r.status_code >= 400:
            try:
                j = r.json()
                msg = j.get("message") or j.get("error") or str(j)[:160]
            except Exception:
                msg = (r.text or "")[:160]
            hint = ""
            if r.status_code in (401, 403):
                hint = " (auth failed — check the API key)"
            elif "domain" in (msg or "").lower():
                hint = " (verify your sending domain in Resend, or send from a verified address)"
            return None, f"Resend {r.status_code}: {msg}{hint}"
        try:
            mid = r.json().get("id")
        except Exception:
            mid = None
        return (mid or "resend-sent"), None
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("Resend send failed (%s): %s", to, exc)
        return None, f"Resend error: {str(exc)[:160]}"


def send_email(to: str, subject: str, html: str, *, from_email: str | None = None,
               reply_to: str | None = None) -> str | None:
    """Send one HTML email via Resend. Returns the message id, or None on failure."""
    return send_with_error(to, subject, html, from_email=from_email, reply_to=reply_to)[0]
