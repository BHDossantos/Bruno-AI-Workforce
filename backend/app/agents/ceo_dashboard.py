"""Agent 6: CEO Dashboard — runs daily at 10 AM.

Aggregates the day's output from all agents, asks the model for the highest-ROI
actions, persists a daily report + KPI metrics, and emails the executive brief.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone

from sqlalchemy import func

from ..ai import client
from ..ai.prompts import CEO_BRIEF
from ..integrations import mailer
from ..config import settings
from ..models import (
    Application,
    DailyReport,
    FollowUp,
    InstagramTarget,
    Influencer,
    Job,
    KpiMetric,
    Lead,
    Message,
    MusicPlaylist,
    Restaurant,
)
from .base import BaseAgent


class CEODashboardAgent(BaseAgent):
    key = "ceo_dashboard"
    name = "CEO Dashboard Agent"
    description = "Aggregates all agent output into one daily executive brief and emails it."
    schedule_cron = "0 10 * * *"  # 10 AM

    def _today_counts(self) -> dict:
        start = datetime.combine(date.today(), datetime.min.time(), tzinfo=timezone.utc)

        def count(model, ts_col, **filters):
            q = self.db.query(func.count()).select_from(model).filter(ts_col >= start)
            for k, v in filters.items():
                q = q.filter(getattr(model, k) == v)
            return q.scalar() or 0

        emails_sent = self.db.query(func.count()).select_from(Message).filter(
            Message.channel == "email", Message.sent_at >= start).scalar() or 0
        insurance_leads = self.db.query(func.count()).select_from(Lead).filter(
            Lead.created_at >= start, Lead.segment.in_(["commercial", "personal"])).scalar() or 0
        consulting_leads = self.db.query(func.count()).select_from(Lead).filter(
            Lead.created_at >= start, Lead.segment == "consulting").scalar() or 0
        return {
            "jobs_found": count(Job, Job.found_at),
            "insurance_leads": insurance_leads,
            "consulting_leads": consulting_leads,
            "restaurant_prospects": count(Restaurant, Restaurant.created_at, kind="prospect"),
            "music_playlists": count(MusicPlaylist, MusicPlaylist.created_at),
            "influencers": count(Influencer, Influencer.created_at),
            "instagram_targets": count(InstagramTarget, InstagramTarget.created_at),
            "emails_sent_today": emails_sent,
            "applications": self.db.query(func.count()).select_from(Application).scalar() or 0,
            "follow_ups_due": self.db.query(func.count()).select_from(FollowUp)
                .filter(FollowUp.due_date <= date.today(), FollowUp.completed.is_(False)).scalar() or 0,
        }

    def _highlights(self) -> dict:
        start = datetime.combine(date.today(), datetime.min.time(), tzinfo=timezone.utc)
        top_jobs = (self.db.query(Job).filter(Job.found_at >= start)
                    .order_by(Job.score.desc()).limit(5).all())
        top_leads = (self.db.query(Lead).filter(Lead.created_at >= start)
                     .order_by(Lead.score.desc()).limit(5).all())
        return {
            "best_jobs": [{"title": j.title, "company": j.company, "score": j.score} for j in top_jobs],
            "best_insurance": [{"company": l.company_name, "category": l.category, "score": l.score}
                               for l in top_leads],
        }

    def execute(self) -> dict:
        counts = self._today_counts()
        highlights = self._highlights()
        raw = {"counts": counts, "highlights": highlights}

        brief = client.complete_json(CEO_BRIEF.format(data=json.dumps(raw, default=str)))
        if not brief:
            brief = {
                "summary": "Daily brief generated from agent output (set OPENAI_API_KEY for AI synthesis).",
                "top_actions": [], "urgent_follow_ups": [],
                "recommended_focus": "Review highest-scoring jobs and leads first.",
            }

        report = DailyReport(
            report_date=date.today(),
            summary=brief.get("summary"),
            top_actions=brief,
            metrics=counts,
        )
        self.db.add(report)

        for name, value in counts.items():
            self.db.add(KpiMetric(metric_date=date.today(), name=name, value=value))

        # Email the brief (no-op without SMTP configured).
        html = self._render_html(brief, counts, highlights)
        if settings.report_to_email:
            report.emailed = mailer.send_email(
                to=settings.report_to_email,
                subject=f"Bruno AI Workforce — Daily Brief {date.today()}",
                html=html,
            )

        self.log_action("daily_report_created", entity="daily_reports",
                        detail={"counts": counts, "emailed": report.emailed})
        return {
            "summary": brief.get("summary"),
            "counts": counts,
            "emailed": report.emailed,
        }

    @staticmethod
    def _render_html(brief: dict, counts: dict, highlights: dict) -> str:
        actions = "".join(
            f"<li><b>{a.get('action','')}</b> — {a.get('why','')} <i>({a.get('area','')})</i></li>"
            for a in (brief.get("top_actions") or []) if isinstance(a, dict)
        )
        kpis = "".join(f"<li>{k.replace('_', ' ').title()}: <b>{v}</b></li>" for k, v in counts.items())
        return f"""
        <h2>Daily Executive Brief — {date.today()}</h2>
        <p>{brief.get('summary', '')}</p>
        <h3>Top ROI Actions</h3><ul>{actions or '<li>No actions generated.</li>'}</ul>
        <h3>KPIs</h3><ul>{kpis}</ul>
        <h3>Recommended Focus</h3><p>{brief.get('recommended_focus', '')}</p>
        """
