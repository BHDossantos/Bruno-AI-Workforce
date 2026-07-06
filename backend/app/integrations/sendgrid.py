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


# dispatch account → its verified SendGrid sender.
_ACCOUNT_FROM = {
    "insurance": "sendgrid_from_insurance",
    "bnb": "sendgrid_from_bnb",
    "savorymind": "sendgrid_from_savorymind",
}


_ACCOUNT_REPLYTO = {
    "insurance": "sendgrid_replyto_insurance",
    "bnb": "sendgrid_replyto_bnb",
    "savorymind": "sendgrid_replyto_savorymind",
}


def from_for(account: str | None) -> str:
    """The verified sender address for a dispatch account, else the default."""
    attr = _ACCOUNT_FROM.get(account or "")
    return (getattr(settings, attr, "") if attr else "") or settings.sendgrid_from_email


def replyto_for(account: str | None, from_email: str) -> str:
    """The Reply-To for a dispatch account: configured override, else the from."""
    attr = _ACCOUNT_REPLYTO.get(account or "")
    return (getattr(settings, attr, "") if attr else "") or from_email


def is_configured() -> bool:
    """Configured if we have a key AND at least one verified sender to send from."""
    return bool(settings.sendgrid_api_key and (
        settings.sendgrid_from_email or settings.sendgrid_from_insurance
        or settings.sendgrid_from_bnb or settings.sendgrid_from_savorymind))


def has_key() -> bool:
    return bool(settings.sendgrid_api_key)


def _headers() -> dict:
    return {"Authorization": f"Bearer {settings.sendgrid_api_key}",
            "Content-Type": "application/json"}


def send_email(to: str, subject: str, html: str, *, from_email: str | None = None,
               reply_to: str | None = None) -> str | None:
    """Send one HTML email via SendGrid from a verified sender. Returns a message id."""
    if not settings.sendgrid_api_key or not to:
        return None
    sender = from_email or settings.sendgrid_from_email
    if not sender:
        return None  # no verified sender to send from
    payload: dict = {
        "personalizations": [{"to": [{"email": to}], "subject": subject or "(no subject)"}],
        "from": {"email": sender, "name": settings.sender_name or sender},
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


def send_with_error(to: str, subject: str, html: str, *, from_email: str | None = None,
                    reply_to: str | None = None) -> tuple[str | None, str | None]:
    """Like send_email but returns (message_id, error_reason) so callers can
    surface exactly why a send failed instead of silently swallowing it."""
    if not settings.sendgrid_api_key:
        return None, "SendGrid API key not set"
    if not to:
        return None, "no recipient"
    sender = from_email or settings.sendgrid_from_email
    if not sender:
        return None, "no verified SendGrid sender configured"
    payload: dict = {
        "personalizations": [{"to": [{"email": to}], "subject": subject or "(no subject)"}],
        "from": {"email": sender, "name": settings.sender_name or sender},
        "content": [{"type": "text/html", "value": html or ""}],
    }
    if reply_to:
        payload["reply_to"] = {"email": reply_to}
    try:
        r = httpx.post(_SEND, json=payload, headers=_headers(), timeout=30)
        if r.status_code >= 400:
            detail = ""
            try:
                errs = (r.json() or {}).get("errors") or []
                detail = "; ".join(e.get("message", "") for e in errs if e.get("message"))
            except Exception:
                detail = (r.text or "")[:200]
            return None, f"SendGrid {r.status_code}: {detail or 'send rejected'}"
        return r.headers.get("X-Message-Id") or "sendgrid", None
    except Exception as exc:  # pragma: no cover - network guard
        return None, f"SendGrid error: {str(exc)[:160]}"


_GLOBAL_STATS = "https://api.sendgrid.com/v3/stats"

# The metrics we surface, in display order, with friendly labels.
_STAT_FIELDS = ["requests", "delivered", "opens", "unique_opens", "clicks",
                "unique_clicks", "bounces", "blocks", "spam_reports", "unsubscribes"]


def stats(days: int = 7) -> dict:
    """Pull real delivery stats from SendGrid (delivered / opens / bounces / …)
    for the last ``days`` days, aggregated. Returns totals + computed rates + a
    per-day series, or {ok: False, reason} when the key can't read stats.

    Uses the global Stats API (/v3/stats), which needs a key with the 'Stats'
    permission — a Mail-Send-only key returns 401/403, surfaced as a clear reason.
    """
    from datetime import date, timedelta
    if not has_key():
        return {"ok": False, "reason": "SendGrid not connected"}
    days = max(1, min(int(days or 7), 90))
    start = (date.today() - timedelta(days=days - 1)).isoformat()
    try:
        r = httpx.get(_GLOBAL_STATS, headers=_headers(), timeout=30,
                      params={"start_date": start, "aggregated_by": "day"})
        if r.status_code in (401, 403):
            return {"ok": False, "reason": "This API key can't read stats — create a "
                    "key with the 'Stats' permission (or Full Access) in SendGrid."}
        r.raise_for_status()
        data = r.json() or []
    except Exception as exc:  # pragma: no cover - network guard
        return {"ok": False, "reason": str(exc)[:120]}

    totals = {f: 0 for f in _STAT_FIELDS}
    series = []
    for day in data:
        day_metrics = {f: 0 for f in _STAT_FIELDS}
        for s in (day.get("stats") or []):
            m = s.get("metrics") or {}
            for f in _STAT_FIELDS:
                day_metrics[f] += int(m.get(f, 0) or 0)
        for f in _STAT_FIELDS:
            totals[f] += day_metrics[f]
        series.append({"date": day.get("date"), **day_metrics})

    sent = totals["requests"] or totals["delivered"]

    def _rate(n):
        return round(100 * n / sent, 1) if sent else 0.0

    return {
        "ok": True, "days": days, "start_date": start,
        "totals": totals, "series": series,
        "delivered_rate": _rate(totals["delivered"]),
        "open_rate": _rate(totals["unique_opens"]),
        "bounce_rate": _rate(totals["bounces"]),
        "spam_rate": _rate(totals["spam_reports"]),
    }


def verify() -> dict:
    """Check the API key is valid. Uses /v3/scopes, which works even for a
    restricted 'Mail Send' key (unlike /verified_senders, which needs broader
    access) — so a correctly-scoped send key still shows green."""
    if not has_key():
        return {"ok": False, "reason": "no API key"}
    try:
        r = httpx.get("https://api.sendgrid.com/v3/scopes", headers=_headers(), timeout=20)
        if r.status_code == 401:
            return {"ok": False, "reason": "API key rejected (401) — check the key."}
        r.raise_for_status()
        scopes = (r.json() or {}).get("scopes", []) if r.headers.get("content-type", "").startswith("application/json") else []
        if scopes and not any("mail.send" in s for s in scopes):
            return {"ok": False, "reason": "Key is missing the 'Mail Send' permission."}
        return {"ok": True, "reason": None}
    except Exception as exc:  # pragma: no cover - network guard
        return {"ok": False, "reason": f"{str(exc)[:100]}"}
