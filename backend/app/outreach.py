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


def sent_today_count(db: Session, account: str) -> int:
    return db.query(func.count()).select_from(Message).filter(
        Message.from_account == account, Message.sent_at >= _day_start(),
    ).scalar() or 0


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
    body = email_template.clean_body(body)  # strip AI placeholders/sign-offs once
    msg = Message(channel="email", direction="outbound", entity_type=entity_type,
                  entity_id=entity_id, to_email=to_email, from_account=account,
                  subject=subject, body=body, status="Drafted", approved=False)
    db.add(msg)
    db.flush()

    if not to_email or not gmail.is_configured(account):
        return msg  # nothing to send to / account unconfigured — keep as stored draft
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

    mode = "draft" if force_draft else settings.gmail_outbound_mode
    if mode == "send" and already_contacted_today(db, to_email):
        _log(db, actor, "send_skipped_duplicate", msg, to=to_email)
        return msg
    if mode == "send" and sent_today_count(db, account) >= effective_cap(db, account):
        mode = "draft"  # hit the (warmup-aware) daily cap — degrade to a draft

    html = email_template.render(body, account)  # consistent template + compliant footer
    if mode == "send":
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
