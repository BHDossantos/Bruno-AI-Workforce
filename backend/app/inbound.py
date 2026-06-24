"""Inbound email sync.

Reads recent replies from both Gmail accounts (personal + insurance) and marks
the matching lead / restaurant / message as ``Replied``. This is the foundation
for Phase 3 reply classification; for now it does sender-address matching.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from . import classify, sms_engine
from .integrations import gmail
from .models import ActionLog, Lead, Message, Restaurant

_TERMINAL = ("Interested", "Closed Won", "Closed Lost")

log = logging.getLogger("bruno.inbound")
ACCOUNTS = [gmail.PERSONAL, gmail.INSURANCE]


def _draft_reply(db: Session, sender: str, reply: dict, cls: dict, account: str) -> None:
    """Generate a concise reply with AI and save it as a draft for one-click send."""
    from . import outreach
    from .ai import client, skills
    body = client.complete(
        f"A prospect ({sender}) replied to our outreach. Their message:\n"
        f"\"{reply.get('snippet', '')}\"\n\nIntent: {cls.get('intent')}.\n"
        "Write a short, warm, helpful reply (max 120 words) that moves toward a call. "
        "No subject line, no placeholders.",
        system=skills.system_prompt("cold-email"))
    if not body or body.startswith("["):
        return  # offline stub — skip
    outreach.dispatch_email(db, entity_type="reply", entity_id=None, to_email=sender,
                            subject=f"Re: {reply.get('subject') or 'your note'}",
                            body=body, account=account, actor="inbound", force_draft=True)


def sync_replies(db: Session, newer_than_days: int = 3) -> dict:
    matched = 0
    scanned = 0
    for account in ACCOUNTS:
        if not gmail.is_configured(account):
            continue
        for reply in gmail.list_replies(newer_than_days=newer_than_days, account=account):
            scanned += 1
            sender = reply.get("from_email")
            if not sender:
                continue
            hit = False
            cls = classify.classify_reply(reply.get("snippet", ""))

            for lead in db.query(Lead).filter(Lead.email == sender).all():
                if lead.status not in _TERMINAL:
                    lead.status = cls["status"]
                # Warm → auto-text from the insurance number.
                sms_engine.maybe_warm_text(
                    db, entity_type="lead", entity_id=lead.id,
                    name=lead.company_name or lead.owner_name, phone=lead.phone,
                    context=lead.reason or "insurance", account="insurance")
                hit = True
            for rest in db.query(Restaurant).filter(Restaurant.email == sender).all():
                if rest.status not in _TERMINAL:
                    rest.status = cls["status"]
                sms_engine.maybe_warm_text(
                    db, entity_type="restaurant", entity_id=rest.id, name=rest.name,
                    phone=rest.phone, context=rest.pain_points or "SavoryMind", account="personal")
                hit = True
            for msg in db.query(Message).filter(Message.to_email == sender).all():
                msg.status = "Replied"
                hit = True

            if hit:
                matched += 1
                db.add(ActionLog(actor="inbound", action="reply_classified", entity="email",
                                 entity_id=sender, detail={"account": account, "intent": cls["intent"],
                                                           "summary": cls["summary"],
                                                           "subject": reply.get("subject")}))
                # Remember the interaction in the knowledge graph.
                try:
                    from . import memory
                    memory.add(db, f"{sender} replied ({cls['intent']}): {cls.get('summary') or reply.get('snippet','')}",
                               kind="event", subject=sender, source="inbound")
                except Exception:  # never let memory break the sync
                    log.debug("memory capture skipped", exc_info=True)

                # AI-draft a reply (kept as a draft for one-click review/send).
                try:
                    _draft_reply(db, sender, reply, cls, account)
                except Exception:
                    log.debug("reply draft skipped", exc_info=True)

    db.commit()
    log.info("Inbound sync: scanned %d, matched %d", scanned, matched)
    return {"scanned": scanned, "matched": matched}
