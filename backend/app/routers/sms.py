"""SMS endpoints: send, inbound webhook, and WhatsApp-style threads."""
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, Response, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import sms_engine, outbound_guard
from ..database import get_db
from ..callback_auth import require_twilio_callback, require_plivo_callback
from ..integrations import sms
from ..models import Lead, ManualContact, Message, Restaurant
from ..security import require_role

router = APIRouter(tags=["sms"])
_read = require_role("admin", "operator", "viewer")
_write = require_role("admin", "operator")


@router.get("/sms/diagnostics")
def diagnostics(db: Session = Depends(get_db), _=Depends(_read)):
    """Show EXACTLY what the app will send to the carrier — the active provider and
    the real 'From' number it uses per account (and whether that number is valid
    E.164) — so a send failure can be pinned to a specific cause instead of guessed.
    Phone numbers are not secrets; API tokens are never returned."""
    from .. import runtime_config
    from ..config import settings
    from ..integrations import telco, twilio_voice, voice
    try:
        runtime_config.apply_to_settings(db)  # reflect numbers saved in Setup
    except Exception:
        pass
    prov = telco.provider("sms")
    accounts = {}
    for acct in ("insurance", "personal"):
        raw = sms.number_for(acct)
        e164 = sms._e164(raw)
        accounts[acct] = {
            "from_number_configured": raw or None,
            "from_number_e164": e164 or None,
            "from_is_valid": bool(e164),
        }
    # Voice (calling) side — the outbound caller-ID + bridge number the dialer uses.
    v_num = twilio_voice._voice_number()
    v_e164 = sms._e164(v_num)
    voice_info = {
        "connected": voice.is_configured(),
        "provider": telco.label("voice") if telco.provider("voice") else None,
        "caller_id": v_num or None,
        "caller_id_e164": v_e164 or None,
        "caller_id_valid": bool(v_e164),
        "callback_set": bool((settings.producer_callback or settings.producer_cell or "").strip()),
        "voicemail_recorded": voice.voicemail_configured(),
    }
    return {
        "provider": telco.label("sms") if prov else None,
        "connected": bool(prov),
        # Which SignalWire number fields are set (values shown — they're not secret).
        "signalwire": {
            "space_url": (settings.signalwire_space_url or "") or None,
            "project_id_set": bool((settings.signalwire_project_id or "").strip()),
            "api_token_set": bool((settings.signalwire_api_token or "").strip()),
            "from_number": (settings.signalwire_from_number or "") or None,
            "insurance_number": (settings.signalwire_insurance_number or "") or None,
        },
        # Twilio fields (values shown are not secret; tokens are only shown as set/unset).
        "twilio": {
            "account_sid_set": bool((settings.twilio_account_sid or "").strip()),
            "auth_token_set": bool((settings.twilio_auth_token or "").strip()),
            "from_number": (settings.twilio_from_number or "") or None,
            "insurance_number": (settings.twilio_insurance_number or "") or None,
            "voice_number": (settings.twilio_voice_number or "") or None,
        },
        "voice": voice_info,
        "accounts": accounts,
        "daily_cap": settings.sms_daily_send_cap,
        "sent_today": sms_engine.sms_sent_today(db),
        "send_window": f"{settings.sms_send_window_start}:00-{settings.sms_send_window_end}:00 "
                       f"{settings.sms_timezone}",
        "note": ("If a send fails with 'to must send to a verified caller id' while the "
                 "From number here is valid and owned in your SignalWire project, the "
                 "block is on the destination — the number/campaign needs 10DLC "
                 "registration completed in SignalWire for unrestricted US sending."),
    }


