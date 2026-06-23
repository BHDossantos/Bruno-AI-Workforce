"""Shared outbound email dispatch.

One place that turns a drafted message into a Gmail send/draft, honoring
``GMAIL_OUTBOUND_MODE`` plus the per-account daily cap and same-day dedupe.
Used by the agents (first touch) and the follow-up engine.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from .config import settings
from .integrations import gmail
from .models import ActionLog, Message


def _day_start():
    return datetime.combine(date.today(), datetime.min.time(), tzinfo=timezone.utc)


def sent_today_count(db: Session, account: str) -> int:
    return db.query(func.count()).select_from(Message).filter(
        Message.from_account == account, Message.sent_at >= _day_start(),
    ).scalar() or 0


def already_contacted_today(db: Session, to_email: str) -> bool:
    return db.query(Message).filter(
        Message.to_email == to_email, Message.sent_at >= _day_start(),
    ).first() is not None


def _log(db: Session, actor: str, action: str, msg: Message, **detail) -> None:
    db.add(ActionLog(actor=actor, action=action, entity="message",
                     entity_id=str(msg.id), detail=detail or None))


def dispatch_email(db: Session, *, entity_type: str, entity_id, to_email: str | None,
                   subject: str | None, body: str | None, account: str = "personal",
                   actor: str = "system") -> Message:
    """Create a Message and route it via Gmail per the configured mode."""
    msg = Message(channel="email", direction="outbound", entity_type=entity_type,
                  entity_id=entity_id, to_email=to_email, from_account=account,
                  subject=subject, body=body, status="Drafted", approved=False)
    db.add(msg)
    db.flush()

    if not to_email or not gmail.is_configured(account):
        return msg  # nothing to send to / account unconfigured — keep as stored draft

    mode = settings.gmail_outbound_mode
    if mode == "send" and already_contacted_today(db, to_email):
        _log(db, actor, "send_skipped_duplicate", msg, to=to_email)
        return msg
    if mode == "send" and sent_today_count(db, account) >= settings.gmail_daily_send_cap:
        mode = "draft"  # hit the daily cap — degrade to a draft

    if mode == "send":
        mid = gmail.send_message(to_email, subject or "", body or "", account=account)
        if mid:
            msg.provider_id = mid
            msg.approved = True
            msg.status = "Sent"
            msg.sent_at = datetime.now(timezone.utc)
            _log(db, actor, "email_sent", msg, to=to_email, account=account)
    else:  # draft / send_on_approve
        did = gmail.create_draft(to_email, subject or "", body or "", account=account)
        if did:
            msg.provider_id = did
            _log(db, actor, "email_drafted", msg, to=to_email, account=account)
    return msg
