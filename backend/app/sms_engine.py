"""SMS conversation engine: warm-intro auto-texts + thread storage.

A lead becomes *warm* when they reply to our email (set by inbound email sync).
At that point, if they have a phone and Twilio is configured, we auto-send one
friendly intro text and start a two-way thread that the user continues from the
dashboard. SMS are stored as ``Message`` rows with ``channel='sms'`` and the
contact's phone in ``to_email`` (the thread key).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from .ai import client, skills
from .ai.prompts import SMS_INTRO
from .config import settings
from .integrations import sms
from .models import Message

log = logging.getLogger("bruno.sms_engine")


def _has_prior_sms(db: Session, phone: str) -> bool:
    return db.query(Message).filter(
        Message.channel == "sms", Message.to_email == phone,
    ).first() is not None


def maybe_warm_text(db: Session, *, entity_type: str, entity_id, name: str | None,
                    phone: str | None, context: str, account: str) -> str | None:
    """Auto-send one warm intro SMS to a freshly-warm lead. Returns the SID or None."""
    if not settings.sms_auto_on_reply or not phone or not sms.is_configured():
        return None
    if _has_prior_sms(db, phone):
        return None  # already in an SMS conversation

    art = client.complete_json(
        SMS_INTRO.format(name=name or "there", context=context or "your inquiry"),
        system=skills.system_prompt("sms"))
    body = (art.get("body") if isinstance(art, dict) else None) or (
        f"Hi {name or 'there'}, thanks for getting back to us! Happy to help — "
        f"what's the best way to move forward? Reply STOP to opt out.")

    sid = sms.send_sms(phone, body, account=account)
    db.add(Message(
        channel="sms", direction="outbound", entity_type=entity_type, entity_id=entity_id,
        to_email=phone, from_account=account, body=body,
        status="Sent" if sid else "Drafted", provider_id=sid,
        sent_at=datetime.now(timezone.utc) if sid else None,
    ))
    log.info("Warm SMS to %s (%s): %s", phone, account, "sent" if sid else "stored")
    return sid


def record_inbound(db: Session, *, phone: str, body: str) -> Message:
    """Store an inbound SMS and link it to a known contact by phone."""
    from .models import Lead, Restaurant

    msg = Message(channel="sms", direction="inbound", to_email=phone, body=body, status="Replied")
    # Best-effort link + mark the contact engaged.
    for model, etype in ((Lead, "lead"), (Restaurant, "restaurant")):
        row = db.query(model).filter(model.phone == phone).first()
        if row:
            msg.entity_type, msg.entity_id = etype, row.id
            if row.status not in ("Interested", "Closed Won", "Closed Lost"):
                row.status = "Interested"
            break
    db.add(msg)
    db.commit()
    return msg