class SmsSend(BaseModel):
    to: str
    message: str = Field(min_length=1)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=128)

    @field_validator("message")
    @classmethod
    def nonblank_message(cls, value):
        if not value.strip():
            raise ValueError("Message cannot be empty or whitespace")
        return value

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
                      "delivery_status": m.delivery_status,
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
    from uuid import UUID
    target = sms._e164(body.to)
    if not target:
        raise HTTPException(422, "Invalid recipient phone")
    # The Message row is the persisted request intent. A caller rollback recreates
    # the same UUID, so the independent provider reservation still deduplicates it.
    intent = body.idempotency_key or outbound_guard.digest(target, body.message)
    request_key = outbound_guard.digest("sms-request", body.account, intent)
    message_id = UUID(request_key[:32])
    outbound_guard.persist_message_intent(dict(
        id=message_id, channel="sms", direction="outbound", entity_type=body.entity_type,
        entity_id=body.entity_id, to_email=target, from_account=body.account,
        body=body.message, status="Drafted", approved=False))
    msg = db.query(Message).filter(Message.id == message_id).populate_existing().with_for_update().one()
    if msg.to_email != target or msg.body != body.message or msg.entity_type != body.entity_type or str(msg.entity_id or "") != str(body.entity_id or ""):
        raise HTTPException(409, "Idempotency key belongs to a different SMS payload")
    if msg.status not in ("Drafted", "Approved"):
        return {"ok": msg.status in ("Sent", "Queued"), "sid": msg.provider_id,
                "message_id": str(msg.id), "status": msg.status,
                "reason": None if msg.status in ("Sent", "Queued") else "Original intent is held or closed; review it before a new action"}
    carrier_available = sms.is_configured()
    sid, err = (sms.send_with_error(target, body.message, account=body.account,
                                   operation_key=f"message:{msg.id}", replay_accepted=True)
                if carrier_available else (None, "No SMS carrier configured"))
    bridge_on = bool(settings.bridge_token) and not carrier_available
    status = "Sent" if sid else ("Queued" if bridge_on else "Drafted" if not carrier_available or outbound_guard.retryable_without_reconciliation(err) else "Needs Review")
    msg.status, msg.provider_id = status, sid
    msg.sent_at = datetime.now(timezone.utc) if sid else None
    db.commit()
    ok = bool(sid) or bridge_on
    reason = None if ok else (err or "SMS isn't connected — configure a carrier or the Mac bridge.")
    return {"ok": ok, "sid": sid, "message_id": str(msg.id), "status": status, "reason": reason}



class SmsSendDrafts(BaseModel):
    account: str | None = None
    limit: int = 20


@router.post("/sms/send-drafts")
def send_drafts(body: SmsSendDrafts, db: Session = Depends(get_db), _=Depends(_write)):
    """Send N drafted texts in one click, HOT LEADS FIRST (e.g. the EverQuote batch's
    per-lead SMS). Paced and compliance-gated: opted-out numbers, out-of-hours,
    and the daily cap are all honored, and each skip reports its real reason."""
    return sms_engine.send_sms_drafts(db, limit=body.limit, account=body.account)


@router.post("/sms/status", dependencies=[Depends(require_twilio_callback)])
async def sms_status(request: Request, db: Session = Depends(get_db)):
    """Twilio delivery-status webhook (public). Records whether the text actually
    landed — delivered / undelivered / failed (+ error) — onto the Message, so the
    UI can show real delivery instead of just 'Sent'."""
    form = await request.form()
    sid = form.get("MessageSid") or form.get("SmsSid")
    st = (form.get("MessageStatus") or form.get("SmsStatus") or "").strip().lower()
    err = form.get("ErrorCode")
    if sid and st:
        msg = (db.query(Message).filter(Message.provider_id == sid, Message.channel == "sms")
               .first())
        if msg:
            msg.delivery_status = st + (f" (error {err})" if err and err not in ("0", "") else "")
            db.commit()
    return Response(content="", media_type="application/xml")


@router.post("/sms/inbound", dependencies=[Depends(require_twilio_callback)])
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


@router.post("/sms/plivo-inbound", dependencies=[Depends(require_plivo_callback)])
async def plivo_inbound(request: Request, db: Session = Depends(get_db)):
    """Plivo inbound-SMS webhook (public). Same as the Twilio one but Plivo posts
    'From'/'Text' — point your Plivo Application's Message URL here so replies land
    on the lead's profile just like Twilio."""
    form = await request.form()
    phone = form.get("From")
    text = form.get("Text")
    if phone and text:
        sms_engine.record_inbound(db, phone=phone, body=text)
    return Response(content="", media_type="text/plain")


@router.post("/sms/plivo-status", dependencies=[Depends(require_plivo_callback)])
async def plivo_status(request: Request, db: Session = Depends(get_db)):
    """Plivo delivery-status callback (public) — records whether a text actually
    landed (delivered/undelivered/failed) onto the Message, mirroring /sms/status."""
    form = await request.form()
    mid = form.get("MessageUUID") or form.get("message_uuid")
    st = (form.get("Status") or form.get("status") or "").strip().lower()
    if mid and st:
        msg = (db.query(Message).filter(Message.provider_id == mid, Message.channel == "sms")
               .first())
        if msg:
            msg.delivery_status = st
            db.commit()
    return Response(content="", media_type="text/plain")
