"""Funnel & performance analytics across every channel.

Builds a real marketing/sales funnel (Sourced → Contacted → Opened → Replied →
Interested → Won) from the lead/restaurant lifecycle statuses, plus reply rates,
SMS, jobs, and a 14-day activity series — so you can see what's working.
"""
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Application, Lead, Message, Restaurant
from ..security import require_role

router = APIRouter(prefix="/analytics", tags=["analytics"])
_read = require_role("admin", "operator", "viewer")

# How far each status sits along the funnel.
_STAGE_INDEX = {
    "New": 0, "Drafted": 1, "Sent": 2, "Opened": 3, "Replied": 4,
    "Follow-up Needed": 4, "Interested": 5, "Closed Won": 6, "Closed Lost": 2,
}
# Funnel levels shown to the user: (label, minimum stage index to count).
_FUNNEL = [("Sourced", 0), ("Contacted", 2), ("Opened", 3),
           ("Replied", 4), ("Interested", 5), ("Won", 6)]


def _funnel(statuses: list[str]) -> list[dict]:
    idx = [_STAGE_INDEX.get(s, 0) for s in statuses]
    return [{"stage": label, "count": sum(1 for i in idx if i >= threshold)}
            for label, threshold in _FUNNEL]


@router.get("/overview")
def overview(db: Session = Depends(get_db), _=Depends(_read)):
    lead_statuses = [s for (s,) in db.query(Lead.status).all()]
    rest_statuses = [s for (s,) in db.query(Restaurant.status)
                     .filter(Restaurant.kind == "prospect").all()]
    all_statuses = lead_statuses + rest_statuses

    emails_sent = db.query(func.count()).select_from(Message).filter(
        Message.channel == "email", Message.sent_at.isnot(None)).scalar() or 0
    emails_drafted = db.query(func.count()).select_from(Message).filter(
        Message.channel == "email", Message.status == "Drafted").scalar() or 0
    replies = db.query(func.count()).select_from(Message).filter(
        Message.direction == "inbound").scalar() or 0
    sms_sent = db.query(func.count()).select_from(Message).filter(
        Message.channel == "sms", Message.direction == "outbound").scalar() or 0
    interested = sum(1 for s in all_statuses if _STAGE_INDEX.get(s, 0) >= 5)
    won = sum(1 for s in all_statuses if s == "Closed Won")
    applied = db.query(func.count()).select_from(Application).filter(
        Application.status.in_(["Applied", "Sent"])).scalar() or 0
    queued = db.query(func.count()).select_from(Application).filter(
        Application.status == "New").scalar() or 0

    # 14-day activity: outbound sends + inbound replies per day.
    since = datetime.now(timezone.utc) - timedelta(days=14)
    sent_by_day = dict(db.query(func.date(Message.sent_at), func.count())
                       .filter(Message.sent_at >= since, Message.direction == "outbound")
                       .group_by(func.date(Message.sent_at)).all())
    repl_by_day = dict(db.query(func.date(Message.created_at), func.count())
                       .filter(Message.created_at >= since, Message.direction == "inbound")
                       .group_by(func.date(Message.created_at)).all())
    activity = []
    for d in range(14, -1, -1):
        day = date.today() - timedelta(days=d)
        activity.append({"date": day.isoformat(),
                         "sent": int(sent_by_day.get(day, 0)),
                         "replied": int(repl_by_day.get(day, 0))})

    reply_rate = round(100 * replies / emails_sent, 1) if emails_sent else 0.0
    return {
        "kpis": {
            "leads_total": len(lead_statuses),
            "restaurant_prospects": len(rest_statuses),
            "emails_sent": emails_sent,
            "emails_drafted": emails_drafted,
            "replies": replies,
            "reply_rate_pct": reply_rate,
            "interested": interested,
            "won": won,
            "sms_sent": sms_sent,
            "jobs_queued": queued,
            "jobs_applied": applied,
        },
        "funnel": _funnel(all_statuses),
        "channels": {
            "insurance": _funnel([s for s, seg in db.query(Lead.status, Lead.segment).all()]),
            "savorymind": _funnel(rest_statuses),
        },
        "activity_14d": activity,
    }
