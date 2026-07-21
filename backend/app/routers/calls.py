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
from ..integrations import plivo_voice, sip_voice, vonage_voice
from ..integrations import twilio_voice as voice
from ..integrations import voice as vdispatch  # provider dispatcher (Plivo/Vonage/SIP/Twilio)
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


@router.post("/test")
def test_call(db: Session = Depends(get_db), _=Depends(_write)):
    """Place a one-tap TEST call to your own cell — proves the carrier creds +
    caller-ID + callback number all work, without dialing a real lead. Surfaces the
    exact carrier error if it fails, so setup is verifiable in seconds."""
    _refresh(db)
    from ..integrations import twilio_voice
    sid, err = twilio_voice.place_test_call()
    if not sid:
        raise HTTPException(400, err or "Test call failed.")
    return {"ok": True, "call_sid": sid,
            "message": "Calling your phone now — pick up to hear the confirmation."}


@router.post("/twiml/test")
def twiml_test():
    """TwiML the carrier fetches for the test call — a spoken confirmation."""
    from ..integrations import twilio_voice
    return Response(twilio_voice.test_twiml(), media_type=_XML)


@router.post("/lead/{lead_id}")
def call_lead(lead_id: str, db: Session = Depends(get_db), _=Depends(_write)):
    """Ring the producer's phone, then bridge to this lead (recorded)."""
    _refresh(db)
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(404, "Lead not found")
    if not lead.phone:
        raise HTTPException(400, "This lead has no phone on file")
    sid, err = vdispatch.place_bridge_call(lead.phone, str(lead.id))
    if not sid:
        raise HTTPException(400, f"Couldn't start the call — {err}")
    db.add(Message(channel="call", direction="outbound", entity_type="lead",
                   entity_id=lead.id, from_account="insurance",
                   body="📞 Call started (ringing your phone)…", status="Dialing",
                   provider_id=sid, sent_at=datetime.now(timezone.utc)))
    db.commit()
    return {"ok": True, "call_sid": sid,
            "message": "Calling your phone now — pick up to be connected to the lead."}


@router.post("/auto/{lead_id}")
def auto_call_lead(lead_id: str, db: Session = Depends(get_db), _=Depends(_write)):
    """Auto-dial the lead: a human answer transfers to your phone; voicemail gets your
    recorded drop. One call, hands-free."""
    _refresh(db)
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(404, "Lead not found")
    if not lead.phone:
        raise HTTPException(400, "This lead has no phone on file")
    sid, err = vdispatch.place_auto_call(lead.phone, str(lead.id))
    if not sid:
        raise HTTPException(400, f"Couldn't start the call — {err}")
    vm = "your recorded voicemail" if voice.voicemail_configured() else "a spoken message"
    db.add(Message(channel="call", direction="outbound", entity_type="lead",
                   entity_id=lead.id, from_account="insurance",
                   body=f"📞 Auto-dialing — transfers to you if answered, leaves {vm} if not…",
                   status="Dialing", provider_id=sid, sent_at=datetime.now(timezone.utc)))
    db.commit()
    return {"ok": True, "call_sid": sid,
            "message": "Auto-dialing the lead — your phone rings if they pick up; "
                       f"otherwise it leaves {vm}."}


@router.post("/auto-dial-run")
def auto_dial_run(db: Session = Depends(get_db), _=Depends(_write)):
    """Run the daily auto-dial pass right now (the same worker the 8am scheduler fires):
    auto-dials the Call List hottest-first, transfers live answers to your phone and
    drops your voicemail otherwise. Returns how many it placed / why it skipped."""
    _refresh(db)
    from .. import auto_dial
    result = auto_dial.run(db)
    placed = result.get("placed")
    if placed is None:
        return {"ok": True, "ran": False,
                "message": f"Auto-dial didn't run — {result.get('skipped', 'unknown')}.",
                **result}
    return {"ok": True, "ran": True,
            "message": f"Auto-dialing {placed} lead(s) now — your phone rings on a live "
                       "answer; voicemail gets your drop.",
            **result}


