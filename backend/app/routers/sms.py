"""SMS endpoints: send, inbound webhook, and WhatsApp-style threads."""
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import sms_engine
from ..database import get_db
from ..integrations import sms
from ..models import Lead, ManualContact, Message, Restaurant
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


def _norm(phone: str | None) -> str:
    """Last 10 digits — so '+1 (617) 555-1234', '6175551234' and '1-617-555-1234'
    all match regardless of how the number was stored/sourced."""
    return re.sub(r"\D", "", phone or "")[-10:]


def _contact_name(db: Session, phone: str) -> str | None:
    """Resolve a display name for a phone across leads, restaurants AND imported
    contacts, matching on the normalized (last-10-digit) number."""
    key = _norm(phone)
    if not key:
        return None
    # ManualContact first — imported personal contacts carry real names.
    for c in db.query(ManualContact).filter(ManualContact.phone.isnot(None)).all():
        if _norm(c.phone) == key:
            return c.name
    for l in db.query(Lead).filter(Lead.phone.isnot(None)).all():
        if _norm(l.phone) == key:
            return l.owner_name or l.company_name
    for r in db.query(Restaurant).filter(Restaurant.phone.isnot(None)).all():
        if _norm(r.phone) == key:
            return r.name
    return None


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
    # Pick up any Twilio creds connected via the in-app Setup page (multi-instance safe).
    try:
        from .. import runtime_config
        runtime_config.apply_to_settings(db)
    except Exception:
        pass
    from ..config import settings
    # A hard opt-out (STOP) is a legal line — never text an opted-out number,
    # even on a manual send. Hours/cap are NOT enforced here: a human replying
    # in an active thread is exempt, and the guard would only get in the way.
    if sms_engine.is_opted_out(db, body.to):
        return {"ok": False, "sid": None, "status": "Blocked",
                "reason": "This number opted out (texted STOP) — we can't text them."}
    sid, err = sms.send_with_error(body.to, body.message, account=body.account)
    bridge_on = bool(settings.bridge_token)
    # Sent via Twilio → Sent; else if a Mac bridge is configured → Queued (it'll
    # deliver from your real number); else there's nowhere to send → Drafted.
    status = "Sent" if sid else ("Queued" if bridge_on else "Drafted")
    msg = Message(channel="sms", direction="outbound", entity_type=body.entity_type,
                  entity_id=body.entity_id, to_email=body.to, from_account=body.account,
                  body=body.message, status=status, provider_id=sid,
                  sent_at=datetime.now(timezone.utc) if sid else None)
    db.add(msg)
    db.commit()
    ok = bool(sid) or bridge_on
    reason = None if ok else (err or "SMS isn't connected — add Twilio in Connect Email & Data.")
    return {"ok": ok, "sid": sid, "status": status, "reason": reason}


class SmsSendDrafts(BaseModel):
    account: str | None = None
    limit: int = 20


@router.post("/sms/send-drafts")
def send_drafts(body: SmsSendDrafts, db: Session = Depends(get_db), _=Depends(_write)):
    """Send N drafted texts in one click, HOT LEADS FIRST (e.g. the EverQuote batch's
    per-lead SMS). Paced and compliance-gated: opted-out numbers, out-of-hours,
    and the daily cap are all honored, and each skip reports its real reason."""
    return sms_engine.send_sms_drafts(db, limit=body.limit, account=body.account)


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
