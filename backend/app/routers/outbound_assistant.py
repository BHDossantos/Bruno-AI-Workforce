"""AI first ONLY for the existing live-answer classification on the existing outbound AMD path."""
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from .. import runtime_config
from ..callback_auth import require_verified_twilio_callback, _credential
from ..config import settings
from ..database import get_db
from ..integrations import twilio_voice as voice
from ..models import OutboundAssistantCall
from .inbound_assistant import AssistantFlow, finish, handle, UNAVAILABLE

router = APIRouter(prefix="/calls/outbound-assistant", tags=["calls"],
                   dependencies=[Depends(require_verified_twilio_callback)])


def policy(db):
    # Reuse the existing destination and bridge caller-ID selection. Explicit
    # verification is an owner attestation, never inferred from stored defaults.
    target = voice._e164(_credential(db, "producer_cell") or _credential(db, "producer_callback"))
    caller_id = voice.bridge_caller_id(target)
    verified_id = settings.outbound_assistant_verified_caller_id
    public = tuple(voice._e164(value) for value in (
        _credential(db, "twilio_voice_number"), _credential(db, "twilio_from_number"),
        _credential(db, "twilio_insurance_number"),
        *_credential(db, "local_presence_numbers").split(",")))
    current_caller_ids = (*public, voice._e164(_credential(db, "transfer_caller_id")))
    return AssistantFlow(
        enabled=settings.outbound_assistant_enabled and settings.auto_dial_transfer_enabled,
        number=settings.outbound_assistant_from_number,
        target=target, verified_target=settings.outbound_assistant_verified_transfer_number,
        caller_id=caller_id if caller_id == verified_id and caller_id in current_caller_ids else "",
        path="/calls/outbound-assistant", direction="outbound-api",
        number_field="From", peer_field="To", model=OutboundAssistantCall,
        blocked_targets=public,
    )


def process(db, stage, turn, params):
    runtime_config.apply_to_settings(db)
    return handle(db, stage, turn, params, policy(db))


async def respond(request, db, stage, turn):
    params = dict(await request.form()) if request.method == "POST" else dict(request.query_params)
    try:
        xml = await run_in_threadpool(process, db, stage, turn, params)
    except SQLAlchemyError:
        db.rollback()
        xml = finish(UNAVAILABLE)
    return Response(xml, media_type="application/xml")


async def start(request: Request, db: Session):
    # The legacy AMD dependency skips verification in development; this branch
    # always authenticates. Keep failures outside its broad fallback exception.
    await require_verified_twilio_callback(request, db)
    return await respond(request, db, "start", 0)


@router.post("/{stage}")
async def callback(stage: str, request: Request, turn: int = 0, db: Session = Depends(get_db)):
    # Start is allowed only through the AMD handler after the existing live-answer classification.
    if stage not in ("turn", "result"):
        return Response(finish(), media_type="application/xml")
    return await respond(request, db, stage, turn)
