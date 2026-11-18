"""Evidence-based reconciliation; no endpoint sends or retries provider requests."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, update, func, case
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import OutboundAttempt, OutboundHold, OutboundResolution, Message, Lead, Restaurant
from ..security import require_role

router = APIRouter(tags=["delivery"])
_operator = require_role("admin", "operator")


class ResolutionIn(BaseModel):
    decision: Literal["keep_held", "accepted", "not_accepted"]
    expected_state: Literal["pending", "unknown", "rejected"]
    evidence: str = Field(min_length=20, max_length=2000)
    provider_reference: str = Field(min_length=5, max_length=200)
    provider_id: str | None = Field(default=None, max_length=200)


@router.post("/messages/delivery-attempts/{key}/resolve")
def resolve(key: str, body: ResolutionIn, db: Session = Depends(get_db), user=Depends(_operator)):
    snapshot = db.get(OutboundAttempt, key)
    if snapshot and snapshot.operation_ref and snapshot.operation_ref.startswith("message:"):
        from uuid import UUID
        try:
            message_id = UUID(snapshot.operation_ref.split(":", 1)[1])
        except ValueError:
            message_id = None
        if message_id:
            # Consistent lock order with Outbox and bridge acknowledgements.
            db.query(Message).filter(Message.id == message_id).with_for_update().first()
    attempt = db.execute(select(OutboundAttempt).where(OutboundAttempt.key == key)
                         .execution_options(populate_existing=True)
                         .with_for_update()).scalar_one_or_none()
    if attempt is None:
        raise HTTPException(404, "Attempt not found")
    if attempt.state != body.expected_state:
        raise HTTPException(409, "Attempt state changed; refresh before recording a decision")
    if len(body.evidence.strip()) < 20 or len(body.provider_reference.strip()) < 5:
        raise HTTPException(422, "Provider evidence and reference are required")
    if body.decision != "keep_held":
        # A pending worker can still invoke its provider after an operator inspects
        # the queue. Never release its hold from this API, even if it looks old.
        if attempt.state == "pending":
            raise HTTPException(409, "Pending worker may still run. Record evidence and keep held; drain/reconciliation procedure required")
        if body.decision == "accepted" and not (body.provider_id or "").strip():
            raise HTTPException(422, "Confirmed acceptance requires a provider receipt")
        attempt.state = "accepted" if body.decision == "accepted" else "not_accepted"
        attempt.provider_id = (body.provider_id or "").strip() if body.decision == "accepted" else None
        attempt.updated_at = func.now()
        db.execute(delete(OutboundHold).where(OutboundHold.scope == attempt.scope,
                                             OutboundHold.attempt_key == key))
        # Historical key stays consumed. Never turn a held item back into a draft.
        # Only update a matching message; provider receipt does not prove delivery.
        if attempt.operation_ref and attempt.operation_ref.startswith("message:"):
            from uuid import UUID
            try:
                message_id = UUID(attempt.operation_ref.split(":", 1)[1])
            except ValueError:
                message_id = None
            if message_id:
                touched = db.execute(update(Message).where(Message.id == message_id,
                                                  Message.status != "Sent").values(
                    status="Sent" if body.decision == "accepted" else "Not Sent",
                    provider_id=attempt.provider_id,
                    sent_at=func.now() if body.decision == "accepted" else None).returning(
                        Message.channel, Message.entity_type, Message.entity_id)).first()
                if touched and body.decision == "accepted" and touched.channel == "email":
                    model = {"lead": Lead, "restaurant": Restaurant}.get(touched.entity_type)
                    if model is not None and touched.entity_id:
                        db.execute(update(model).where(model.id == touched.entity_id).values(
                            status=case((model.status.in_(["New", "Drafted", "Approved"]), "Sent"), else_=model.status),
                            times_contacted=func.coalesce(model.times_contacted, 0) + 1,
                            last_contacted_at=func.now()))
    db.add(OutboundResolution(attempt_key=key, actor=str(user.id), decision=body.decision,
                             evidence=body.evidence.strip(), provider_reference=body.provider_reference.strip()))
    db.commit()
    return {"key": key, "state": attempt.state, "sent": False, "retried": False}


@router.get("/messages/delivery-attempts/{key}/history")
def history(key: str, db: Session = Depends(get_db), _=Depends(_operator)):
    rows = db.query(OutboundResolution).filter(OutboundResolution.attempt_key == key).order_by(
        OutboundResolution.created_at, OutboundResolution.id).all()
    return [{"id": row.id, "actor": row.actor, "decision": row.decision,
             "evidence": row.evidence, "provider_reference": row.provider_reference,
             "created_at": row.created_at} for row in rows]
