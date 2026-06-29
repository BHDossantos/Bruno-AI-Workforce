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

from . import memory, outreach
from .ai import client, skills
from .ai.prompts import FOLLOWUP_EMAIL
from .models import FollowUp, Influencer, Lead, Message, MusicPlaylist, Restaurant

log = logging.getLogger("bruno.followups")

# A proven multi-touch cadence: every touch has a DISTINCT job, so the sequence
# adds value instead of nagging. Steps map to base.FOLLOW_UP_OFFSETS (1–7).
_STEP_PURPOSE = {
    1: "Share one concrete, useful insight or quick win relevant to their world — "
       "give value first, ask for nothing big.",
    2: "Offer social proof: a brief, specific result or example of someone like them "
       "who benefited (no name-dropping fluff, a real outcome).",
    3: "Reframe from a DIFFERENT angle or pain point than before — maybe the prior "
       "angle wasn't their priority; try another concrete problem you solve.",
    4: "Share a helpful resource (a short guide, checklist, or data point) with no "
       "strings attached — pure goodwill.",
    5: "A light, human check-in on timing — ask if this is even a priority right now, "
       "make it easy to say 'not now'.",
    6: "Create gentle, honest urgency or a clear next step (a 15-min call, a quick "
       "yes/no) — still respectful, no fake scarcity.",
    7: "BREAKUP email: this is your last note. Say you'll close their file for now, "
       "keep the door open ('reply anytime and I'll pick it back up'). Often the "
       "highest-replying touch — make it warm and zero-pressure.",
}


def _purpose_for(step: int) -> str:
    return _STEP_PURPOSE.get(step, _STEP_PURPOSE[7])  # beyond the map → breakup tone


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
        # Recall what we know about them so the follow-up is personal + well-timed.
        memory_block = memory.entity_context(db, name=name, email=to_email)
        art = client.complete_json(
            FOLLOWUP_EMAIL.format(step=fu.step, name=name or "there", context=context,
                                  purpose=_purpose_for(fu.step), memory=memory_block),
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
            # Remember the touch so the next follow-up never repeats it.
            try:
                memory.add(db, f"Sent follow-up #{fu.step} about {context}"
                           + (f' — "{subject}"' if subject else ""),
                           kind="event", subject=name or to_email, source="followups")
            except Exception:  # memory must never break sending
                log.debug("follow-up memory capture skipped", exc_info=True)

    db.commit()
    log.info("Follow-ups: due=%d sent=%d skipped_replied=%d", len(due), sent, skipped)
    return {"due": len(due), "sent": sent, "skipped_replied": skipped}