@router.post("/record-voicemail")
def record_voicemail(db: Session = Depends(get_db), _=Depends(_write)):
    """Ring your phone so you can record the voicemail drop in your own voice."""
    _refresh(db)
    sid, err = vdispatch.record_voicemail_call()
    if not sid:
        raise HTTPException(400, f"Couldn't start the recording call — {err}")
    return {"ok": True, "message": "Calling your phone now — record your voicemail after the beep, "
                                   "then press #. It'll be used on every voicemail drop."}


@router.get("/voicemail-status")
def voicemail_status(db: Session = Depends(get_db), _=Depends(_read)):
    """Whether a voicemail drop is recorded (for the Setup UI)."""
    _refresh(db)
    from ..config import settings
    return {"recorded": voice.voicemail_configured(), "url": settings.producer_voicemail_url or None}


@router.get("/health")
def calling_health(db: Session = Depends(get_db), _=Depends(_read)):
    """Calling health for the Call List dashboard: which provider places calls, how
    many went out today / this week, the connect vs voicemail-or-missed split, and
    the connect rate — the calling equivalent of the email deliverability screen."""
    _refresh(db)
    from datetime import date, timedelta
    from sqlalchemy import func

    from ..config import settings
    start = datetime.combine(date.today(), datetime.min.time(), tzinfo=timezone.utc)
    week = start - timedelta(days=6)

    def _counts(since):
        rows = dict(db.query(Message.status, func.count()).filter(
            Message.channel == "call", Message.direction == "outbound",
            Message.sent_at >= since).group_by(Message.status).all())
        connected = int(rows.get("Sent", 0))
        missed = int(rows.get("Missed", 0))
        dialing = int(rows.get("Dialing", 0))
        finished = connected + missed
        rate = round(100.0 * connected / finished, 1) if finished else 0.0
        return {"placed": connected + missed + dialing, "connected": connected,
                "missed": missed, "dialing": dialing, "connect_rate": rate}

    today = _counts(start)
    week_stats = _counts(week)
    provider = vdispatch.active()
    cap = int(settings.auto_dial_daily_cap or 0)
    from ..integrations import telco

    # Full "ready to dial" checklist — the CARRIER creds (telco.diagnose) PLUS the
    # two things the Call button also needs: a callback cell to ring first, and a
    # public base URL so the carrier can reach our call webhooks. Naming every gap
    # here means pasting the API token doesn't just surface the NEXT missing field.
    setup = telco.diagnose()
    blockers = list(setup.get("missing") or [])
    if not (settings.producer_callback or "").strip():
        blockers.append("your cell / callback number (Setup → Calling)")
    if not (settings.public_base_url or "").strip():
        blockers.append("PUBLIC_BASE_URL (set in the deploy env)")
    setup["blockers"] = blockers
    setup["ready_to_dial"] = vdispatch.is_configured() and not blockers
    return {
        "provider": provider,
        "configured": vdispatch.is_configured(),
        # Exactly what's still missing to make the number dial (API token, callback
        # cell, base URL) — so "still not working" is an actionable checklist.
        "setup": setup,
        "voicemail_ready": voice.voicemail_configured(),
        "transfer_enabled": bool(settings.auto_dial_transfer_enabled),
        "daily_cap": cap,
        "remaining_today": max(0, cap - today["placed"]) if cap else None,
        "today": today,
        "week": week_stats,
    }


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


# ── Public Twilio / SignalWire (LaML) webhooks ────────────────────────────────
# Accept BOTH GET and POST: Twilio defaults to POST, but a SignalWire number/LaML
# handler can be configured for GET — a method mismatch returns 405, which the
# carrier reports as error 11200 ("HTTP retrieval failure") and the call drops.
# Every handler also swallows exceptions and returns valid LaML, so the carrier
# never gets a 5xx (also an 11200) even if a config refresh / DB read hiccups.
@router.api_route("/twiml/bridge", methods=["GET", "POST"])
def twiml_bridge(lead_phone: str = "", lead_id: str = "", db: Session = Depends(get_db)):
    """Returned to Twilio after YOU answer — dials + records the lead. Refreshes the
    connected Twilio config first: this webhook can land on a Cloud Run instance that
    never loaded the voice number from the DB, which left callerId empty and made
    Twilio reject the <Dial> — so the call dropped the moment you picked up."""
    try:
        _refresh(db)
        return Response(voice.bridge_twiml(lead_phone, lead_id or None), media_type=_XML)
    except Exception:  # never hand the carrier a 5xx — that surfaces as 11200
        return Response(voice.bridge_twiml(lead_phone, lead_id or None), media_type=_XML)


