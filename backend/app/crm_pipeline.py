"""Actionable CRM pipeline (Kanban) — leads grouped into deal stages with the
next action, lead score, temperature and expected value per card, plus a move()
to advance a lead through the stages. This is the sales board (distinct from the
read-only funnel analytics on /pipeline).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from .lead_temperature import DEAD, HOT, WARM, classify
from .models import Lead

# Canonical pipeline stages, in order.
STAGES = ["New", "Contacted", "Replied", "Qualified", "Meeting", "Won", "Lost", "Nurture"]

_NEXT_ACTION = {
    "New": "Send first touch",
    "Contacted": "Follow up",
    "Replied": "Reply now — keep it moving",
    "Qualified": "Book a meeting / send quote",
    "Meeting": "Run the meeting, then send proposal",
    "Won": "Onboard + ask for referral",
    "Lost": "Move to nurture in 6 months",
    "Nurture": "Re-engage when timing is better",
}

# Rough expected deal value per segment (commission / contract), used for
# pipeline value. Multiplied by a stage win-probability.
_SEGMENT_VALUE = {
    "commercial": 1800, "personal": 600, "consulting": 6000, "restaurant": 1200,
}
_STAGE_PROB = {
    "New": 0.02, "Contacted": 0.04, "Replied": 0.15, "Qualified": 0.35,
    "Meeting": 0.6, "Won": 1.0, "Lost": 0.0, "Nurture": 0.05,
}

# Canonical status written when a card is moved into a stage.
_STAGE_STATUS = {
    "New": "New", "Contacted": "Sent", "Replied": "Replied", "Qualified": "Interested",
    "Meeting": "Meeting", "Won": "Won", "Lost": "Closed Lost", "Nurture": "Nurture",
}


def stage_of(lead: Lead) -> str:
    """Map a lead's status/temperature to a canonical pipeline stage."""
    s = (lead.status or "").strip().lower()
    if s in ("won", "closed won", "client", "customer"):
        return "Won"
    if s in ("nurture", "nurture later"):
        return "Nurture"
    temp = classify(lead.status)
    if temp == DEAD:
        return "Lost"
    if temp == HOT:
        return "Meeting" if s in ("meeting", "meeting booked", "demo", "demo booked", "booked") else "Qualified"
    if temp == WARM:
        return "Replied"
    # cold: distinguish not-yet-contacted from contacted
    if (lead.times_contacted or 0) > 0 or s in ("sent", "drafted", "contacted"):
        return "Contacted"
    return "New"


def _card(lead: Lead, stage: str) -> dict:
    value = int(_SEGMENT_VALUE.get(lead.segment or "", 800) * _STAGE_PROB.get(stage, 0.05))
    return {
        "id": str(lead.id),
        "name": lead.owner_name or lead.company_name or lead.email or "—",
        "company": lead.company_name,
        "segment": lead.segment,
        "score": int(lead.score or 0),
        "temperature": classify(lead.status),
        "email": lead.email,
        "last_contacted": lead.last_contacted_at.isoformat() if lead.last_contacted_at else None,
        "expected_value": value,
        "next_action": _NEXT_ACTION.get(stage, ""),
    }


def board(db: Session, segment: str | None = None, per_stage: int = 50) -> dict:
    """Return the pipeline grouped by stage with cards (highest-score first)."""
    q = db.query(Lead)
    if segment:
        q = q.filter(Lead.segment == segment)
    leads = q.order_by(Lead.score.desc()).all()
    cols: dict[str, dict] = {
        s: {"stage": s, "next_action": _NEXT_ACTION.get(s, ""), "count": 0,
            "value": 0, "cards": []} for s in STAGES
    }
    for lead in leads:
        st = stage_of(lead)
        col = cols[st]
        col["count"] += 1
        card = _card(lead, st)
        col["value"] += card["expected_value"]
        if len(col["cards"]) < per_stage:
            col["cards"].append(card)
    return {
        "stages": [cols[s] for s in STAGES],
        "pipeline_value": sum(c["value"] for c in cols.values()),
    }


def move(db: Session, lead_id: str, stage: str) -> dict:
    """Move a lead to a pipeline stage (sets its canonical status)."""
    if stage not in STAGES:
        return {"ok": False, "error": "unknown stage"}
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        return {"ok": False, "error": "lead not found"}
    lead.status = _STAGE_STATUS[stage]
    db.commit()
    return {"ok": True, "id": str(lead.id), "stage": stage, "status": lead.status}
