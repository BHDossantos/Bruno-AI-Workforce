"""Email delivery via SendGrid (https://sendgrid.com) — a SECOND email API used
ALONGSIDE Resend to raise total sending capacity.

Each ESP has its own daily/monthly quota, so ``outreach`` round-robins sends across
whichever providers are configured (Resend + SendGrid) to roughly double the
effective limit and add redundancy. This exposes the SAME small interface as
``resend`` (``is_configured`` / ``from_for`` / ``replyto_for`` / ``send_with_error``)
so the dispatch code treats them interchangeably. No-ops cleanly when unconfigured.

Send: POST https://api.sendgrid.com/v3/mail/send with a Bearer key and a JSON body
(personalizations/from/subject/content). A 2xx returns the ``X-Message-Id`` header;
anything else carries SendGrid's real error so a failure self-diagnoses.
"""
from __future__ import annotations

import logging

import httpx

from ..config import settings

log = logging.getLogger("bruno.sendgrid")

_SEND = "https://api.sendgrid.com/v3/mail/send"

_ACCOUNT_FROM = {"insurance": "sendgrid_from_insurance"}


def has_key() -> bool:
    return bool((settings.sendgrid_api_key or "").strip())


def is_configured() -> bool:
    """Configured once we have an API key AND a verified sender to send from."""
    return bool(has_key() and (settings.sendgrid_from_insurance or settings.sendgrid_from_email))


def from_for(account: str | None) -> str:
    """The verified sender address for a dispatch account, else the default."""
    attr = _ACCOUNT_FROM.get(account or "")
    return (getattr(settings, attr, "") if attr else "") or settings.sendgrid_from_email \
        or settings.sendgrid_from_insurance


def replyto_for(account: str | None, from_email: str) -> str:
    """Where replies land: the configured monitored inbox, else the from-address."""
    return (settings.sendgrid_reply_to or "").strip() or from_email


def send_with_error(to: str, subject: str, html: str, *, from_email: str | None = None,
                    reply_to: str | None = None) -> tuple[str | None, str | None]:
    """Send one HTML email via SendGrid. Returns (message_id, error_reason) — exactly
    one is non-None — so callers stay provider-agnostic (identical to resend)."""
    if not has_key():
        return None, "SendGrid isn't connected — add your API key in Setup."
    if not to:
        return None, "no recipient email"
    sender = from_email or from_for("insurance")
    if not sender:
        return None, "no SendGrid sender set — verify a domain and set the from address."
    name = settings.sender_name or ""
    personalization: dict = {"to": [{"email": to}]}
    # BCC the owner on every outbound email (blind — the recipient never sees it),
    # exactly like the Resend path, so a copy of what the customer received lands in
    # the owner's inbox. Skip if it's the recipient themselves.
    bcc = (settings.outbound_bcc or "").strip()
    if bcc and bcc.lower() != (to or "").strip().lower():
        personalization["bcc"] = [{"email": bcc}]
    payload: dict = {
        "personalizations": [personalization],
        "from": {"email": sender, **({"name": name} if name else {})},
        "subject": subject or "(no subject)",
        "content": [{"type": "text/html", "value": html or " "}],
    }
    if reply_to:
        payload["reply_to"] = {"email": reply_to}
    headers = {"Authorization": f"Bearer {(settings.sendgrid_api_key or '').strip()}",
               "Content-Type": "application/json"}
    try:
        r = httpx.post(_SEND, json=payload, headers=headers, timeout=30)
        if r.status_code >= 400:
            try:
                j = r.json()
                errs = j.get("errors") or []
                msg = (errs[0].get("message") if errs else None) or str(j)[:160]
            except Exception:
                msg = (r.text or "")[:160]
            hint = ""
            if r.status_code in (401, 403):
                hint = " (auth failed — check the API key)"
            elif "from" in (msg or "").lower() or "verif" in (msg or "").lower():
                hint = " (verify your sending domain/from address in SendGrid → Sender Authentication)"
            return None, f"SendGrid {r.status_code}: {msg}{hint}"
        # 202 Accepted, no body — the id comes back in a header.
        mid = r.headers.get("X-Message-Id") or "sendgrid-sent"
        return mid, None
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("SendGrid send failed (%s): %s", to, exc)
        return None, f"SendGrid error: {str(exc)[:160]}"


def send_email(to: str, subject: str, html: str, *, from_email: str | None = None,
               reply_to: str | None = None) -> str | None:
    """Send one HTML email via SendGrid. Returns the message id, or None on failure."""
    return send_with_error(to, subject, html, from_email=from_email, reply_to=reply_to)[0]
