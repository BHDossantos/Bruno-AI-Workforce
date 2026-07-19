"""SMS follow-up — text leads who were emailed but never replied.

A second, higher-response channel: a lead that got a cold email but hasn't
responded after a couple of days gets ONE short, compliant text nudge. Every
send goes through sms_engine.send_text, which enforces the compliance gate
(opt-out/DNC, TCPA contact hours, the daily SMS cap) — so this can't text
someone who opted out or blow past the cap. Hottest leads first.

OFF by default (needs A2P 10DLC registration before texting at volume); the
scheduler only runs it when ``sms_followup_enabled`` is on, but the manual
'Text non-repliers' action runs on demand.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, exists
from sqlalchemy.orm import Session

from .config import settings
from .models import Lead, Message

log = logging.getLogger("bruno.sms_followups")


def is_enabled() -> bool:
    """Tolerant truthiness — the flag may arrive as a real bool (default) or a
    string ('true'/'1'/'on') when set through the in-app runtime config."""
    v = settings.sms_followup_enabled
    return v is True or str(v).strip().lower() in ("1", "true", "yes", "on")


def _delay_days() -> int:
    try:
        return max(0, int(settings.sms_followup_delay_days or 2))
    except (TypeError, ValueError):
        return 2


def _text_for(lead: Lead) -> str:
    first = ((lead.owner_name or "").split() or ["there"])[0]
    biz = settings.insurance_business_name or "Thrust Insurance"
    return (f"Hi {first}, it's {settings.producer_name} with {biz}. I emailed you about your "
            "insurance quote — happy to run the numbers whenever works for you. "
            "Reply STOP to opt out.")


def run(db: Session, limit: int | None = None) -> dict:
    """Send the follow-up text to eligible leads (emailed >= delay days ago, no reply,
    not yet texted), hottest first, within today's remaining SMS cap headroom."""
    from . import lead_temperature, sms_engine

    cutoff = datetime.now(timezone.utc) - timedelta(days=_delay_days())
    emailed = exists().where(and_(
        Message.entity_type == "lead", Message.entity_id == Lead.id,
        Message.channel == "email", Message.direction == "outbound",
        Message.status == "Sent", Message.sent_at <= cutoff))
    texted = exists().where(and_(
        Message.entity_type == "lead", Message.entity_id == Lead.id,
        Message.channel == "sms", Message.direction == "outbound"))
    replied = exists().where(and_(
        Message.entity_type == "lead", Message.entity_id == Lead.id,
        Message.direction == "inbound"))

    # Only work as many as today's remaining SMS headroom (the cap is global).
    headroom = max(0, settings.sms_daily_send_cap - sms_engine.sms_sent_today(db))
    if headroom <= 0:
        return {"eligible": 0, "sent": 0, "skipped": 0, "capped": True}

    rows = (db.query(Lead)
            .filter(Lead.phone.isnot(None), Lead.phone != "", emailed, ~texted, ~replied)
            .order_by(*lead_temperature.dispatch_order(Lead))
            .limit(min(limit or headroom, headroom)).all())

    sent = skipped = 0
    for lead in rows:
        sid = sms_engine.send_text(db, entity_type="lead", entity_id=lead.id,
                                   phone=lead.phone, body=_text_for(lead), account="insurance")
        if sid:
            sent += 1
        else:
            skipped += 1  # opted out / outside hours / cap hit / no SMS provider
    log.info("SMS follow-up: %d eligible, %d sent, %d skipped", len(rows), sent, skipped)
    return {"eligible": len(rows), "sent": sent, "skipped": skipped}
