"""Outbox + inbound sync routes.

Lists outbound messages (sent / drafted), lets an operator approve & send a
drafted message through the correct Gmail account, and triggers inbound reply
sync across both mailboxes.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import followups, inbound
from ..database import get_db
from ..integrations import gmail
from ..models import Message
from ..schemas import MessageOut
from ..security import require_role

router = APIRouter(tags=["messages"])
_read = require_role("admin", "operator", "viewer")
_write = require_role("admin", "operator")


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
    if not gmail.is_configured(msg.from_account):
        raise HTTPException(status_code=400, detail=f"Gmail account '{msg.from_account}' not configured")
    mid = gmail.send_message(msg.to_email, msg.subject or "", msg.body or "", account=msg.from_account)
    if not mid:
        raise HTTPException(status_code=502, detail="Gmail send failed")
    msg.provider_id = mid
    msg.approved = True
    msg.status = "Sent"
    msg.sent_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(msg)
    return msg


@router.post("/inbound/sync")
def sync_inbound(newer_than_days: int = 3, db: Session = Depends(get_db), _=Depends(_write)):
    """Pull recent replies from both mailboxes and mark matching records as Replied."""
    return inbound.sync_replies(db, newer_than_days=newer_than_days)


@router.post("/followups/run")
def run_followups(db: Session = Depends(get_db), _=Depends(_write)):
    """Send all due follow-ups now (skips anyone who replied)."""
    return followups.process_due_followups(db)
