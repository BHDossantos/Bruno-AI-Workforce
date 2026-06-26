"""iMessage bridge API.

A helper running on the user's Mac polls these endpoints and sends/receives SMS
through Messages.app — so texts go out from the user's REAL number (free, no
Twilio). Authenticated with a single shared secret in the X-Bridge-Token header
(set BRIDGE_TOKEN). Endpoints are intentionally NOT behind the user login because
the Mac helper is a machine client.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import Message

router = APIRouter(prefix="/bridge", tags=["bridge"])


def _auth(token: str | None) -> None:
    if not settings.bridge_token or token != settings.bridge_token:
        raise HTTPException(status_code=401, detail="Invalid or missing bridge token")


@router.get("/outbox")
def outbox(x_bridge_token: str | None = Header(default=None),
           limit: int = 50, db: Session = Depends(get_db)):
    """Outbound texts waiting to be sent from the Mac (queued, not yet sent)."""
    _auth(x_bridge_token)
    rows = (db.query(Message).filter(
        Message.channel == "sms", Message.direction == "outbound",
        Message.status.in_(("Queued", "Drafted")), Message.sent_at.is_(None),
        Message.to_email.isnot(None)).order_by(Message.created_at.asc()).limit(limit).all())
    return [{"id": str(m.id), "to": m.to_email, "body": m.body or ""} for m in rows]


class SentBody(BaseModel):
    id: str


@router.post("/sent")
def mark_sent(body: SentBody, x_bridge_token: str | None = Header(default=None),
              db: Session = Depends(get_db)):
    """Mark a queued text as sent once the Mac has delivered it."""
    _auth(x_bridge_token)
    m = db.query(Message).filter(Message.id == body.id).first()
    if not m:
        raise HTTPException(404, "message not found")
    m.status = "Sent"
    m.sent_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True, "id": body.id}


class InboundBody(BaseModel):
    model_config = {"populate_by_name": True}
    from_: str = Field(alias="from")  # JSON key is "from" (a Python keyword)
    body: str


@router.post("/inbound")
def inbound(body: InboundBody, x_bridge_token: str | None = Header(default=None),
            db: Session = Depends(get_db)):
    """Record an incoming text the Mac read from Messages — runs the same
    warm-lead/reply handling as the Twilio inbound webhook."""
    _auth(x_bridge_token)
    from .. import sms_engine
    phone = (body.from_ or "").strip()
    if not phone or not (body.body or "").strip():
        raise HTTPException(400, "from and body required")
    msg = sms_engine.record_inbound(db, phone=phone, body=body.body)
    return {"ok": True, "id": str(msg.id), "status": msg.status}
