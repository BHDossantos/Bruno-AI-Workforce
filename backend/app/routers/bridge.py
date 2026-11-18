"""iMessage bridge API.

A helper running on the user's Mac polls these endpoints and sends/receives SMS
through Messages.app — so texts go out from the user's REAL number (free, no
Twilio). Authenticated with a single shared secret in the X-Bridge-Token header
(set BRIDGE_TOKEN). Endpoints are intentionally NOT behind the user login because
the Mac helper is a machine client.
"""
from datetime import datetime, timezone
from typing import Literal
import secrets
import hmac

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import Message, OutboundAttempt, OutboundHold
from .. import outbound_guard

router = APIRouter(prefix="/bridge", tags=["bridge"])


def _auth(token: str | None) -> None:
    if not settings.bridge_token or token != settings.bridge_token:
        raise HTTPException(status_code=401, detail="Invalid or missing bridge token")


@router.get("/outbox")
def outbox(x_bridge_token: str | None = Header(default=None),
           limit: int = 50, db: Session = Depends(get_db)):
    """Outbound texts waiting to be sent from the Mac (queued, not yet sent)."""
    _auth(x_bridge_token)
    # Only explicitly bridge-queued messages can be claimed. Never steal a
    # carrier draft or a held result. A lost response remains held, not reissued.
    rows = (db.query(Message).filter(
        Message.channel == "sms", Message.direction == "outbound",
        Message.status == "Queued", Message.sent_at.is_(None),
        Message.to_email.isnot(None)).order_by(Message.created_at.asc())
        .limit(max(1, min(limit, 50))).with_for_update(skip_locked=True).all())
    from .. import sms_engine
    claims = []
    for m in rows:
        if sms_engine.sms_block_reason(db, m.to_email, enforce_hours=True):
            continue
        claimed = False
        def handoff():
            nonlocal claimed
            claimed = True
            return None, outbound_guard.DeferredDelivery("bridge handoff")
        _, error = outbound_guard.invoke("sms", m.to_email, m.from_account,
                                         f"message:{m.id}", [m.body], handoff)
        if not claimed or "could not be recorded" in (error or ""):
            continue
        key = outbound_guard.digest(outbound_guard.recipient_scope("sms", m.to_email),
                                    m.from_account, f"message:{m.id}")
        token = secrets.token_urlsafe(32)
        db.query(OutboundAttempt).filter(OutboundAttempt.key == key).update(
            {"claim_hash": outbound_guard.digest(token)})
        m.status = "Needs Review"  # pending external result, never automatically requeued
        claims.append({"id": str(m.id), "to": m.to_email, "body": m.body or "", "claim_token": token})
    db.commit()  # Commit claim ownership before returning any text to the helper.
    return claims


class SentBody(BaseModel):
    id: str
    claim_token: str = Field(min_length=20, max_length=200)
    outcome: Literal["accepted", "unknown"] = "accepted"


@router.post("/sent")
def mark_sent(body: SentBody, x_bridge_token: str | None = Header(default=None),
              db: Session = Depends(get_db)):
    """Record a claimed helper result. Acceptance is not delivery confirmation."""
    _auth(x_bridge_token)
    m = db.query(Message).filter(Message.id == body.id).with_for_update().first()
    if not m:
        raise HTTPException(404, "message not found")
    key = outbound_guard.digest(outbound_guard.recipient_scope("sms", m.to_email),
                                m.from_account, f"message:{m.id}")
    attempt = db.query(OutboundAttempt).filter(OutboundAttempt.key == key).with_for_update().first()
    if not attempt or not attempt.claim_hash or not hmac.compare_digest(
            attempt.claim_hash, outbound_guard.digest(body.claim_token)):
        raise HTTPException(403, "Invalid bridge claim")
    if attempt.state == "accepted" and body.outcome == "accepted":
        return {"ok": True, "id": body.id}  # ACK replay, never another send
    if attempt.state != "pending":
        raise HTTPException(409, "Claim already resolved; review recorded evidence")
    attempt.state = "accepted" if body.outcome == "accepted" else "unknown"
    attempt.updated_at = datetime.now(timezone.utc)
    if body.outcome == "accepted":
        attempt.provider_id = "bridge-local-acceptance:" + str(m.id)
        m.status = "Sent"
        m.provider_id = attempt.provider_id
        m.sent_at = datetime.now(timezone.utc)
        db.query(OutboundHold).filter(OutboundHold.scope == attempt.scope,
                                     OutboundHold.attempt_key == key).delete()
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
