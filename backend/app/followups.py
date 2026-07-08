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

from sqlalchemy import func

from . import memory, outreach
from .ai import client, skills
from .ai.prompts import FOLLOWUP_EMAIL
from .config import settings
from .models import FollowUp, Influencer, Lead, Message, MusicPlaylist, Restaurant, Task

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


def _lead_first(db: Session, lead_id):
    return db.query(Lead).filter(Lead.id == lead_id).first()


def _sms_text(name: str | None, purpose: str) -> str:
    """A short, compliant follow-up text. Uses AI when live, else a safe template —
    always identifies the producer + business (CAN-SPAM/TCPA identity) and stays
    under one segment."""
    producer = settings.producer_name
    fallback = (f"Hi {name or 'there'}, it's {producer} with Thrust Insurance — it takes "
                "2 minutes to verify a couple details and get you an accurate quote. "
                "Reply or text me the best time to talk. Reply STOP to opt out.")
    try:
        if client.is_live():
            txt = client.complete(
                f"Write ONE friendly follow-up SMS (under 300 chars) for an insurance lead "
                f"named {name or 'there'}. Goal: {purpose}. Sign as {producer} with Thrust "
                "Insurance. No placeholders. End with 'Reply STOP to opt out.'",
                system="You are a warm, compliant licensed insurance producer.")
            if txt and not txt.startswith("["):
                return txt.strip()
    except Exception:  # AI must never block the cadence
        log.debug("sequence SMS AI generation skipped", exc_info=True)
    return fallback


def process_due_followups(db: Session, limit: int = 400) -> dict:
    """Execute all due, not-yet-completed follow-ups — HOT LEADS FIRST — across every
    channel in the cadence: email (sent via the dispatcher), SMS (queued as a
    compliance-gated draft), and calls (a task in the call queue). Anyone who already
    replied is skipped and their sequence stops."""
    today = date.today()
    # Hot leads first: rank due steps by their lead's score (non-lead follow-ups
    # fall to 0 and run after). Then by due date so older touches don't starve.
    due = (db.query(FollowUp)
           .outerjoin(Lead, (FollowUp.entity_type == "lead") & (FollowUp.entity_id == Lead.id))
           .filter(FollowUp.due_date <= today, FollowUp.completed.is_(False))
           .order_by(func.coalesce(Lead.score, 0).desc(), FollowUp.due_date)
           .limit(limit).all())
    sysp = skills.system_prompt("cold-email")
    sent = texted = tasked = skipped = 0

    for fu in due:
        msgs = db.query(Message).filter(
            Message.entity_type == fu.entity_type, Message.entity_id == fu.entity_id,
        ).all()
        if any(m.status == "Replied" for m in msgs):
            fu.completed = True  # they responded — stop the whole sequence
            skipped += 1
            continue
        channel = fu.channel or "email"
        purpose = fu.body or _purpose_for(fu.step)
        name, context = _entity_context(db, fu.entity_type, fu.entity_id)

        # ── Call task: a to-do in the queue, not an auto-send (you place the call). ──
        if channel == "call" and fu.entity_type == "lead":
            lead = _lead_first(db, fu.entity_id)
            db.add(Task(status="pending",
                        summary=f"📞 Call {name or 'lead'} — {purpose[:120]}",
                        payload={"kind": "call", "lead_id": str(fu.entity_id),
                                 "phone": (lead.phone if lead else None),
                                 "purpose": purpose, "context": context}))
            fu.completed = True
            tasked += 1
            continue

        # ── SMS: queue a compliance-gated draft (sends hot-first via the SMS engine). ──
        if channel == "sms" and fu.entity_type == "lead":
            lead = _lead_first(db, fu.entity_id)
            phone = lead.phone if lead else None
            if not phone:
                fu.completed = True  # nothing to text
                continue
            text = _sms_text(name, purpose)
            db.add(Message(channel="sms", direction="outbound", entity_type="lead",
                           entity_id=fu.entity_id, to_email=phone, from_account="insurance",
                           body=text, status="Drafted"))
            fu.body = text
            fu.completed = True
            texted += 1
            continue

        # ── Email: generate + send/draft via the shared dispatcher (respects mode). ──
        to_email = next((m.to_email for m in msgs if m.to_email and "@" in (m.to_email or "")), None)
        if not to_email:
            fu.completed = True  # no address to email
            continue
        account = msgs[0].from_account if msgs else "insurance"
        memory_block = memory.entity_context(db, name=name, email=to_email)
        art = client.complete_json(
            FOLLOWUP_EMAIL.format(step=fu.step, name=name or "there", context=context,
                                  purpose=purpose, memory=memory_block),
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
            try:
                memory.add(db, f"Sent follow-up #{fu.step} about {context}"
                           + (f' — "{subject}"' if subject else ""),
                           kind="event", subject=name or to_email, source="followups")
            except Exception:  # memory must never break sending
                log.debug("follow-up memory capture skipped", exc_info=True)

    db.commit()
    log.info("Follow-ups: due=%d email=%d sms=%d calls=%d skipped_replied=%d",
             len(due), sent, texted, tasked, skipped)
    return {"due": len(due), "sent": sent, "texted": texted, "call_tasks": tasked,
            "skipped_replied": skipped}
