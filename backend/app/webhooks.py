"""Outbound webhooks — notify n8n, Make, Zapier, or any URL when key events
happen in Bruno, so custom automations can be built outside the app.

Best-effort and non-blocking by design: a broken or slow webhook must NEVER
break the action that triggered it (a new client, a reply, a logged note).
Payloads are signed with HMAC-SHA256 in an X-Bruno-Signature header when a
webhook has a secret, so the receiver can verify authenticity.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy.orm import Session

from .models import Webhook

log = logging.getLogger("bruno.webhooks")
_TIMEOUT = httpx.Timeout(6.0, connect=3.0)

# Events other modules can fire. Kept as a curated, documented set (not
# free-text) so the webhook UI can offer a clear picklist.
EVENTS: list[dict] = [
    {"key": "client.created", "label": "New client added to the Client Book"},
    {"key": "client.note_added", "label": "Communication logged on a client (call/SMS/WhatsApp/email/meeting)"},
    {"key": "lead.replied", "label": "A prospect replied to outreach"},
]
EVENT_KEYS = {e["key"] for e in EVENTS}


def _sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def dispatch(db: Session, event: str, data: dict) -> None:
    """Fire `event` to every enabled webhook subscribed to it (or to '*').
    Never raises — a broken webhook must not break the caller."""
    try:
        hooks = db.query(Webhook).filter(Webhook.enabled.is_(True)).all()
    except Exception:  # pragma: no cover - defensive
        return
    if not hooks:
        return
    payload = {"event": event, "data": data,
               "sent_at": datetime.now(timezone.utc).isoformat()}
    body = json.dumps(payload, default=str).encode()
    fired = False
    for hook in hooks:
        events = hook.events or []
        if "*" not in events and event not in events:
            continue
        fired = True
        headers = {"Content-Type": "application/json"}
        if hook.secret:
            headers["X-Bruno-Signature"] = _sign(hook.secret, body)
        try:
            r = httpx.post(hook.url, content=body, headers=headers, timeout=_TIMEOUT)
            hook.last_status = str(r.status_code)
        except Exception as exc:  # pragma: no cover - network guard
            hook.last_status = f"error: {str(exc)[:100]}"
            log.warning("Webhook '%s' (%s) failed: %s", hook.name, event, exc)
        hook.last_triggered_at = datetime.now(timezone.utc)
    if fired:
        try:
            db.commit()
        except Exception:  # pragma: no cover - defensive
            db.rollback()