@router.api_route("/twiml/announce", methods=["GET", "POST"])
def twiml_announce():
    """Played to the lead on answer — the recording-consent notice."""
    try:
        return Response(voice.announce_twiml(), media_type=_XML)
    except Exception:
        return Response(voice._xml('<Pause length="1"/>'), media_type=_XML)


@router.api_route("/twiml/amd", methods=["GET", "POST"])
async def twiml_amd(request: Request, lead_id: str = "", db: Session = Depends(get_db)):
    """Auto-dial answer webhook: Twilio tells us who answered (AnsweredBy). Human →
    transfer to your phone; machine → leave your recorded voicemail. Refreshes config
    so the voice number / voicemail URL are loaded on any instance."""
    try:
        _refresh(db)
        answered_by = ""
        if request.method == "POST":
            form = await request.form()
            answered_by = form.get("AnsweredBy") or ""
        answered_by = answered_by or request.query_params.get("AnsweredBy") or ""
        return Response(voice.amd_twiml(answered_by or None, lead_id or None), media_type=_XML)
    except Exception:  # fall back to bridging YOU in rather than dropping the call
        return Response(voice.amd_twiml(None, lead_id or None), media_type=_XML)


@router.api_route("/twiml/record-vm", methods=["GET", "POST"])
def twiml_record_vm(db: Session = Depends(get_db)):
    """Played when we call you to record your voicemail drop."""
    try:
        _refresh(db)
        return Response(voice.record_vm_twiml(), media_type=_XML)
    except Exception:
        return Response(voice.record_vm_twiml(), media_type=_XML)


@router.post("/vm-saved")
async def vm_saved(request: Request, db: Session = Depends(get_db)):
    """Save the producer's recorded voicemail so the auto-dialer plays it on machines."""
    form = await request.form()
    rec_url = form.get("RecordingUrl")
    if rec_url:
        try:
            from .. import runtime_config
            # Twilio recording URLs serve audio at the .mp3 variant; <Play> fetches it.
            runtime_config.save(db, "producer_voicemail_url", rec_url + ".mp3")
        except Exception:
            db.rollback()
    return Response(voice._xml("<Say>Got it — your voicemail is saved. Goodbye.</Say>"), media_type=_XML)


@router.api_route("/twiml/outbound", methods=["GET", "POST"])
async def twiml_outbound(request: Request, db: Session = Depends(get_db)):
    """TwiML App voiceUrl for the browser softphone — dials the number the SDK
    passed as 'To'. Reads 'To'/'lead_id' from the POST form OR the query string
    (GET), so it works whichever HTTP method the carrier is configured to use."""
    try:
        _refresh(db)  # load the connected voice number so callerId isn't empty
        to = lead_id = ""
        if request.method == "POST":
            form = await request.form()
            to = (form.get("To") or "").strip()
            lead_id = (form.get("lead_id") or "").strip()
        to = to or (request.query_params.get("To") or "").strip()
        lead_id = lead_id or (request.query_params.get("lead_id") or "").strip()
        if not to:
            return Response(voice._xml("<Say>No number to call.</Say>"), media_type=_XML)
        return Response(voice.outbound_twiml(to, lead_id or None), media_type=_XML)
    except Exception:
        return Response(voice._xml("<Say>Sorry, we hit a problem placing the call.</Say>"),
                        media_type=_XML)


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


