"""Mission Control — the single morning command screen.

Aggregates today's real activity, the goal-vs-actual scoreboard, pending
approvals and the emergency-stop state into one payload so the home screen can
answer "what's happening and what needs me right now?".
"""
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import control
from ..database import get_db
from ..security import require_role as _rr
from ..models import (Application, ContentItem, Job, Lead, Message, Restaurant)
from ..security import require_role

router = APIRouter(prefix="/mission", tags=["mission"])
_read = require_role("admin", "operator", "viewer")

# Daily targets per area (sensible defaults; the goal score is target vs today).
_TARGETS = {
    "Social posts": 9, "Insurance leads": 50, "BnB Global leads": 50,
    "SavoryMind leads": 50, "Outreach sent": 50, "Replies": 10, "Job applications": 10,
}


def _today_start() -> datetime:
    return datetime.combine(date.today(), datetime.min.time(), tzinfo=timezone.utc)


@router.get("/control")
def mission_control(db: Session = Depends(get_db), _=Depends(_read)):
    start = _today_start()

    def c(model, *filters) -> int:
        return int(db.query(func.count()).select_from(model).filter(*filters).scalar() or 0)

    posts = c(ContentItem, ContentItem.created_at >= start,
              ContentItem.status.in_(["scheduled", "needs_approval", "ready", "generated", "published"]))
    ins_leads = c(Lead, Lead.created_at >= start, Lead.segment.in_(["commercial", "personal"]))
    bnb_leads = c(Lead, Lead.created_at >= start, Lead.segment == "consulting")
    restaurants = c(Restaurant, Restaurant.kind == "prospect", Restaurant.created_at >= start)
    sent = c(Message, Message.direction == "outbound", Message.created_at >= start,
             Message.status.in_(["Sent", "Queued"]))
    replies = c(Message, Message.direction == "inbound", Message.created_at >= start)
    apps = c(Application, Application.created_at >= start)
    jobs_found = c(Job, Job.found_at >= start)

    today = {
        "posts": posts, "insurance_leads": ins_leads, "bnb_leads": bnb_leads,
        "savorymind_leads": restaurants, "outreach_sent": sent, "replies": replies,
        "applications": apps, "jobs_found": jobs_found,
    }
    actuals = {
        "Social posts": posts, "Insurance leads": ins_leads, "BnB Global leads": bnb_leads,
        "SavoryMind leads": restaurants, "Outreach sent": sent, "Replies": replies,
        "Job applications": apps,
    }
    goals = [{
        "area": area, "target": target, "today": actuals.get(area, 0),
        "status": "on track" if actuals.get(area, 0) >= target else "behind",
    } for area, target in _TARGETS.items()]

    # Pending approvals (mirror /approvals/count).
    pending = (c(ContentItem, ContentItem.status == "needs_approval")
               + c(Lead, Lead.status == "Drafted", Lead.email.isnot(None))
               + c(Restaurant, Restaurant.kind == "prospect", Restaurant.status == "Drafted",
                   Restaurant.email.isnot(None)))

    return {
        "paused": control.is_paused_safe(db),
        "today": today,
        "goals": goals,
        "approvals_pending": pending,
    }


@router.post("/work-pipeline")
def work_pipeline(db: Session = Depends(get_db), _=Depends(_rr("admin", "operator"))):
    """Source + draft across every revenue line and queue it all for approval."""
    from .. import pipeline_run
    return pipeline_run.work_pipeline(db)
