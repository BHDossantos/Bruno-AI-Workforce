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
    return {"ok": True, **_serialize(db, row)}


def launch(db: Session, plan_id: str) -> dict:
    """Run the mapped business agent with THIS plan's filters, so the brief you
    typed actually steers sourcing instead of just triggering a generic run.
    Location becomes the sourcing scope, industry/keywords narrow the sourced
    batch, and every lead/restaurant found is tagged with this plan's id."""
    row = db.query(CampaignPlan).filter(CampaignPlan.id == plan_id).first()
    if not row:
        return {"ok": False, "error": "Plan not found"}
    from .agents import AGENTS
    cls = AGENTS.get(row.agent_key or "")
    if not cls:
        return {"ok": False, "error": "No agent mapped for this business"}
    plan = row.plan or {}
    filters = plan.get("filters") or {}
    kwargs: dict = {"campaign_id": str(row.id)}
    if filters.get("location"):
        kwargs["scope"] = str(filters["location"])
    if filters.get("industry"):
        kwargs["industry"] = str(filters["industry"])
    kw = filters.get("keywords")
    if kw:
        kwargs["keywords"] = kw if isinstance(kw, list) else [str(kw)]
    try:
        result = cls(db).run(**kwargs)
    except Exception as exc:  # surface, don't crash
        return {"ok": False, "error": f"Launch failed: {str(exc)[:150]}"}
    row.status = "launched"
    db.commit()
    return {"ok": True, "launched": row.business, "result": result,
            **_campaign_counts(db, str(row.id))}


def list_plans(db: Session, limit: int = 50) -> list[dict]:
    rows = db.query(CampaignPlan).order_by(CampaignPlan.created_at.desc()).limit(limit).all()
    return [_serialize(db, r) for r in rows]


def _campaign_counts(db: Session, campaign_id: str) -> dict:
    from sqlalchemy import func

    from .models import Lead, Restaurant
    leads = (db.query(func.count()).select_from(Lead)
             .filter(Lead.campaign_id == campaign_id).scalar() or 0)
    restaurants = (db.query(func.count()).select_from(Restaurant)
                   .filter(Restaurant.campaign_id == campaign_id).scalar() or 0)
    return {"leads_sourced": int(leads), "restaurants_sourced": int(restaurants)}


def _serialize(db: Session, row: CampaignPlan) -> dict:
    counts = (_campaign_counts(db, str(row.id)) if row.status == "launched"
              else {"leads_sourced": 0, "restaurants_sourced": 0})
    return {
        "id": str(row.id), "brief": row.brief, "business": row.business,
        "agent_key": row.agent_key, "plan": row.plan or {}, "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        **counts,
    }
