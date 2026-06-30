"""Natural-language campaign builder.

"Find Boston restaurants under 4.3 stars and pitch SavoryMind, follow up 6×" →
a structured, reviewable campaign plan (business, audience, filters, channels,
sequence, schedule, metric). The user can then launch it, which runs the mapped
business agent to source + draft into the pipeline. Degrades gracefully offline.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from .ai import client
from .ai.prompts import CAMPAIGN_FROM_BRIEF
from .models import CampaignPlan

log = logging.getLogger("bruno.campaign_builder")

# business label → agent key that sources + drafts for it.
_AGENT_FOR = {
    "Insurance": "commercial_finder",
    "BnB Global": "bnbglobal",
    "SavoryMind": "savorymind",
}


def build(db: Session, brief: str) -> dict:
    brief = (brief or "").strip()
    if not brief:
        return {"ok": False, "error": "Describe the campaign you want."}
    if not client.is_live():
        return {"ok": False, "error": "Set OPENAI_API_KEY to build campaigns."}
    data = client.complete_json(CAMPAIGN_FROM_BRIEF.format(brief=brief))
    if not isinstance(data, dict) or not data.get("business"):
        return {"ok": False, "error": "Couldn't parse that — try rephrasing."}
    business = data.get("business")
    row = CampaignPlan(brief=brief, business=business,
                       agent_key=_AGENT_FOR.get(business), plan=data)
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"ok": True, **_serialize(row)}


def launch(db: Session, plan_id: str) -> dict:
    """Run the mapped business agent to start sourcing + drafting for this plan."""
    row = db.query(CampaignPlan).filter(CampaignPlan.id == plan_id).first()
    if not row:
        return {"ok": False, "error": "Plan not found"}
    from .agents import AGENTS
    cls = AGENTS.get(row.agent_key or "")
    if not cls:
        return {"ok": False, "error": "No agent mapped for this business"}
    try:
        result = cls(db).run()
    except Exception as exc:  # surface, don't crash
        return {"ok": False, "error": f"Launch failed: {str(exc)[:150]}"}
    row.status = "launched"
    db.commit()
    return {"ok": True, "launched": row.business, "result": result}


def list_plans(db: Session, limit: int = 50) -> list[dict]:
    rows = db.query(CampaignPlan).order_by(CampaignPlan.created_at.desc()).limit(limit).all()
    return [_serialize(r) for r in rows]


def _serialize(row: CampaignPlan) -> dict:
    return {
        "id": str(row.id), "brief": row.brief, "business": row.business,
        "agent_key": row.agent_key, "plan": row.plan or {}, "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
