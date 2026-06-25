"""Referral engine — turn warm relationships into warm leads.

Your warmest insurance leads come from people who already trust you. This asks
engaged contacts (those who replied / are interested / closed won) for referrals
— a short, warm note from the Thrust mailbox (with your booking link in the
footer when calendar_link is set). Each lead is asked once (deduped by the
referral subject); referred names come back as email replies in your inbox.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from . import outreach
from .ai import client
from .config import settings
from .models import Lead, Message

log = logging.getLogger("bruno.referrals")

_SUBJECT = "A quick favor"  # fixed prefix → reliable one-ask-per-lead dedupe
# Engaged statuses worth asking for a referral (warm signal already shown).
_WARM = ("Replied", "Interested", "Follow-up Needed", "Closed Won")


def _already_asked(db: Session, lead_id) -> bool:
    return db.query(Message).filter(
        Message.entity_type == "lead", Message.entity_id == lead_id,
        Message.subject.like(f"{_SUBJECT}%")).first() is not None


def _fallback(first: str) -> str:
    return (f"Hi {first},\n\nThank you for trusting me with your insurance — it genuinely means a "
            "lot. Most of my best clients come by referral, so I wanted to ask: do you know anyone "
            "— a friend, family member, or business owner — who could use a fresh, no-pressure look "
            "at their coverage? I'd be glad to give them the same care I've given you.\n\n"
            "Just reply with a name or a quick intro and I'll take it from there.\n\nThank you!\nBruno")


def _body(first: str, company: str | None) -> str:
    if not client.is_live():
        return _fallback(first)
    prompt = (f"Write a SHORT, warm referral-request email from Bruno Dos Santos (Thrust Insurance) "
              f"to {first}, an engaged insurance client/prospect. Thank them, note most of your best "
              "clients come from referrals, and ask if they know anyone (friends, family, business "
              "owners) who could use a free coverage review. Friendly, brief, no hype. "
              'Return JSON: {"body": "..."}.')
    out = client.complete_json(prompt, system="You output only valid JSON.")
    if isinstance(out, dict) and out.get("body"):
        return out["body"]
    return _fallback(first)


def run(db: Session, limit: int = 20) -> dict:
    """Ask the next batch of engaged insurance leads for referrals (once each)."""
    leads = (db.query(Lead).filter(
        Lead.segment.in_(["commercial", "personal"]),
        Lead.status.in_(_WARM),
        Lead.email.isnot(None)).limit(200).all())
    asked = 0
    for lead in leads:
        if asked >= limit:
            break
        if not outreach.is_real_email(lead.email) or _already_asked(db, lead.id):
            continue
        first = (lead.owner_name or "there").split()[0]
        msg = outreach.dispatch_email(
            db, entity_type="lead", entity_id=lead.id, to_email=lead.email,
            subject=f"{_SUBJECT}, {first}", body=_body(first, lead.company_name),
            account="insurance", actor="referrals")
        if msg.status in ("Sent", "Drafted"):
            asked += 1
    return {"candidates": len(leads), "asked": asked}
