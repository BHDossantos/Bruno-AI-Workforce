"""Inbound email sync.

Reads recent replies from both Gmail accounts (personal + insurance) and marks
the matching lead / restaurant / message as ``Replied``. This is the foundation
for Phase 3 reply classification; for now it does sender-address matching.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from . import classify, newsletters, sms_engine
from .integrations import gmail
from .models import ActionLog, Lead, Message, Restaurant

_TERMINAL = ("Interested", "Closed Won", "Closed Lost")

log = logging.getLogger("bruno.inbound")
ACCOUNTS = [gmail.PERSONAL, gmail.INSURANCE]


def _draft_reply(db: Session, sender: str, reply: dict, cls: dict, account: str) -> None:
    """Generate a concise reply with AI and save it as a draft for one-click send.
    When the prospect is interested/asking, the reply drives straight to the
    calendar (the booking link is added by the email template automatically)."""
    from . import email_template, outreach
    from .ai import client, skills
    intent = cls.get("intent")
    wants_call = intent in ("interested", "question")
    link = email_template.booking_link(account)
    # For a hot reply, explicitly push the booking link + propose a call; otherwise
    # a warm, helpful reply that opens the door to one.
    goal = ("They're interested — thank them, answer briefly, and drive to a quick call. "
            + (f"Point them to this booking link to grab a time: {link}. "
               if link else "Ask for two or three times that work. ")
            if wants_call else
            "Write a warm, helpful reply that gently opens the door to a short call. ")
    seed = cls.get("suggested_reply") or ""
    body = client.complete(
        f"A prospect ({sender}) replied to our outreach. Their message:\n"
        f"\"{reply.get('snippet', '')}\"\n\nIntent: {intent}.\n"
        + (f"A suggested angle: {seed}\n" if seed else "")
        + goal + "Keep it short (max 120 words). No subject line, no placeholders.",
        system=skills.system_prompt("cold-email"))
    if not body or body.startswith("["):
        return  # offline stub — skip
    outreach.dispatch_email(db, entity_type="reply", entity_id=None, to_email=sender,
                            subject=f"Re: {reply.get('subject') or 'your note'}",
                            body=body, account=account, actor="inbound", force_draft=True)


def sync_replies(db: Session, newer_than_days: int = 3) -> dict:
    # Pick up Gmail credentials connected via the in-app Setup page on any instance.
    try:
        from . import runtime_config
        runtime_config.apply_to_settings(db)
    except Exception:
        pass
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
            _auto_entity = (None, None)  # (entity_type, entity_id) for automation branching

            for lead in db.query(Lead).filter(Lead.email == sender).all():
                _auto_entity = ("lead", lead.id)
                if lead.status not in _TERMINAL:
                    lead.status = cls["status"]
                # Warm → auto-text from the insurance number.
                sms_engine.maybe_warm_text(
                    db, entity_type="lead", entity_id=lead.id,
                    name=lead.company_name or lead.owner_name, phone=lead.phone,
                    context=lead.reason or "insurance", account="insurance")
                # Warm reply → subscribe to that funnel's newsletter (CAN-SPAM: opt-in).
                f = newsletters.funnel_for_segment(lead.segment)
                if f:
                    newsletters.subscribe(db, f, sender, lead.company_name or lead.owner_name)
                hit = True
            for rest in db.query(Restaurant).filter(Restaurant.email == sender).all():
                _auto_entity = ("restaurant", rest.id)
                if rest.status not in _TERMINAL:
                    rest.status = cls["status"]
                sms_engine.maybe_warm_text(
                    db, entity_type="restaurant", entity_id=rest.id, name=rest.name,
                    phone=rest.phone, context=rest.pain_points or "SavoryMind", account="personal")
                newsletters.subscribe(db, "savorymind", sender, rest.name)
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

                # Automation rules: branch on the reply intent (task / suppress /
                # nurture / stop drip) per the user's enabled rules.
                try:
                    from . import automation
                    automation.on_reply(db, intent=cls["intent"], sender=sender,
                                        entity_type=_auto_entity[0], entity_id=_auto_entity[1],
                                        summary=cls.get("summary"))
                except Exception:
                    log.debug("automation rules skipped", exc_info=True)

                # AI-draft a reply (kept as a draft for one-click review/send).
                # Skipped for unsubscribes (we're suppressing, not replying).
                try:
                    if cls["intent"] != "unsubscribe":
                        _draft_reply(db, sender, reply, cls, account)
                except Exception:
                    log.debug("reply draft skipped", exc_info=True)

    db.commit()
    log.info("Inbound sync: scanned %d, matched %d", scanned, matched)
    return {"scanned": scanned, "matched": matched}
