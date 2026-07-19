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


def _auto_reply_on() -> bool:
    """Opt-in flag to SEND (not just draft) the reply to hot leads. Tolerates a real
    bool (default) or a runtime-config string ('true'/'1'/'on')."""
    from .config import settings
    v = getattr(settings, "auto_reply_enabled", False)
    return v is True or str(v).strip().lower() in ("1", "true", "yes", "on")


def _draft_reply(db: Session, sender: str, reply: dict, cls: dict, account: str) -> None:
    """Generate a concise reply with AI. Normally saved as a draft for one-click send;
    when auto_reply_enabled is on AND the prospect is clearly interested/asking, it's
    SENT immediately (with the booking link) so a hot lead gets an answer in seconds."""
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
    # Send now only for a clearly-interested reply when the operator opted in;
    # otherwise keep it a draft for one-click human review. dispatch_email still
    # runs the compliance gate + daily cap, so auto-send can't reach an opted-out
    # address or blow the cap.
    auto_send = wants_call and _auto_reply_on()
    outreach.dispatch_email(db, entity_type="reply", entity_id=None, to_email=sender,
                            subject=f"Re: {reply.get('subject') or 'your note'}",
                            body=body, account=account, actor="inbound",
                            force_draft=not auto_send)


def process_reply(db: Session, *, sender: str, subject: str | None, snippet: str,
                  account: str, store_message: bool = False) -> dict:
    """Process one inbound email reply end-to-end: classify it, link it to the
    matching lead / restaurant / message, advance their status, warm-text, opt them
    into the funnel newsletter, log it, notify external webhooks, and AI-draft a
    one-click reply. Shared by the Gmail poll (``sync_replies``) and the Resend
    inbound webhook so both paths behave identically.

    ``store_message`` (webhook path) also persists the inbound email itself as a
    Message row so it shows on the contact's CRM thread — the Gmail poll leaves it
    False since it only flags the existing outbound thread as Replied.

    Does NOT commit — the caller owns the transaction. Returns ``{"hit", "cls"}``.
    """
    reply = {"snippet": snippet, "subject": subject}
    cls = classify.classify_reply(snippet or "")
    hit = False
    _auto_entity = (None, None)  # (entity_type, entity_id) for automation branching
    linked = (None, None)        # entity to attach the stored inbound message to

    for lead in db.query(Lead).filter(Lead.email == sender).all():
        _auto_entity = linked = ("lead", lead.id)
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
        _auto_entity = linked = ("restaurant", rest.id)
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

    # Persist the actual inbound email onto the CRM thread (webhook path). Worth
    # recording even from an unknown sender, so it forces a "hit" (log + draft).
    if store_message:
        db.add(Message(channel="email", direction="inbound", to_email=sender,
                       subject=subject, body=snippet, status=cls["status"],
                       entity_type=linked[0], entity_id=linked[1], from_account=account))
        hit = True

    if hit:
        db.add(ActionLog(actor="inbound", action="reply_classified", entity="email",
                         entity_id=sender, detail={"account": account, "intent": cls["intent"],
                                                   "summary": cls["summary"],
                                                   "subject": subject}))
        # Remember the interaction in the knowledge graph.
        try:
            from . import memory
            memory.add(db, f"{sender} replied ({cls['intent']}): {cls.get('summary') or snippet}",
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

        # Notify any subscribed external automation (n8n/Make/etc.).
        try:
            from . import webhooks
            webhooks.dispatch(db, "lead.replied", {
                "sender": sender, "account": account, "intent": cls["intent"],
                "summary": cls.get("summary"), "subject": subject})
        except Exception:
            log.debug("webhook dispatch skipped", exc_info=True)

        # AI-draft a reply (kept as a draft for one-click review/send).
        # Skipped for unsubscribes (we're suppressing, not replying).
        try:
            if cls["intent"] != "unsubscribe":
                _draft_reply(db, sender, reply, cls, account)
        except Exception:
            log.debug("reply draft skipped", exc_info=True)

    return {"hit": hit, "cls": cls}


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
            res = process_reply(db, sender=sender, subject=reply.get("subject"),
                                snippet=reply.get("snippet", ""), account=account)
            if res["hit"]:
                matched += 1

    db.commit()
    log.info("Inbound sync: scanned %d, matched %d", scanned, matched)
    return {"scanned": scanned, "matched": matched}
