"""Daily reports + dashboard KPI routes."""
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    Application,
    DailyReport,
    FollowUp,
    InstagramTarget,
    Job,
    Lead,
    Message,
    MusicPlaylist,
    Restaurant,
)
from datetime import date as _date
from ..schemas import ReportOut
from ..security import require_role

router = APIRouter(tags=["dashboard"])
_read = require_role("admin", "operator", "viewer")


@router.get("/reports", response_model=list[ReportOut])
def list_reports(limit: int = 30, db: Session = Depends(get_db), _=Depends(_read)):
    return db.query(DailyReport).order_by(DailyReport.report_date.desc()).limit(limit).all()


@router.get("/reports/latest", response_model=ReportOut | None)
def latest_report(db: Session = Depends(get_db), _=Depends(_read)):
    return db.query(DailyReport).order_by(DailyReport.report_date.desc()).first()


@router.get("/dashboard/summary")
def summary(db: Session = Depends(get_db), _=Depends(_read)):
    """KPI summary for the home dashboard (today's totals)."""
    start = datetime.combine(date.today(), datetime.min.time(), tzinfo=timezone.utc)

    def c(model, ts, **f):
        q = db.query(func.count()).select_from(model).filter(ts >= start)
        for k, v in f.items():
            q = q.filter(getattr(model, k) == v)
        return q.scalar() or 0

    emails_sent_today = db.query(func.count()).select_from(Message).filter(
        Message.channel == "email", Message.sent_at >= start).scalar() or 0
    replies = db.query(func.count()).select_from(Message).filter(Message.status == "Replied").scalar() or 0
    followups_due = db.query(func.count()).select_from(FollowUp).filter(
        FollowUp.due_date <= _date.today(), FollowUp.completed.is_(False)).scalar() or 0
    applications = db.query(func.count()).select_from(Application).scalar() or 0
    sms_threads = db.query(func.count(func.distinct(Message.to_email))).filter(
        Message.channel == "sms").scalar() or 0

    insurance_leads = db.query(func.count()).select_from(Lead).filter(
        Lead.created_at >= start, Lead.segment.in_(["commercial", "personal"])).scalar() or 0
    consulting_leads = db.query(func.count()).select_from(Lead).filter(
        Lead.created_at >= start, Lead.segment == "consulting").scalar() or 0

    return {
        "date": date.today().isoformat(),
        "jobs_found": c(Job, Job.found_at),
        "insurance_leads": insurance_leads,
        "consulting_leads": consulting_leads,
        "restaurant_prospects": c(Restaurant, Restaurant.created_at, kind="prospect"),
        "music_playlists": c(MusicPlaylist, MusicPlaylist.created_at),
        "instagram_targets": c(InstagramTarget, InstagramTarget.created_at),
        "emails_sent_today": emails_sent_today,
        "replies": replies,
        "follow_ups_due": followups_due,
        "applications": applications,
        "sms_threads": sms_threads,
        "totals": {
            "jobs": db.query(func.count()).select_from(Job).scalar() or 0,
            "leads": db.query(func.count()).select_from(Lead).scalar() or 0,
            "restaurants": db.query(func.count()).select_from(Restaurant).scalar() or 0,
        },
    }
