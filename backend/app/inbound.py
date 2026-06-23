"""Inbound email sync.

Reads recent replies from both Gmail accounts (personal + insurance) and marks
the matching lead / restaurant / message as ``Replied``. This is the foundation
for Phase 3 reply classification; for now it does sender-address matching.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from . import sms_engine
from .integrations import gmail
from .models import ActionLog, Lead, Message, Restaurant

log = logging.getLogger("bruno.inbound")
ACCOUNTS = [gmail.PERSONAL, gmail.INSURANCE]


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

            for lead in db.query(Lead).filter(Lead.email == sender).all():
                if lead.status not in ("Replied", "Interested", "Closed Won", "Closed Lost"):
                    lead.status = "Replied"
                # Warm → auto-text from the insurance number.
                sms_engine.maybe_warm_text(
                    db, entity_type="lead", entity_id=lead.id,
                    name=lead.company_name or lead.owner_name, phone=lead.phone,
                    context=lead.reason or "insurance", account="insurance")
                hit = True
            for rest in db.query(Restaurant).filter(Restaurant.email == sender).all():
                if rest.status not in ("Replied", "Interested", "Closed Won", "Closed Lost"):
                    rest.status = "Replied"
                sms_engine.maybe_warm_text(
                    db, entity_type="restaurant", entity_id=rest.id, name=rest.name,
                    phone=rest.phone, context=rest.pain_points or "SavoryMind", account="personal")
                hit = True
            for msg in db.query(Message).filter(Message.to_email == sender).all():
                msg.status = "Replied"
                hit = True

            if hit:
                matched += 1
                db.add(ActionLog(actor="inbound", action="reply_matched", entity="email",
                                 entity_id=sender, detail={"account": account, "subject": reply.get("subject")}))

    db.commit()
    log.info("Inbound sync: scanned %d, matched %d", scanned, matched)
    return {"scanned": scanned, "matched": matched}
