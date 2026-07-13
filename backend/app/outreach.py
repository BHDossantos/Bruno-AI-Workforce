"""Shared outbound email dispatch.

One place that turns a drafted message into a Gmail send/draft, honoring
``GMAIL_OUTBOUND_MODE`` plus the per-account daily cap and same-day dedupe.
Used by the agents (first touch) and the follow-up engine.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from . import email_template
from .config import settings
from .integrations import gmail
from .models import ActionLog, Lead, Message, Restaurant


def _bump_contact(db: Session, entity_type: str | None, entity_id) -> None:
    """Record that we reached out to this entity (count + timestamp)."""
    model = {"lead": Lead, "restaurant": Restaurant}.get(entity_type or "")
    if not model or not entity_id:
        return
    row = db.query(model).filter(model.id == entity_id).first()
    if row is not None:
        row.times_contacted = (row.times_contacted or 0) + 1
        row.last_contacted_at = datetime.now(timezone.utc)


def _split_name(full: str | None) -> tuple[str | None, str | None]:
    parts = (full or "").strip().split()
    if not parts:
        return None, None
    return parts[0], (" ".join(parts[1:]) or None)


def _entity_fields(db: Session, entity_type: str | None, entity_id):
    """(first, last, company, website, phone) for the lead/restaurant behind a message,
    used to enrich the lead we hand to Instantly. Best-effort; never raises."""
    if entity_type == "lead":
        row = db.query(Lead).filter(Lead.id == entity_id).first()
        if row:
            first, last = _split_name(row.owner_name)
            return first, last, row.company_name, row.website, row.phone
    elif entity_type == "restaurant":
        row = db.query(Restaurant).filter(Restaurant.id == entity_id).first()
        if row:
            first, last = _split_name(row.owner_manager)
            return first, last, row.name, row.website, row.phone
    return None, None, None, None, None


# Placeholder/sample domains that must never receive real outreach.
_PLACEHOLDER_DOMAINS = {"example.com", "example.org", "example.net", "test.com",
                        "email.com", "domain.com", "sample.com"}
_PLACEHOLDER_SUFFIXES = (".invalid", ".local", ".test", ".example")


def is_real_email(addr: str | None) -> bool:
    """True only for a plausibly-real, deliverable address (not sample data)."""
    a = (addr or "").strip().lower()
    if "@" not in a or a.count("@") != 1:
        return False
    domain = a.split("@", 1)[1]
    if not domain or "." not in domain:
        return False
    if domain in _PLACEHOLDER_DOMAINS:
        return False
    return not any(domain.endswith(s) for s in _PLACEHOLDER_SUFFIXES)


def _day_start():
    return datetime.combine(date.today(), datetime.min.time(), tzinfo=timezone.utc)


def sent_today_count(db: Session, account: str | None = None) -> int:
    """Emails actually sent today. Per-account when account is given, else GLOBAL
    across all accounts (used for the provider-wide cap, e.g. SendGrid's daily limit)."""
    q = db.query(func.count()).select_from(Message).filter(Message.sent_at >= _day_start())
    if account is not None:
        q = q.filter(Message.from_account == account)
    return q.scalar() or 0


def effective_cap(db: Session, account: str) -> int:
    """Daily send cap with deliverability warmup: a fresh mailbox starts low and
    ramps up, so it isn't flagged as spam. Reaches the full cap over time."""
    cap = settings.gmail_daily_send_cap
    if not settings.email_warmup_enabled:
        return cap
    first = db.query(func.min(Message.sent_at)).filter(
        Message.from_account == account, Message.sent_at.isnot(None)).scalar()
    days = (date.today() - first.date()).days if first else 0
    return min(cap, settings.email_warmup_start + settings.email_warmup_step * max(0, days))


def already_contacted_today(db: Session, to_email: str) -> bool:
    return db.query(Message).filter(
        Message.to_email == to_email, Message.sent_at >= _day_start(),
    ).first() is not None


def _log(db: Session, actor: str, action: str, msg: Message, **detail) -> None:
    db.add(ActionLog(actor=actor, action=action, entity="message",
                     entity_id=str(msg.id), detail=detail or None))


def deliver(to_email: str, subject: str | None, body: str | None,
            account: str = "insurance") -> tuple[str | None, str | None]:
    """Deliver one email NOW via the best available channel, returning
    (message_id, error_reason).

    Order: Resend first (modern API, best deliverability on your own domain), then
    SendGrid, then the account's Gmail mailbox. This is what the Outbox "Send" /
    "Send next N" buttons use, so a working provider delivers even when a Gmail app
    password is rejected.
    """
    from .integrations import resend, sendgrid
    html = email_template.render(email_template.clean_body(body), account)
    # 1) Resend — preferred when connected.
    if resend.is_configured():
        from_email = resend.from_for(account)
        reply_to = resend.replyto_for(account, from_email)
        mid, err = resend.send_with_error(to_email, subject or "", html or "",
                                          from_email=from_email, reply_to=reply_to)
        if mid:
            return mid, None
        # Resend couldn't send — fall through to SendGrid / Gmail, else report why.
        if not sendgrid.is_configured() and not gmail.is_configured(account):
            return None, err
        _resend_err = err
    else:
        _resend_err = None
    # 2) SendGrid.
    if sendgrid.is_configured():
        from_email = sendgrid.from_for(account)
        reply_to = sendgrid.replyto_for(account, from_email)
        mid, err = sendgrid.send_with_error(to_email, subject or "", html or "",
                                            from_email=from_email, reply_to=reply_to)
        if mid:
            return mid, None
        # SendGrid couldn't send — fall through to Gmail if it's set up, else
        # report the SendGrid reason.
        if gmail.is_configured(account):
            mid2, err2 = gmail.send_with_error(to_email, subject or "", body or "", account=account)
            return mid2, (None if mid2 else (err2 or err))
        return None, err
    if gmail.is_configured(account):
        return gmail.send_with_error(to_email, subject or "", body or "", account=account)
    return None, (_resend_err
                  or f"No delivery channel configured for '{account}' (connect Resend, SendGrid or a Gmail mailbox)")


def can_deliver(account: str = "insurance") -> bool:
    """True if any channel can deliver for this account (Resend, SendGrid or Gmail)."""
    from .integrations import resend, sendgrid
    return resend.is_configured() or sendgrid.is_configured() or gmail.is_configured(account)


def send_email_drafts(db: Session, *, limit: int = 25, account: str | None = None) -> dict:
    """Send drafted/approved outbound emails in the operator's priority order:
    new HOT & uncontacted → HOT needing follow-up → WARM → COLD (dead last), and
    within a tier the oldest draft first for fair pacing. Shared by the manual
    'Send drafts' button AND the auto-outreach cron. Returns sent/failed counts +
    the real failure reasons."""
    from sqlalchemy import and_

    from . import lead_temperature
    q = (db.query(Message)
         .outerjoin(Lead, and_(Message.entity_type == "lead", Message.entity_id == Lead.id))
         .filter(Message.direction == "outbound", Message.to_email.isnot(None),
                 Message.status.in_(["Drafted", "Approved"])))
    if account:
        q = q.filter(Message.from_account == account)
    msgs = (q.order_by(*lead_temperature.send_priority_order(Lead, Message))
            .limit(max(1, min(limit, 50))).all())

    sent = failed = 0
    errors: list[str] = []
    for m in msgs:
        if not can_deliver(m.from_account):
            failed += 1
            reason = f"No delivery channel for '{m.from_account}' — connect SendGrid or a Gmail mailbox"
            if reason not in errors:
                errors.append(reason)
            continue
        mid, err = deliver(m.to_email, m.subject, m.body, account=m.from_account)
        if mid:
            m.provider_id = mid
            m.approved = True
            m.status = "Sent"
            m.sent_at = datetime.now(timezone.utc)
            sent += 1
        else:
            failed += 1
            if err and err not in errors:
                errors.append(err)
    db.commit()
    return {"sent": sent, "failed": failed, "considered": len(msgs), "errors": errors[:3]}


def dispatch_email(db: Session, *, entity_type: str, entity_id, to_email: str | None,
                   subject: str | None, body: str | None, account: str = "personal",
                   actor: str = "system", force_draft: bool = False,
                   autonomous: bool = True) -> Message:
    """Create a Message and route it via Gmail per the configured mode.

    force_draft keeps it a draft regardless of GMAIL_OUTBOUND_MODE (used for
    replies, which a human should review before sending).

    autonomous=True (the default, used by agents/cron) means: in semi/manual mode
    the message is drafted and waits for approval. Explicit user actions (approval
    queue, manual 'send' buttons) pass autonomous=False so they send immediately."""
    # Pick up any Gmail/data credentials connected via the in-app Setup page — even
    # if THIS process/instance started before they were saved (multi-instance safe).
    try:
        from . import runtime_config
        runtime_config.apply_to_settings(db)
    except Exception:  # never let config refresh block a send
        pass
    # Insurance relay through the personal mailbox (Thrust reply-to). Enabled when
    # the user flips the toggle, OR AUTOMATICALLY when the insurance mailbox has no
    # sender of its own but the personal mailbox can send — so business-insurance
    # outreach goes out on autopilot without any extra setup. Replies still land in
    # the Thrust inbox via Reply-To.
    try:
        from . import control
        if account == gmail.INSURANCE and (
            control.insurance_relay_via_personal(db)
            or (gmail.is_configured(gmail.PERSONAL)
                and not gmail.has_own_credentials(gmail.INSURANCE))
        ):
            settings.insurance_via_personal_reply_to = True
    except Exception:  # never let a toggle lookup block a send
        pass
    body = email_template.clean_body(body)  # strip AI placeholders/sign-offs once
    msg = Message(channel="email", direction="outbound", entity_type=entity_type,
                  entity_id=entity_id, to_email=to_email, from_account=account,
                  subject=subject, body=body, status="Drafted", approved=False)
    db.add(msg)
    db.flush()

    from .integrations import sender, sendgrid
    # A sender is anything that can deliver: a campaign engine (Instantly/Smartlead),
    # SendGrid (direct delivery), or Gmail. Only draft if NONE is configured.
    if not to_email or not (gmail.is_configured(account) or sender.is_configured()
                            or sendgrid.is_configured()):
        return msg  # nothing to send to / no sender configured — keep as stored draft
    if not is_real_email(to_email):
        # Never email sample/placeholder data — keep it as a draft only.
        _log(db, actor, "send_skipped_synthetic", msg, to=to_email)
        return msg

    from . import control
    if control.is_paused_safe(db):
        # Emergency stop engaged — keep everything as a draft, send nothing.
        _log(db, actor, "send_skipped_paused", msg, to=to_email)
        return msg
    # Semi-auto / manual mode: agent- and cron-initiated sends DRAFT and wait for
    # the user to approve in the Approval Queue. Only full-auto mode auto-sends.
    # Explicit user actions (approval, manual buttons) pass autonomous=False → send.
    # EXCEPTION: with Outreach Autopilot on, SALES outreach (cold leads + their
    # follow-ups) auto-sends even in semi mode — the lead machine runs on its own,
    # while content still waits for approval.
    outreach_auto = (entity_type in ("lead", "restaurant", "contact")
                     and control.outreach_autopilot(db))
    if autonomous and control.get_mode(db) != "auto" and not outreach_auto:
        _log(db, actor, "email_drafted_semi", msg, to=to_email)
        return msg

    # Provider hand-off: when a dedicated engine (Instantly/Smartlead) is connected,
    # push the lead into its campaign, which sends + follows up + warms across its own
    # inboxes. We pass our AI-written body as the personalization variable. The
    # provider paces itself, so OUR daily cap doesn't apply here. This is the durable
    # path for cold email at volume.
    if not force_draft and sender.is_configured() and entity_type in ("lead", "restaurant", "contact"):
        first = last = company = website = phone = None
        try:
            first, last, company, website, phone = _entity_fields(db, entity_type, entity_id)
        except Exception:
            pass
        if sender.add_lead(email=to_email, first_name=first, last_name=last,
                           company_name=company, website=website, phone=phone,
                           personalization=body):
            msg.provider_id = sender.name() or "provider"
            msg.approved = True
            msg.status = "Sent"
            msg.sent_at = datetime.now(timezone.utc)
            _bump_contact(db, entity_type, entity_id)
            _log(db, actor, "email_sent_provider", msg, to=to_email, account=sender.name())
            try:
                from . import newsletters
                newsletters.subscribe_on_outreach(db, entity_type, entity_id, to_email)
            except Exception:
                pass
        else:
            _log(db, actor, "provider_handoff_failed", msg, to=to_email)
        return msg

    # Normalize the configured mode: only the three known values are valid;
    # anything else (e.g. a stray env var like "15") must NOT silently disable
    # sending — default unknown values to "send" since auto-send is the intent.
    configured = (settings.gmail_outbound_mode or "send").strip().lower()
    if configured not in ("send", "send_on_approve", "draft"):
        configured = "send"
    mode = "draft" if force_draft else configured
    if mode == "send" and already_contacted_today(db, to_email):
        _log(db, actor, "send_skipped_duplicate", msg, to=to_email)
        return msg
    # SendGrid has ONE global daily limit (not per-mailbox), so cap on the global
    # sent-today count; Gmail mailboxes are capped per-account with warmup.
    if sendgrid.is_configured():
        _cap, _sent = settings.sendgrid_daily_cap, sent_today_count(db)
    else:
        _cap, _sent = effective_cap(db, account), sent_today_count(db, account)
    if mode == "send" and _sent >= _cap:
        mode = "draft"  # hit the daily cap — degrade to a draft

    html = email_template.render(body, account)  # consistent template + compliant footer
    if mode == "send":
        # Deliver via SendGrid when connected (reliable at volume), else Gmail.
        # Send AS the business's verified sender; replies come back to that address.
        if sendgrid.is_configured():
            from_email = sendgrid.from_for(account)
            reply_to = sendgrid.replyto_for(account, from_email)
            mid = sendgrid.send_email(to_email, subject or "", html or "",
                                      from_email=from_email, reply_to=reply_to)
        else:
            mid = gmail.send_message(to_email, subject or "", html or "", account=account)
        if mid:
            msg.provider_id = mid
            msg.approved = True
            msg.status = "Sent"
            msg.sent_at = datetime.now(timezone.utc)
            _bump_contact(db, entity_type, entity_id)  # track reach-out count
            _log(db, actor, "email_sent", msg, to=to_email, account=account)
            # Add people we ACTUALLY emailed to their funnel newsletter (CAN-SPAM:
            # every issue has an unsubscribe link). Only on a real send — never for
            # drafts/paused/capped/unapproved, so we never subscribe someone we
            # didn't email.
            try:
                from . import newsletters
                newsletters.subscribe_on_outreach(db, entity_type, entity_id, to_email)
            except Exception:
                pass
    else:  # draft / send_on_approve
        did = gmail.create_draft(to_email, subject or "", html or "", account=account)
        if did:
            msg.provider_id = did
            _log(db, actor, "email_drafted", msg, to=to_email, account=account)
    return msg