# ── Public Plivo webhooks (Plivo XML) — used when voice_provider routes to Plivo ─
@router.post("/plivo/amd")
async def plivo_amd(request: Request, lead_id: str = "", db: Session = Depends(get_db)):
    """Plivo auto-dial answer webhook. Plivo's machine detection reports the result;
    human → transfer to your phone (if enabled), machine → leave your recorded drop.
    Reads several possible param names so it's robust to Plivo's AMD payload."""
    _refresh(db)
    form = await request.form()
    raw = (form.get("Machine") or form.get("AnsweredBy") or form.get("MachineDetection")
           or form.get("CallStatus") or "").strip().lower()
    answered_by = "machine" if raw in ("true", "machine", "machine_start", "machine_end") else "human"
    return Response(plivo_voice.amd_xml(answered_by, lead_id or None), media_type=_XML)


@router.post("/plivo/bridge")
def plivo_bridge(lead_phone: str = "", lead_id: str = "", db: Session = Depends(get_db)):
    """Returned to Plivo after YOU answer a bridge call — dials + records the lead."""
    _refresh(db)
    return Response(plivo_voice.bridge_xml(lead_phone, lead_id or None), media_type=_XML)


@router.post("/plivo/record-vm")
def plivo_record_vm(db: Session = Depends(get_db)):
    """Played when we call you to record your voicemail drop (Plivo)."""
    _refresh(db)
    return Response(plivo_voice.record_vm_xml(), media_type=_XML)


@router.post("/plivo/vm-saved")
async def plivo_vm_saved(request: Request, db: Session = Depends(get_db)):
    """Save the producer's recorded voicemail (Plivo posts RecordUrl)."""
    form = await request.form()
    rec_url = form.get("RecordUrl") or form.get("RecordingUrl")
    if rec_url:
        try:
            from .. import runtime_config
            runtime_config.save(db, "producer_voicemail_url", rec_url)
        except Exception:
            db.rollback()
    return Response("", media_type=_XML)


@router.post("/plivo/status")
async def plivo_status(request: Request, lead_id: str = "", db: Session = Depends(get_db)):
    """Plivo hangup callback — mark the call row done when it completes."""
    form = await request.form()
    uuid = form.get("CallUUID") or form.get("RequestUUID")
    status = (form.get("CallStatus") or form.get("HangupCause") or "").strip().lower()
    if uuid:
        msg = db.query(Message).filter(Message.provider_id == uuid,
                                       Message.channel == "call").first()
        if msg and msg.status == "Dialing":
            msg.status = "Sent" if status in ("completed", "normal_hangup") else "Missed"
            db.commit()
    return Response("", media_type=_XML)


# ── Public Vonage webhooks (NCCO / JSON) — used when voice_provider routes to Vonage ─
@router.post("/vonage/amd")
async def vonage_amd(request: Request, lead_id: str = "", db: Session = Depends(get_db)):
    """Vonage auto-dial answer webhook → returns the NCCO (JSON). Transfer-off default
    leaves the recorded voicemail; transfer-on connects a live answer to your cell."""
    _refresh(db)
    answered = ""
    try:
        body = await request.json()
        answered = (body.get("machine") and "machine") or ""
    except Exception:
        pass
    return vonage_voice.amd_ncco(answered or None, lead_id or None)


@router.post("/vonage/bridge")
async def vonage_bridge(request: Request, lead_phone: str = "", lead_id: str = "",
                        db: Session = Depends(get_db)):
    """Returned to Vonage after YOU answer a bridge call — dials the lead."""
    _refresh(db)
    return vonage_voice.bridge_ncco(lead_phone, lead_id or None)


@router.post("/vonage/record-vm")
async def vonage_record_vm(db: Session = Depends(get_db)):
    """Played when we call you to record your voicemail drop (Vonage)."""
    _refresh(db)
    return vonage_voice.record_vm_ncco()


@router.post("/vonage/vm-saved")
async def vonage_vm_saved(request: Request, db: Session = Depends(get_db)):
    """Save the producer's recorded voicemail (Vonage posts recording_url)."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    rec_url = body.get("recording_url") if isinstance(body, dict) else None
    if rec_url:
        try:
            from .. import runtime_config
            runtime_config.save(db, "producer_voicemail_url", rec_url)
        except Exception:
            db.rollback()
    return {}


@router.post("/vonage/event")
async def vonage_event(request: Request, lead_id: str = "", db: Session = Depends(get_db)):
    """Vonage call-status events — mark the call row done when it completes."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    uuid_ = body.get("uuid") if isinstance(body, dict) else None
    status = (body.get("status") or "").strip().lower() if isinstance(body, dict) else ""
    if uuid_ and status:
        msg = db.query(Message).filter(Message.provider_id == uuid_,
                                       Message.channel == "call").first()
        if msg and msg.status == "Dialing" and status in ("completed", "answered", "failed",
                                                           "timeout", "rejected", "busy", "unanswered"):
            msg.status = "Sent" if status in ("completed", "answered") else "Missed"
            db.commit()
    return {}


