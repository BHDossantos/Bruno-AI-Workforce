"""Opt-in Twilio receptionist. No outbound REST calls or model-controlled dialing."""
from dataclasses import dataclass
import re
import time

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from twilio.twiml.voice_response import VoiceResponse

from .. import control
from ..ai import client as ai
from ..callback_auth import require_verified_twilio_callback
from ..config import settings
from ..database import get_db
from ..models import InboundAssistantCall

router = APIRouter(prefix="/calls/assistant", tags=["calls"],
                   dependencies=[Depends(require_verified_twilio_callback)])
PHONE = re.compile(r"\+[1-9]\d{7,14}\Z")
CALL = re.compile(r"CA[0-9a-fA-F]{32}\Z")
UNAVAILABLE = "Bruno is unavailable right now. Please try again later. Goodbye."
CHOICE = "To try Bruno now, press 1. Otherwise, tell me briefly how I can help."


@dataclass(frozen=True)
class AssistantFlow:
    enabled: bool
    number: str
    target: str
    verified_target: str
    caller_id: str
    path: str = "/calls/assistant"
    direction: str = "inbound"
    number_field: str = "To"
    peer_field: str = "From"
    model: type = InboundAssistantCall
    blocked_targets: tuple[str, ...] = ()


def finish(message=""):
    response = VoiceResponse()
    if message:
        response.say(message)
    response.hangup()
    return str(response)


def gather(message, turn, path="/calls/assistant"):
    response = VoiceResponse()
    prompt = response.gather(input="speech dtmf", num_digits=1, timeout=5,
                             speech_timeout="auto", action_on_empty_result=True,
                             action=f"{path}/turn?turn={turn}", method="POST")
    prompt.say(message)
    return str(response)


def answer(speech):
    """Existing OpenAI client, bounded for Twilio webhook deadlines, no tools."""
    client = ai._get_client()
    if client is None:
        return "I cannot answer questions right now. " + CHOICE
    try:
        result = client.with_options(timeout=4.0, max_retries=0).chat.completions.create(
            model=settings.openai_model, max_tokens=100, temperature=0.2,
            messages=[{"role": "system", "content":
                       "You are Bruno's AI phone receptionist in the Workforce app. "
                       "You have no personal information, tools, calendar or ChatGPT conversation access. "
                       "Never claim to send messages, arrange callbacks, transfer calls or know Bruno's availability. "
                       "Do not give professional advice. Briefly acknowledge the caller's request in one sentence. "
                       "If they want Bruno, explain they can press 1. Never request sensitive information."},
                      {"role": "user", "content": speech[:1000]}])
        text = result.choices[0].message.content
        return (text[:400] + " " + CHOICE) if text else CHOICE
    except Exception:
        return "I cannot answer questions right now. " + CHOICE


def handle(db, stage, turn, params, flow=None):
    if flow is None:
        flow = AssistantFlow(settings.inbound_assistant_enabled,
                             settings.inbound_assistant_number,
                             settings.inbound_assistant_transfer_number,
                             settings.inbound_assistant_verified_transfer_number,
                             settings.inbound_assistant_number)
    model = flow.model
    sid = params.get("CallSid", "")
    number = flow.number
    if (not flow.enabled or not PHONE.fullmatch(number)
            or params.get(flow.number_field) != number or params.get("Direction") != flow.direction
            or not CALL.fullmatch(sid) or control.is_paused(db)):
        return finish(UNAVAILABLE)
    now = int(time.time())
    if stage == "start":
        # Unique insert fences concurrent starts and replayed signed requests.
        db.add(model(call_sid=sid, stage="listening", turn=1,
                                    expires_at=now + 600))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return finish()
        return gather("Hello, I am Bruno's AI assistant. Your speech is processed by our "
                      "voice and AI providers. Please do not share sensitive information. " + CHOICE, 1, flow.path)
    if stage not in ("turn", "result") or not 1 <= turn <= 4:
        return finish()
    transfer = stage == "turn" and params.get("Digits") == "1"
    next_stage = "dialing" if transfer else ("done" if stage == "result" or turn == 4 else "listening")
    claimed = db.execute(update(model).where(
        model.call_sid == sid,
        model.stage == ("dialing" if stage == "result" else "listening"),
        model.turn == turn,
        model.expires_at > now,
    ).values(stage=next_stage, turn=turn if transfer else turn + 1))
    # Commit before producing any dialing instruction or contacting AI. Never
    # replay a Dial after a lost response; uncertain delivery deliberately ends.
    db.commit()
    if claimed.rowcount != 1:
        return finish()
    if stage == "result":
        return finish("Goodbye." if params.get("DialCallStatus") == "completed" else UNAVAILABLE)
    if transfer:
        target = flow.target
        if (not PHONE.fullmatch(target)
                or target != flow.verified_target
                or target == number or target == params.get(flow.peer_field)
                or target in flow.blocked_targets or not PHONE.fullmatch(flow.caller_id)
                or flow.caller_id == target or flow.caller_id == params.get(flow.peer_field)
                or control.is_paused(db)):
            return finish(UNAVAILABLE)
        response = VoiceResponse()
        response.say("I will try Bruno now.")
        response.dial(target, caller_id=flow.caller_id, timeout=20, time_limit=1800,
                      action=f"{flow.path}/result?turn={turn}", method="POST")
        return str(response)
    if turn == 4 or not params.get("SpeechResult", "").strip():
        return finish(UNAVAILABLE)
    return gather(answer(params["SpeechResult"]), turn + 1, flow.path)


@router.post("/{stage}")
async def callback(stage: str, request: Request, turn: int = 0, db: Session = Depends(get_db)):
    params = dict(await request.form())  # signature dependency has rejected duplicates
    try:
        xml = await run_in_threadpool(handle, db, stage, turn, params)
    except SQLAlchemyError:
        db.rollback()
        xml = finish(UNAVAILABLE)
    return Response(xml, media_type="application/xml")
