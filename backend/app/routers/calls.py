"""Calling — place a recorded call to a lead and capture AI notes.

Two entry points:
  • POST /calls/lead/{id}  → bridge: Twilio rings YOUR phone, then dials the lead.
  • GET  /calls/token      → a Twilio Voice token for the browser softphone.

Plus the public Twilio webhooks (TwiML + status + recording) that bridge the
call, play the consent notice, and hand the finished recording to the AI
note-taker. Webhooks are public because Twilio calls them.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..integrations import twilio_voice as voice
from ..models import Lead, Message
from ..security import require_role

router = APIRouter(prefix="/calls", tags=["calls"])
_write = require_role("admin", "operator")
_read = require_role("admin", "operator", "viewer")

_XML = "application/xml"


def _refresh(db: Session) -> None:
    try:
        from .. import runtime_config
        runtime_config.apply_to_settings(db)
    except Exception:
        pass


@router.post("/lead/{lead_id}")
def call_lead(lead_id: str, db: Session = Depends(get_db), _=Depends(_write)):
    """Ring the producer's phone, then bridge to this lead (recorded)."""
    _refresh(db)
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(404, "Lead not found")
    if not lead.phone:
        raise HTTPException(400, "This lead has no phone on file")
    sid, err = voice.place_bridge_call(lead.phone, str(lead.id))
    if not sid:
        raise HTTPException(400, f"Couldn't start the call — {err}")
    db.add(Message(channel="call", direction="outbound", entity_type="lead",
                   entity_id=lead.id, from_account="insurance",
                   body="📞 Call started (ringing your phone)…", status="Dialing",
                   provider_id=sid, sent_at=datetime.now(timezone.utc)))
    db.commit()
    return {"ok": True, "call_sid": sid,
            "message": "Calling your phone now — pick up to be connected to the lead."}


@router.get("/token")
def browser_token(db: Session = Depends(get_db), _=Depends(_read)):
    """Short-lived Twilio Voice token for the in-browser softphone."""
    _refresh(db)
    if not voice.browser_configured():
        raise HTTPException(400, "Browser calling not set up — add a Twilio API Key + "
                                 "TwiML App SID on Setup.")
    tok = voice.access_token("bruno-agent")
    if not tok:
        raise HTTPException(400, "Could not mint a voice token.")
    return {"token": tok, "identity": "bruno-agent"}


# ── Public Twilio webhooks ────────────────────────────────────────────────────
@router.post("/twiml/bridge")
def twiml_bridge(lead_phone: str = "", lead_id: str = "", db: Session = Depends(get_db)):
    """Returned to Twilio after YOU answer — dials + records the lead. Refreshes the
    connected Twilio config first: this webhook can land on a Cloud Run instance that
    never loaded the voice number from the DB, which left callerId empty and made
    Twilio reject the <Dial> — so the call dropped the moment you picked up."""
    _refresh(db)
    return Response(voice.bridge_twiml(lead_phone, lead_id or None), media_type=_XML)


@router.post("/twiml/announce")
def twiml_announce():
    """Played to the lead on answer — the recording-consent notice."""
    return Response(voice.announce_twiml(), media_type=_XML)


@router.post("/twiml/outbound")
async def twiml_outbound(request: Request, db: Session = Depends(get_db)):
    """TwiML App voiceUrl for the browser softphone — dials the number the SDK
    passed as 'To'."""
    _refresh(db)  # load the connected voice number so callerId isn't empty
    form = await request.form()
    to = (form.get("To") or "").strip()
    lead_id = (form.get("lead_id") or "").strip()
    if not to:
        return Response(voice._xml("<Say>No number to call.</Say>"), media_type=_XML)
    return Response(voice.outbound_twiml(to, lead_id or None), media_type=_XML)


@router.post("/dial-status")
async def dial_status(request: Request, lead_id: str = "", db: Session = Depends(get_db)):
    """<Dial action> callback — the real outcome of dialing the lead (completed /
    no-answer / busy / failed). Records it on the call row so a dropped call shows
    WHY, and returns empty TwiML so the call just ends. CallSid here is the parent
    (producer) leg = the sid we stored when we placed the call."""
    form = await request.form()
    sid = form.get("CallSid")
    dial = (form.get("DialCallStatus") or "").strip().lower()
    if sid and dial:
        msg = db.query(Message).filter(Message.provider_id == sid,
                                       Message.channel == "call").first()
        if msg:
            msg.delivery_status = dial
            if dial != "completed" and msg.status == "Dialing":
                msg.status = "Missed"
            db.commit()
    return Response("", media_type=_XML)


@router.post("/status")
async def call_status(request: Request, lead_id: str = "", db: Session = Depends(get_db)):
    """Call status callback — mark the call row done when it completes."""
    form = await request.form()
    sid = form.get("CallSid")
    status = form.get("CallStatus")
    if sid and status in ("completed", "busy", "no-answer", "failed", "canceled"):
        msg = db.query(Message).filter(Message.provider_id == sid,
                                       Message.channel == "call").first()
        if msg and msg.status == "Dialing":
            msg.status = "Sent" if status == "completed" else "Missed"
            db.commit()
    return Response("", media_type=_XML)


@router.post("/recording")
async def call_recording(request: Request, lead_id: str = "", db: Session = Depends(get_db)):
    """Recording-ready callback → transcribe + AI-summarize + log to the lead."""
    form = await request.form()
    rec_url = form.get("RecordingUrl")
    duration = form.get("RecordingDuration")
    sid = form.get("CallSid")
    if not rec_url:
        return Response("", media_type=_XML)
    _refresh(db)
    try:
        from .. import call_intelligence
        call_intelligence.process_recording(
            db, lead_id=lead_id or None, recording_url=rec_url,
            duration=int(duration) if (duration or "").isdigit() else None, call_sid=sid)
    except Exception:  # never 500 a Twilio webhook
        db.rollback()
    return Response("", media_type=_XML)