@router.get("/sip/health")
def sip_health(db: Session = Depends(get_db), _=Depends(_read)):
    """Test the app → self-hosted FreeSWITCH link (Setup 'Test connection' button):
    ESL auth + whether the BYOC trunk gateway is registered, before any real call."""
    _refresh(db)
    return sip_voice.health()


# ── Public self-hosted SIP softswitch webhooks (FreeSWITCH HTTAPI / XML) ───────
# Served when voice_provider routes to our own FreeSWITCH. Same fetch-instructions
# shape as TwiML/NCCO, but FreeSWITCH's HTTAPI XML dialect. See integrations/sip_voice.py.
@router.post("/sip/amd")
async def sip_amd(request: Request, lead_id: str = "", db: Session = Depends(get_db)):
    """Auto-dial answer → machine gets the recorded drop; a live human transfers to
    your cell (when enabled). Reads mod_amd's result, which FreeSWITCH HTTAPI posts
    as the amd_result channel variable."""
    _refresh(db)
    raw = ""
    try:
        form = await request.form()
        raw = (form.get("amd_result") or form.get("variable_amd_result") or "").strip().lower()
    except Exception:
        pass
    answered_by = "machine" if "machine" in raw else ("human" if raw else "")
    return Response(sip_voice._httapi(sip_voice.amd_work(answered_by or None, lead_id or None)),
                    media_type=_XML)


@router.post("/sip/bridge")
def sip_bridge(lead_phone: str = "", lead_id: str = "", db: Session = Depends(get_db)):
    """Returned after YOU answer a bridge call — consent, then dial the lead."""
    _refresh(db)
    return Response(sip_voice._httapi(sip_voice.bridge_work(lead_phone, lead_id or None)),
                    media_type=_XML)


@router.post("/sip/record-vm")
def sip_record_vm(db: Session = Depends(get_db)):
    """Played when we call you to record your voicemail drop (FreeSWITCH)."""
    _refresh(db)
    return Response(sip_voice._httapi(sip_voice.record_vm_work()), media_type=_XML)


@router.post("/sip/vm-saved")
async def sip_vm_saved(request: Request, db: Session = Depends(get_db)):
    """FreeSWITCH POSTs the recorded greeting here (multipart). Store it and point
    the voicemail drop at the hosted URL. Best-effort; always returns a valid doc."""
    try:
        form = await request.form()
        rec = form.get("vm-greeting.wav") or form.get("recording") or form.get("file")
        data = await rec.read() if hasattr(rec, "read") else None
        if data:
            from ..integrations import storage
            url = storage.upload_public(data, "voicemail/sip-greeting.wav", "audio/wav")
            if url:
                from .. import runtime_config
                runtime_config.save(db, "producer_voicemail_url", url)
    except Exception:
        db.rollback()
    return Response(sip_voice._httapi("<hangup/>"), media_type=_XML)


@router.post("/sip/event")
async def sip_event(request: Request, lead_id: str = "", db: Session = Depends(get_db)):
    """FreeSWITCH call-status callback — mark the call row done when it completes."""
    try:
        form = await request.form()
    except Exception:
        form = {}
    uuid_ = (form.get("uuid") or form.get("Unique-ID") or "") if form else ""
    status = (form.get("status") or form.get("hangup_cause") or "").strip().lower() if form else ""
    if uuid_ and status:
        msg = db.query(Message).filter(Message.provider_id == uuid_,
                                       Message.channel == "call").first()
        if msg and msg.status == "Dialing":
            msg.status = "Sent" if status in ("completed", "answered", "normal_clearing") else "Missed"
            db.commit()
    return Response("", media_type=_XML)
