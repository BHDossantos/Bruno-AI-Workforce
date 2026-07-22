"""Conversation Engine API — structured call logging + the outcome dashboard.

Endpoints:
  • GET  /conversations/schema            → dropdown options (data-driven form)
  • POST /leads/{id}/conversation         → log one structured conversation
  • GET  /leads/{id}/conversations        → a lead's conversation history
  • GET  /conversations/dashboard         → segment the book by outcome
  • GET  /conversations/objection-response → the AI-suggested line for an objection
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import conversation_engine as engine
from ..database import get_db
from ..models import ConversationOutcome, Lead
from ..security import require_role

router = APIRouter(tags=["conversations"])
_write = require_role("admin", "operator")
_read = require_role("admin", "operator", "viewer")


class ConversationIn(BaseModel):
    method: str = "call"
    outcome: str | None = None
    attempt_number: int | None = None
    duration_seconds: int | None = None
    voicemail_left: bool = False
    text_sent: bool = False
    email_sent: bool = False
    conversation_status: str | None = None
    insurance_needed: list[str] = []
    objection: str | None = None
    quote_started: bool = False
    quote_completed: bool = False
    quote_sent: bool = False
    current_carrier: str | None = None
    current_premium: float | None = None
    renewal_month: str | None = None
    future_review: bool = False
    not_interested_reason: str | None = None
    quotes_gathered: int | None = None
    biggest_concern: str | None = None
    quote_priority: str | None = None
    next_action: str | None = None
    next_follow_up_at: str | None = None
    close_probability: int | None = None
    notes: dict | None = None


def _serialize(r: ConversationOutcome) -> dict:
    return {
        "id": str(r.id), "created_at": r.created_at.isoformat() if r.created_at else None,
        "method": r.method, "outcome": r.outcome, "attempt_number": r.attempt_number,
        "duration_seconds": r.duration_seconds,
        "voicemail_left": r.voicemail_left, "text_sent": r.text_sent, "email_sent": r.email_sent,
        "conversation_status": r.conversation_status, "insurance_needed": r.insurance_needed or [],
        "objection": r.objection, "quote_started": r.quote_started,
        "quote_completed": r.quote_completed, "quote_sent": r.quote_sent,
        "current_carrier": r.current_carrier,
        "current_premium": float(r.current_premium) if r.current_premium is not None else None,
        "renewal_month": r.renewal_month, "future_review": r.future_review,
        "not_interested_reason": r.not_interested_reason, "quotes_gathered": r.quotes_gathered,
        "biggest_concern": r.biggest_concern, "quote_priority": r.quote_priority,
        "next_action": r.next_action,
        "next_follow_up_at": r.next_follow_up_at.isoformat() if r.next_follow_up_at else None,
        "ai_summary": r.ai_summary, "close_probability": r.close_probability,
        "suggested_response": engine.response_for(
            conversation_status=r.conversation_status, objection=r.objection),
    }


@router.get("/conversations/schema")
def conversation_schema(_=Depends(_read)):
    """All dropdown options for the structured Log-Call form, plus the objection
    response map — so the UI renders itself and adding an option is a one-line change."""
    return {"schema": engine.SCHEMA, "objection_responses": engine.OBJECTION_RESPONSES}


@router.post("/leads/{lead_id}/conversation")
def log_conversation(lead_id: str, body: ConversationIn, db: Session = Depends(get_db),
                     user=Depends(_write)):
    """Log ONE structured conversation for a lead. Writes the queryable row and fires
    side effects: a call on the timeline, DNC suppression, status move, and the next
    follow-up / renewal reminder."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(404, "Lead not found")
    producer = getattr(user, "email", None) or "producer"
    row = engine.log_outcome(db, lead.id, body.model_dump(), producer=producer)
    return {"ok": True, **_serialize(row)}


@router.get("/leads/{lead_id}/conversations")
def lead_conversations(lead_id: str, db: Session = Depends(get_db), _=Depends(_read)):
    """A lead's full conversation history, newest first."""
    rows = (db.query(ConversationOutcome)
            .filter(ConversationOutcome.lead_id == lead_id)
            .order_by(ConversationOutcome.created_at.desc()).all())
    return {"lead_id": lead_id, "count": len(rows), "conversations": [_serialize(r) for r in rows]}


@router.get("/conversations/dashboard")
def conversations_dashboard(db: Session = Depends(get_db), _=Depends(_read)):
    """Segment the whole book by conversation status + today's activity + which
    carriers we're competing against."""
    return engine.dashboard(db)


@router.get("/conversations/renewals")
def conversations_renewals(db: Session = Depends(get_db), _=Depends(_read)):
    """The renewal pipeline — already-insured leads who wanted a review, sorted by
    the ~30-day-before-renewal reminder date. Work these ahead of renewal season."""
    return {"renewals": engine.upcoming_renewals(db)}


@router.get("/leads/{lead_id}/opportunity")
def lead_opportunity(lead_id: str, db: Session = Depends(get_db), _=Depends(_read)):
    """Per-line cross-sell opportunity estimate for a lead (Auto/Home/Umbrella/…),
    from their data + everything logged on their conversations."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(404, "Lead not found")
    convos = (db.query(ConversationOutcome)
              .filter(ConversationOutcome.lead_id == lead_id).all())
    return {"lead_id": lead_id, "opportunity": engine.estimate_opportunity(lead, convos)}


@router.get("/conversations/objection-response")
def objection_response(objection: str | None = None, conversation_status: str | None = None,
                       _=Depends(_read)):
    """The AI-suggested line to say for a given objection / conversation status."""
    return {"response": engine.response_for(objection=objection,
                                            conversation_status=conversation_status)}
