"""Resend webhook — makes email two-way.

Point Resend's webhook (and, once you enable inbound receiving, its inbound
route) at ``POST /resend/inbound``. It handles both kinds of Resend event on the
one public endpoint:

* **Inbound reply received** → classify it, link it to the lead/restaurant it came
  from, advance their status, opt them into the funnel newsletter, AI-draft a
  one-click reply, and save the email onto the contact's CRM thread. This is what
  makes replies to your outreach flow back into the app automatically.
* **Delivery events** (delivered / bounced / complained / opened …) → record the
  real outcome on the matching sent Message so the UI shows whether it landed.

Signature: if ``resend_webhook_secret`` ("whsec_…") is set, every post is
Svix-verified and rejected on mismatch; if it's blank the endpoint accepts posts
unauthenticated, exactly like the Twilio/Plivo inbound webhooks.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import re

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import Message

router = APIRouter(tags=["resend"])
log = logging.getLogger("bruno.resend_webhook")

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")

# Resend delivery event type -> the delivery_status we record on the Message.
_DELIVERY = {
    "email.delivered": "delivered",
    "email.bounced": "bounced",
    "email.complained": "complained",
    "email.delivery_delayed": "delayed",
    "email.opened": "opened",
    "email.clicked": "clicked",
    "email.sent": "sent",
}


def _extract_email(value) -> str | None:
    """Pull a bare address out of ``from``, which Resend may send as a plain
    string, ``"Name <email>"``, a ``{email, name}`` object, or a 1-element list."""
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, dict):
        value = value.get("email") or value.get("address") or value.get("from")
    if not isinstance(value, str):
        return None
    m = _EMAIL_RE.search(value)
    return m.group(0).lower() if m else None


def _verify_svix(secret: str, headers, raw: bytes) -> bool:
    """Verify a Svix-signed webhook (Resend uses Svix). Signed content is
    ``{id}.{timestamp}.{body}`` HMAC-SHA256'd with the base64 secret; the header
    carries one or more space-separated ``v1,<sig>`` entries."""
    sig_header = headers.get("svix-signature") or headers.get("webhook-signature")
    svix_id = headers.get("svix-id") or headers.get("webhook-id")
    ts = headers.get("svix-timestamp") or headers.get("webhook-timestamp")
    if not (sig_header and svix_id and ts):
        return False
    try:
        key = base64.b64decode(secret.split("_", 1)[1] if secret.startswith("whsec_") else secret)
        signed = f"{svix_id}.{ts}.".encode() + raw
        expected = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()
    except Exception:
        return False
    for part in sig_header.split():
        _, _, sig = part.partition(",")
        if sig and hmac.compare_digest(sig, expected):
            return True
    return False


@router.post("/resend/inbound")
async def resend_inbound(request: Request, db: Session = Depends(get_db)):
    """Public Resend webhook. Records inbound replies onto the CRM and delivery
    outcomes onto sent messages. Always returns 200 (except a real signature
    failure) so Resend doesn't retry-storm on a benign parse miss."""
    raw = await request.body()
    secret = (settings.resend_webhook_secret or "").strip()
    if secret and not _verify_svix(secret, request.headers, raw):
        return {"ok": False, "error": "signature verification failed"}

    try:
        payload = await request.json()
    except Exception:
        return {"ok": False, "error": "invalid JSON"}
    if not isinstance(payload, dict):
        return {"ok": False, "error": "unexpected payload"}

    etype = (payload.get("type") or payload.get("event") or "").lower()
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload

    # 1) Delivery / engagement event on a message we sent → record the outcome.
    if etype in _DELIVERY:
        email_id = data.get("email_id") or data.get("id")
        if email_id:
            msg = (db.query(Message).filter(Message.provider_id == email_id,
                                             Message.channel == "email").first())
            if msg:
                msg.delivery_status = _DELIVERY[etype]
                db.commit()
        return {"ok": True, "handled": etype}

    # 2) Inbound reply received → run the full two-way pipeline.
    is_inbound = ("inbound" in etype or "received" in etype
                  or (not etype and (data.get("text") or data.get("html"))))
    if is_inbound:
        sender = _extract_email(data.get("from") or data.get("sender"))
        if not sender:
            return {"ok": False, "error": "no sender address"}
        subject = data.get("subject") or ""
        snippet = (data.get("text") or data.get("snippet")
                   or _strip_html(data.get("html") or "")).strip()
        # Route to the account the reply was addressed to (insurance by default).
        to_addr = _extract_email(data.get("to")) or ""
        account = "insurance" if (not to_addr or to_addr == (settings.resend_from_insurance or "").lower()
                                  or "insurance" in to_addr or "dossantos" in to_addr) else "personal"
        try:
            from .. import inbound, runtime_config
            runtime_config.apply_to_settings(db)
            res = inbound.process_reply(db, sender=sender, subject=subject, snippet=snippet,
                                        account=account, store_message=True)
            db.commit()
            return {"ok": True, "handled": "inbound", "matched": res["hit"],
                    "intent": res["cls"].get("intent")}
        except Exception as exc:  # never 500 back at Resend — it'll just retry forever
            db.rollback()
            log.warning("Resend inbound processing failed (%s): %s", sender, exc)
            return {"ok": False, "error": "processing error"}

    # Unknown / ignored event type (e.g. contact.* events) — acknowledge quietly.
    return {"ok": True, "handled": None, "type": etype or None}


def _strip_html(html: str) -> str:
    """Crude HTML→text so an HTML-only inbound email still gets a readable body
    for classification and the CRM thread."""
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html or "", flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()
