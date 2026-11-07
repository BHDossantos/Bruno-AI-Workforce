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

_TERMINAL = ("Interested", "Closed Won", "Closed Lost", "do_not_contact", "Do Not Contact", "Unsubscribed", "Bounced")

log = logging.getLogger("bruno.inbound")
ACCOUNTS = [gmail.PERSONAL, gmail.INSURANCE, gmail.INSURANCE_BACKUP, gmail.BNB, gmail.SAVORYMIND]


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
                  account: str, store_message: bool = False, allow_automation: bool = True) -> dict:
    """Classify/link an inbound message. Provider ingestion passes allow_automation=False.

    Opt-outs are persisted immediately and never run warm texts or drafting.
    Other callers retain their existing explicit automation controls.
    """
    reply = {"snippet": snippet, "subject": subject}
    cls = classify.classify_reply(snippet or "")
    if cls.get("intent") == "unsubscribe":
        from . import compliance
        compliance.add_dnc(db, value=sender, kind="email", reason="inbound opt-out", source="inbound", commit=False)
        if store_message:
            db.add(Message(channel="email", direction="inbound", to_email=sender,
                           subject=subject, body=snippet, status="Unsubscribed", from_account=account))
        return {"hit": True, "cls": cls}
    hit = False
    _auto_entity = (None, None)  # (entity_type, entity_id) for automation branching
    linked = (None, None)        # entity to attach the stored inbound message to

    for lead in db.query(Lead).filter(Lead.email == sender).all():
        _auto_entity = linked = ("lead", lead.id)
        if lead.status not in _TERMINAL:
            lead.status = cls["status"]
        # Warm → auto-text from the insurance number.
        if allow_automation:
            sms_engine.maybe_warm_text(
            db, entity_type="lead", entity_id=lead.id,
            name=lead.company_name or lead.owner_name, phone=lead.phone,
            context=lead.reason or "insurance", account="insurance")
        # Warm reply → subscribe to that funnel's newsletter (CAN-SPAM: opt-in).
        f = newsletters.funnel_for_segment(lead.segment)
        if f and allow_automation:
            newsletters.subscribe(db, f, sender, lead.company_name or lead.owner_name)
        hit = True
    for rest in db.query(Restaurant).filter(Restaurant.email == sender).all():
        _auto_entity = linked = ("restaurant", rest.id)
        if rest.status not in _TERMINAL:
            rest.status = cls["status"]
        if allow_automation:
            sms_engine.maybe_warm_text(
            db, entity_type="restaurant", entity_id=rest.id, name=rest.name,
            phone=rest.phone, context=rest.pain_points or "SavoryMind", account="personal")
        if allow_automation:
            newsletters.subscribe(db, "savorymind", sender, rest.name)
        hit = True
    for msg in db.query(Message).filter(Message.to_email == sender, Message.direction == "outbound").all():
        msg.status = "Replied"
        hit = True

    # Store unknown inbound mail, but do not present it as a matched outreach reply.
    if store_message:
        db.add(Message(channel="email", direction="inbound", to_email=sender,
                       subject=subject, body=snippet, status=cls["status"] if hit else "Unmatched Inbound",
                       entity_type=linked[0], entity_id=linked[1], from_account=account))
        hit = True

    if hit:
        db.add(ActionLog(actor="inbound", action="reply_classified", entity="email",
                         entity_id=sender, detail={"account": account, "intent": cls["intent"],
                                                   "summary": cls["summary"],
                                                   "subject": subject}))
        if not allow_automation:
            return {"hit": hit, "cls": cls}
        # Remember the interaction in the knowledge graph.
        try:
            from . import memory
            memory.add(db, f"{sender} replied ({cls['intent']}): {cls.get('summary') or snippet}",
                       kind="event", subject=sender, source="inbound", commit=False)
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
    """Store each provider message once before classification; never send from ingestion."""
    import uuid
    from datetime import datetime, timezone, timedelta
    from sqlalchemy import select, func
    from .models import MailboxSyncHealth
    from . import compliance, runtime_config
    runtime_config.apply_to_settings(db)
    scanned = matched = duplicates = 0
    health = {}
    for account in ACCOUNTS:
        prior_health = db.get(MailboxSyncHealth, account)
        since = prior_health.completed_through if prior_health else None
        if since:
            since = since.replace(tzinfo=timezone.utc) if since.tzinfo is None else since
            since -= timedelta(minutes=5)  # overlap is safe because identities are durable
        running = prior_health or MailboxSyncHealth(account=account)
        running.status, running.error_code = "running", None
        running.checked_at = datetime.now(timezone.utc)
        running.scanned = 0
        db.add(running)
        db.commit()  # interrupted scans remain visibly incomplete
        batch = gmail.list_replies(newer_than_days=newer_than_days, account=account, since=since)
        status = getattr(batch, "status", "unverified")
        error = getattr(batch, "error_code", None)
        for reply in batch:
            scanned += 1
            if not all(reply.get(k) for k in ("mailbox", "message_id", "received_at", "from_email")):
                status, error = "partial", "missing_provider_identity"
                continue
            identity = f"gmail:{reply['mailbox']}:{reply['message_id']}"
            mid = uuid.uuid5(uuid.NAMESPACE_URL, identity)
            dialect = db.get_bind().dialect.name
            if dialect == "postgresql":
                from sqlalchemy.dialects.postgresql import insert
            elif dialect == "sqlite":
                from sqlalchemy.dialects.sqlite import insert
            else:
                raise RuntimeError("Unsupported ingestion storage")
            sender = reply["from_email"]
            matching_accounts = list({account, *(a for a in ACCOUNTS
                if gmail.address_for(a).strip().lower() == reply["mailbox"].lower())})
            bounce = reply.get("bounce_to")
            won = db.execute(insert(Message).values(id=mid, channel="email", direction="inbound",
                to_email=sender, from_account=account, subject=reply.get("subject"), body=reply.get("snippet", ""),
                status="Bounce Report" if bounce else "Received", provider_id=identity,
                created_at=reply["received_at"]).on_conflict_do_nothing(index_elements=["id"]).returning(Message.id)).scalar()
            if not won:
                duplicates += 1
                continue
            if bounce:
                # A structured DSN is a conservative suppression signal, not a
                # fabricated delivery receipt. Only link known older outbound mail.
                for bounce_address in reply.get("bounce_recipients") or [bounce]:
                    originals = db.scalars(select(Message).where(Message.direction == "outbound",
                        Message.channel == "email", Message.from_account.in_(matching_accounts),
                        func.lower(func.trim(Message.to_email)) == bounce_address,
                        Message.sent_at <= reply["received_at"])).all()
                    if originals:
                        for original in originals:
                            original.delivery_status = "bounced"
                        compliance.add_dnc(db, value=bounce_address, kind="email", reason="Gmail permanent DSN; review evidence", source="gmail_dsn", commit=False)
                db.commit()
                continue
            result = classify.classify_reply(reply.get("snippet", ""))
            if result.get("intent") == "unsubscribe":
                compliance.add_dnc(db, value=sender, kind="email", reason="Gmail opt-out", source="gmail", commit=False)
            originals = db.scalars(select(Message).where(Message.direction == "outbound",
                Message.channel == "email", Message.from_account.in_(matching_accounts),
                func.lower(func.trim(Message.to_email)) == sender,
                Message.sent_at <= reply["received_at"])).all()
            incoming = db.get(Message, mid)
            incoming.status = "Replied" if originals else "Unmatched Inbound"
            for original in originals:
                original.status = "Replied"
            for lead in (db.scalars(select(Lead).where(func.lower(func.trim(Lead.email)) == sender)) if originals else []):
                if lead.status not in _TERMINAL:
                    lead.status = result.get("status", "Replied")
            for restaurant in (db.scalars(select(Restaurant).where(func.lower(func.trim(Restaurant.email)) == sender)) if originals else []):
                if restaurant.status not in _TERMINAL:
                    restaurant.status = result.get("status", "Replied")
            matched += bool(originals)
            db.add(ActionLog(actor="inbound", action="reply_classified", entity="email", entity_id=sender,
                detail={"account": account, "intent": result.get("intent"), "provider_message": identity}))
            db.commit()
        record = db.scalar(select(MailboxSyncHealth).where(MailboxSyncHealth.account == account)
                           .with_for_update().execution_options(populate_existing=True))
        record.status, record.error_code = status, error
        record.checked_at = datetime.now(timezone.utc)
        record.scanned = len(batch)
        if status == "complete":
            through = getattr(batch, "through", None)
            old = record.completed_through
            if old and old.tzinfo is None:
                old = old.replace(tzinfo=timezone.utc)
            if through and (old is None or through > old):
                record.completed_through = through
        db.add(record)
        db.commit()
        health[account] = {"status": status, "error_code": error, "scanned": len(batch)}
    return {"scanned": scanned, "matched": matched, "duplicates": duplicates, "health": health,
            "outreach_sent": 0}
