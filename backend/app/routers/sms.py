"""SMS endpoints: send, inbound webhook, and WhatsApp-style threads."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import sms_engine
from ..database import get_db
from ..integrations import sms
from ..models import Lead, Message, Restaurant
from ..security import require_role

router = APIRouter(tags=["sms"])
_read = require_role("admin", "operator", "viewer")
_write = require_role("admin", "operator")


class SmsSend(BaseModel):
    to: str
    message: str
    account: str = "personal"
    entity_type: str | None = None
    entity_id: str | None = None


def _contact_name(db: Session, phone: str) -> str | None:
    lead = db.query(Lead).filter(Lead.phone == phone).first()
    if lead:
        return lead.company_name or lead.owner_name
    rest = db.query(Restaurant).filter(Restaurant.phone == phone).first()
    return rest.name if rest else None


@router.get("/sms/threads")
def threads(db: Session = Depends(get_db), _=Depends(_read)):
    """One row per phone conversation: latest message + count."""
    rows = (db.query(Message.to_email, func.max(Message.created_at).label("last"),
                     func.count().label("n"))
            .filter(Message.channel == "sms", Message.to_email.isnot(None))
            .group_by(Message.to_email).order_by(func.max(Message.created_at).desc()).all())
    out = []
    for phone, last, n in rows:
        last_msg = (db.query(Message).filter(Message.channel == "sms", Message.to_email == phone)
                    .order_by(Message.created_at.desc()).first())
        out.append({
            "phone": phone, "name": _contact_name(db, phone), "count": n,
            "last_at": last.isoformat() if last else None,
            "last_body": last_msg.body if last_msg else None,
            "last_direction": last_msg.direction if last_msg else None,
        })
    return out


@router.get("/sms/thread")
def thread(phone: str, db: Session = Depends(get_db), _=Depends(_read)):
    """Full message history for one phone number (oldest first)."""
    msgs = (db.query(Message).filter(Message.channel == "sms", Message.to_email == phone)
            .order_by(Message.created_at).all())
    return {
        "phone": phone, "name": _contact_name(db, phone),
        "messages": [{"direction": m.direction, "body": m.body, "status": m.status,
                      "at": m.created_at.isoformat() if m.created_at else None} for m in msgs],
    }


@router.post("/sms/send")
def send(body: SmsSend, db: Session = Depends(get_db), _=Depends(_write)):
    sid = sms.send_sms(body.to, body.message, account=body.account)
    msg = Message(channel="sms", direction="outbound", entity_type=body.entity_type,
                  entity_id=body.entity_id, to_email=body.to, from_account=body.account,
                  body=body.message, status="Sent" if sid else "Drafted", provider_id=sid,
                  sent_at=datetime.now(timezone.utc) if sid else None)
    db.add(msg)
    db.commit()
    return {"ok": bool(sid), "sid": sid, "status": msg.status}


@router.post("/sms/inbound")
async def inbound(request: Request, db: Session = Depends(get_db)):
    """Twilio inbound-SMS webhook (public). Stores the text + links the contact."""
    form = await request.form()
    phone = form.get("From")
    text = form.get("Body")
    if phone and text:
        sms_engine.record_inbound(db, phone=phone, body=text)
    # Empty TwiML — we reply from the app, not auto.
    return Response(content="<?xml version=\"1.0\" encoding=\"UTF-8\"?><Response></Response>",
                    media_type="application/xml")
