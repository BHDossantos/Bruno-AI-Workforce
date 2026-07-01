"""Booking nudge — re-engage interested leads who never booked.

The follow-up sequence STOPS the moment a prospect replies, which is correct for
cold cadence but leaves a gap: someone who said "yes, interested" and got a reply
draft, then went quiet, gets nothing. These are the hottest, closest-to-revenue
contacts. This pass finds interested-but-not-booked leads/restaurants and sends
ONE gentle, booking-focused nudge (with the business's booking link woven in),
exactly once, a couple of days after the last touch.

Auto-send follows the same rule as the follow-up engine: it goes through
outreach.dispatch_email, so it respects Outreach Autopilot, the daily cap, the
paused state and the real-email guard.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from . import email_template, outreach
from .integrations import gmail
from .models import ActionLog, Lead, Restaurant

log = logging.getLogger("bruno.booking_nudge")

_ACTION = "booking_nudge"
_MIN_AGE_DAYS = 2      # wait this long after the last touch before nudging
_PER_RUN_CAP = 50


def _already_nudged(db: Session, entity_type: str, entity_id) -> bool:
    return db.query(ActionLog.id).filter(
        ActionLog.action == _ACTION, ActionLog.entity == entity_type,
        ActionLog.entity_id == str(entity_id)).first() is not None


def _nudge_body(name: str | None, context: str, booking_link: str) -> str | None:
    """A short, warm nudge that points to the calendar. AI-written, else a clean
    fallback so the nudge still sends offline."""
    from .ai import client, skills
    ask = (f"Include this booking link and invite them to grab a time: {booking_link}"
           if booking_link else "Invite them to reply with a couple of times that work.")
    body = client.complete(
        f"A prospect ({name or 'there'}) told us they were interested in {context} but "
        "hasn't booked a call yet. Write a very short (max 70 words), warm, no-pressure "
        f"nudge to get a quick call on the calendar. {ask} No subject line, no placeholders.",
        system=skills.system_prompt("cold-email"))
    if not body or body.startswith("["):
        # Offline / no AI key — a clean, sendable fallback.
        first = (name or "there").split()[0]
        return (f"Hi {first}, following up on your interest in {context} — "
                "I'd love to find 15 minutes to see if we can help. "
                + ("Grab whatever time works for you here and I'll take care of the rest."
                   if booking_link else "Reply with a couple of times that work and I'll send an invite."))
    return body


def _nudge(db: Session, *, entity_type: str, entity_id, name: str | None,
           email: str, context: str, account: str) -> bool:
    link = email_template.booking_link(account)
    body = _nudge_body(name, context, link)
    subject = f"Grabbing 15 minutes, {(name or 'there').split()[0]}?"
    msg = outreach.dispatch_email(
        db, entity_type=entity_type, entity_id=entity_id, to_email=email,
        subject=subject, body=body, account=account, actor="booking_nudge")
    # Record the nudge regardless of send outcome so we never nudge twice.
    db.add(ActionLog(actor="booking_nudge", action=_ACTION, entity=entity_type,
                     entity_id=str(entity_id), detail={"sent": msg.status == "Sent"}))
    return msg.status == "Sent"


def run(db: Session, limit: int = _PER_RUN_CAP) -> dict:
    """Send one booking nudge to each interested-but-not-booked prospect."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=_MIN_AGE_DAYS)
    sent = eligible = 0

    leads = (db.query(Lead).filter(
        Lead.status == "Interested", Lead.email.isnot(None),
        Lead.last_contacted_at.isnot(None), Lead.last_contacted_at <= cutoff)
        .limit(limit).all())
    for lead in leads:
        if _already_nudged(db, "lead", lead.id) or not outreach.is_real_email(lead.email):
            continue
        eligible += 1
        if _nudge(db, entity_type="lead", entity_id=lead.id,
                  name=lead.company_name or lead.owner_name, email=lead.email,
                  context=lead.reason or "insurance",
                  account=gmail.account_for_segment(lead.segment)):
            sent += 1

    rests = (db.query(Restaurant).filter(
        Restaurant.status == "Interested", Restaurant.email.isnot(None),
        Restaurant.last_contacted_at.isnot(None), Restaurant.last_contacted_at <= cutoff)
        .limit(limit).all())
    for r in rests:
        if _already_nudged(db, "restaurant", r.id) or not outreach.is_real_email(r.email):
            continue
        eligible += 1
        if _nudge(db, entity_type="restaurant", entity_id=r.id, name=r.name, email=r.email,
                  context=r.pain_points or "SavoryMind", account=gmail.restaurant_account()):
            sent += 1

    db.commit()
    log.info("Booking nudges: eligible=%d sent=%d", eligible, sent)
    return {"eligible": eligible, "sent": sent}
