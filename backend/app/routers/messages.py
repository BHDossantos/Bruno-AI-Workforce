"""Outbox + inbound sync routes.

Lists outbound messages (sent / drafted), lets an operator approve & send a
drafted message through the correct Gmail account, and triggers inbound reply
sync across both mailboxes.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import followups, inbound
from ..database import get_db
from ..models import Message
from ..schemas import MessageOut
from ..security import require_role

router = APIRouter(tags=["messages"])
_read = require_role("admin", "operator", "viewer")
_write = require_role("admin", "operator")


class ReplyIn(BaseModel):
    to_email: str
    subject: str | None = None
    body: str
    account: str | None = None


@router.get("/messages", response_model=list[MessageOut])
def list_messages(status: str | None = None, account: str | None = None, limit: int = 200,
                  db: Session = Depends(get_db), _=Depends(_read)):
    q = db.query(Message)
    if status:
        q = q.filter(Message.status == status)
    if account:
        q = q.filter(Message.from_account == account)
    return q.order_by(Message.created_at.desc()).limit(limit).all()


@router.post("/messages/{message_id}/approve", response_model=MessageOut)
def approve_message(message_id: str, db: Session = Depends(get_db), _=Depends(_write)):
    msg = db.query(Message).filter(Message.id == message_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    msg.approved = True
    db.commit()
    db.refresh(msg)
    return msg


@router.post("/messages/{message_id}/send", response_model=MessageOut)
def send_message(message_id: str, db: Session = Depends(get_db), _=Depends(_write)):
    """Send a drafted message now via its account's mailbox (one click, no approval step)."""
    msg = db.query(Message).filter(Message.id == message_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    if not msg.to_email:
        raise HTTPException(status_code=400, detail="Message has no recipient")
    from .. import outreach
    if not outreach.can_deliver(msg.from_account):
        raise HTTPException(status_code=400,
                            detail=f"No delivery channel for '{msg.from_account}' — connect Resend or a Gmail mailbox in Setup")
    mid, err = outreach.deliver(msg.to_email, msg.subject, msg.body, account=msg.from_account)
    if not mid:
        raise HTTPException(status_code=502, detail=f"Send failed: {err or 'unknown error'}")
    msg.provider_id = mid
    msg.approved = True
    msg.status = "Sent"
    msg.sent_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(msg)
    return msg


class SendDraftsIn(BaseModel):
    account: str | None = None
    limit: int = 20


@router.post("/messages/send-drafts")
def send_drafts(body: SendDraftsIn, db: Session = Depends(get_db), _=Depends(_write)):
    """Send N drafted outbound messages in one click, HOT LEADS FIRST (paced —
    protects a new mailbox's deliverability). A drafted email to a hot/in-market
    lead (EverQuote) goes out before any colder lead's; within the same tier the
    oldest draft goes first so pacing stays fair. Reports sent/failed + the real
    reason for any failure."""
    from .. import outreach
    return outreach.send_email_drafts(db, limit=body.limit, account=body.account)


@router.post("/messages/reply")
def send_custom_reply(body: ReplyIn, db: Session = Depends(get_db), _=Depends(_write)):
    """Send a composed reply now (e.g. a quote-intake email chosen in the inbox).
    Explicit operator action → sends immediately via the shared dispatcher, which
    still enforces the daily cap, paused state and real-email guard."""
    from .. import outreach
    if not body.to_email or not body.body:
        raise HTTPException(status_code=400, detail="Recipient and body are required")
    msg = outreach.dispatch_email(
        db, entity_type="reply", entity_id=None, to_email=body.to_email,
        subject=body.subject or "Re: your message", body=body.body,
        account=body.account or "insurance", actor="inbox", autonomous=False)
    return {"ok": msg.status == "Sent", "status": msg.status, "to": body.to_email}


@router.get("/messages/inbox")
def unified_inbox(business: str | None = None, label: str | None = None,
                  db: Session = Depends(get_db), _=Depends(_read)):
    """Unified inbox: every prospect reply across all businesses, with an AI label,
    summary, and the drafted reply ready to send. Filter by business or label."""
    from .. import unified_inbox as ui
    return ui.feed(db, business=business, label=label)


@router.post("/inbound/sync")
def sync_inbound(newer_than_days: int = 3, db: Session = Depends(get_db), _=Depends(_write)):
    """Pull recent replies from both mailboxes and mark matching records as Replied."""
    return inbound.sync_replies(db, newer_than_days=newer_than_days)


@router.post("/followups/run")
def run_followups(db: Session = Depends(get_db), _=Depends(_write)):
    """Send all due follow-ups now (skips anyone who replied)."""
    return followups.process_due_followups(db)


@router.post("/followups/nudge-bookings")
def nudge_bookings(db: Session = Depends(get_db), _=Depends(_write)):
    """Nudge interested-but-not-booked prospects toward the calendar (one per lead)."""
    from .. import booking_nudge
    return {"ok": True, **booking_nudge.run(db)}


@router.get("/followups")
def list_followups(limit: int = 200, db: Session = Depends(get_db), _=Depends(_read)):
    """Every contacted prospect's pending follow-up — who to follow up with, when,
    which step, and whether it's due now. The single place to manage follow-ups."""
    from datetime import date
    from ..models import FollowUp
    rows = (db.query(FollowUp).filter(FollowUp.completed.is_(False))
            .order_by(FollowUp.due_date).limit(limit).all())
    today = date.today()
    items = []
    for fu in rows:
        name, _ctx = followups._entity_context(db, fu.entity_type, fu.entity_id)
        # Recipient + last touch from the first outreach message for this entity.
        msgs = (db.query(Message).filter(Message.entity_type == fu.entity_type,
                Message.entity_id == fu.entity_id).all())
        to_email = next((m.to_email for m in msgs if m.to_email), None)
        if not to_email:
            continue  # nothing to follow up with
        replied = any(m.status == "Replied" for m in msgs)
        last_sent = max((m.sent_at or m.created_at for m in msgs if m.direction == "outbound"),
                        default=None)
        items.append({
            "id": str(fu.id), "entity_type": fu.entity_type,
            "name": name or to_email, "to": to_email, "step": fu.step,
            "due_date": fu.due_date.isoformat() if fu.due_date else None,
            "due": bool(fu.due_date and fu.due_date <= today),
            "replied": replied,
            "last_sent": last_sent.isoformat() if last_sent else None,
        })
    due = sum(1 for i in items if i["due"] and not i["replied"])
    return {"due": due, "total": len(items), "items": items}
