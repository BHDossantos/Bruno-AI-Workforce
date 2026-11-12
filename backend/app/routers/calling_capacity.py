"""Administrative setup and signed callbacks for opt-in capacity calling."""
from datetime import datetime, timedelta, timezone
from uuid import UUID
from xml.sax.saxutils import escape, quoteattr
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, AwareDatetime, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session
from .. import calling_capacity as capacity, control
from ..callback_auth import require_twilio_callback
from ..calling_capacity_models import CallHandler, CallPermit, CallReservation
from ..config import settings
from ..database import get_db
from ..models import Lead
from ..security import require_role

router = APIRouter(prefix="/calls/capacity", tags=["capacity calling"])
_admin = require_role("admin")
_read = require_role("admin", "operator", "viewer")
STATES = set("AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split())


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    phone: str = Field(pattern=r"^\+1[2-9][0-9]{9}$")
    authorization_ref: str = Field(min_length=3, max_length=1000)
    expires_at: AwareDatetime

    @field_validator("expires_at")
    @classmethod
    def current_evidence(cls, value):
        now = datetime.now(timezone.utc)
        if not now < value <= now + timedelta(days=90):
            raise ValueError("Evidence must expire within the next 90 days")
        return value


class HandlerInput(Evidence):
    states: list[str] = Field(min_length=1, max_length=51)

    @field_validator("states")
    @classmethod
    def valid_states(cls, values):
        if any(s not in STATES for s in values):
            raise ValueError("Explicit verified US state codes required")
        return sorted(set(values))


class PermitInput(Evidence):
    state: str
    recipient_timezone: str

    @field_validator("recipient_timezone")
    @classmethod
    def valid_timezone(cls, value):
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Verified recipient IANA timezone required")
        return value


    @field_validator("state")
    @classmethod
    def valid_state(cls, value):
        if value not in STATES:
            raise ValueError("Verified recipient state required")
        return value


class Availability(BaseModel):
    seconds: int = Field(ge=0, le=900)


@router.post("/handlers")
def handler_setup(body: HandlerInput, db: Session = Depends(get_db), _=Depends(_admin)):
    row = db.scalar(select(CallHandler).where(CallHandler.phone == body.phone).with_for_update())
    if row and row.reservation_id:
        raise HTTPException(409, "Handler has an unresolved call; cannot change licensing or destination")
    if not row:
        row = CallHandler(phone=body.phone)
        db.add(row)
    row.states, row.authorization_ref = body.states, body.authorization_ref
    row.verified_until, row.available_until = body.expires_at, None
    db.commit()
    return {"id": str(row.id), "available": False, "calling_enabled": settings.auto_dial_capacity_enabled}


@router.post("/handlers/{handler_id}/availability")
def available(handler_id: UUID, body: Availability, db: Session = Depends(get_db), _=Depends(_admin)):
    row = db.get(CallHandler, handler_id)
    if not row:
        raise HTTPException(404, "Handler not found")
    row.available_until = datetime.now(timezone.utc) + timedelta(seconds=body.seconds)
    db.commit()
    return {"available_until": row.available_until, "busy": row.reservation_id is not None}


@router.post("/leads/{lead_id}/permission")
def permit_setup(lead_id: UUID, body: PermitInput, db: Session = Depends(get_db), _=Depends(_admin)):
    from ..integrations.sms import _e164
    lead = db.get(Lead, lead_id)
    if not lead or lead.segment not in {"commercial", "personal"}:
        raise HTTPException(404, "Insurance lead not found")
    if body.phone != _e164(lead.phone):
        raise HTTPException(409, "Permission must match the current lead phone")
    row = db.get(CallPermit, lead_id)
    if not row:
        row = CallPermit(lead_id=lead_id)
        db.add(row)
    for key, value in body.model_dump().items():
        setattr(row, key, value)
    db.commit()
    return {"lead_id": str(lead_id), "outreach_enqueued": 0}


@router.get("/status")
def status(db: Session = Depends(get_db), _=Depends(_read)):
    rows = db.scalars(select(CallReservation).where(CallReservation.status != "terminal").limit(200)).all()
    return {"enabled": settings.auto_dial_capacity_enabled, "mode": "one_handler_per_leg",
            "unresolved": [{"id": str(r.id), "status": r.status, "provider_id": r.provider_id,
                            "created_at": r.created_at} for r in rows], "limit": 200}


def xml(content):
    return Response('<?xml version="1.0" encoding="UTF-8"?><Response>' + content + '</Response>', media_type="application/xml")


@router.post("/amd", dependencies=[Depends(require_twilio_callback)])
async def amd(request: Request, reservation_id: UUID, db: Session = Depends(get_db)):
    form = await request.form()
    sid, answered = str(form.get("CallSid") or ""), str(form.get("AnsweredBy") or "").lower()
    # Never treat uncertain machine classification as confirmed live answer.
    if answered != "human" or not settings.auto_dial_capacity_enabled or control.is_paused_safe(db):
        return xml('<Hangup/>')
    target = capacity.transfer_target(db, reservation_id, sid)
    if not target:
        return xml('<Say>No representative is available. Goodbye.</Say><Hangup/>')
    from ..integrations.twilio_voice import _base_url, bridge_caller_id
    base = _base_url()
    if not base:
        return xml('<Hangup/>')
    # No recording is introduced, no false quote request or callback promise.
    action = f"{base}/calls/capacity/transfer-result?reservation_id={reservation_id}"
    return xml('<Say>Please hold while we connect you.</Say>'
               f'<Dial answerOnBridge="true" timeout="20" callerId={quoteattr(bridge_caller_id(target))} '
               f'action={quoteattr(action)}>{escape(target)}</Dial>')


@router.post("/transfer-result", dependencies=[Depends(require_twilio_callback)])
async def transfer_result(request: Request, reservation_id: UUID, db: Session = Depends(get_db)):
    form = await request.form()
    # Keep the slot until the parent leg has a terminal status. A late child-leg
    # callback must not free a handler while the parent call is still active.
    if not capacity.callback(db, reservation_id, str(form.get("CallSid") or ""), "answered"):
        return xml('<Hangup/>')
    if form.get("DialCallStatus") == "completed":
        return xml('<Hangup/>')
    return xml('<Say>We could not connect you to a representative. Goodbye.</Say><Hangup/>')


@router.post("/status", dependencies=[Depends(require_twilio_callback)])
async def provider_status(request: Request, reservation_id: UUID, db: Session = Depends(get_db)):
    form = await request.form()
    sid, state = str(form.get("CallSid") or ""), str(form.get("CallStatus") or "").lower()
    capacity.callback(db, reservation_id, sid, state)
    # Preserve the existing message timeline. The capacity fence is handled even
    # when the provider callback beats creation of the Message row.
    from .calls import call_status
    await call_status(request, db=db)
    return xml('')
