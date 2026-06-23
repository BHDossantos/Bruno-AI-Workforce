"""Automated follow-up engine.

Processes follow-up steps whose due date has arrived, generating a short AI
follow-up (using the cold-email skill) and sending it via the same account/
recipient as the original outreach. Anyone who already replied is skipped.
Works for every outreach type (leads, restaurants, playlists, influencers, jobs)
because it reuses the first-touch ``Message`` to find the recipient + account.
"""
from __future__ import annotations

import logging
from datetime import date

from sqlalchemy.orm import Session

from . import outreach
from .ai import client, skills
from .ai.prompts import FOLLOWUP_EMAIL
from .models import FollowUp, Influencer, Lead, Message, MusicPlaylist, Restaurant

log = logging.getLogger("bruno.followups")


def _entity_context(db: Session, etype: str, eid) -> tuple[str | None, str]:
    if etype == "lead":
        e = db.query(Lead).filter(Lead.id == eid).first()
        if e:
            return (e.company_name or e.owner_name), (e.reason or "insurance outreach")
    elif etype == "restaurant":
        e = db.query(Restaurant).filter(Restaurant.id == eid).first()
        if e:
            return e.name, (e.pain_points or "SavoryMind restaurant pitch")
    elif etype == "playlist":
        e = db.query(MusicPlaylist).filter(MusicPlaylist.id == eid).first()
        if e:
            return e.name, f"music playlist submission ({e.genre})"
    elif etype == "influencer":
        e = db.query(Influencer).filter(Influencer.id == eid).first()
        if e:
            return e.name, f"{e.niche} influencer collaboration"
    elif etype == "job":
        return None, "executive role application / hiring-manager outreach"
    return None, "previous outreach"


def process_due_followups(db: Session, limit: int = 400) -> dict:
    """Send all due, not-yet-completed follow-ups. Returns a summary."""
    today = date.today()
    due = (db.query(FollowUp)
           .filter(FollowUp.due_date <= today, FollowUp.completed.is_(False))
           .order_by(FollowUp.due_date)
           .limit(limit).all())
    sysp = skills.system_prompt("cold-email")
    sent = skipped = 0

    for fu in due:
        msgs = db.query(Message).filter(
            Message.entity_type == fu.entity_type, Message.entity_id == fu.entity_id,
        ).all()
        to_email = next((m.to_email for m in msgs if m.to_email), None)
        if not msgs or not to_email:
            fu.completed = True  # no one to follow up with
            continue
        if any(m.status == "Replied" for m in msgs):
            fu.completed = True  # they responded — stop the sequence
            skipped += 1
            continue

        account = msgs[0].from_account
        name, context = _entity_context(db, fu.entity_type, fu.entity_id)
        art = client.complete_json(
            FOLLOWUP_EMAIL.format(step=fu.step, name=name or "there", context=context),
            system=sysp)
        subject = (art.get("subject") if isinstance(art, dict) else None) or f"Following up ({fu.step})"
        body = art.get("body") if isinstance(art, dict) else None

        msg = outreach.dispatch_email(
            db, entity_type=fu.entity_type, entity_id=fu.entity_id, to_email=to_email,
            subject=subject, body=body, account=account, actor="followups")
        fu.body = body
        fu.completed = True
        if msg.status == "Sent":
            sent += 1

    db.commit()
    log.info("Follow-ups: due=%d sent=%d skipped_replied=%d", len(due), sent, skipped)
    return {"due": len(due), "sent": sent, "skipped_replied": skipped}
