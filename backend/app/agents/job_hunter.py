"""Agent 1: Executive Job Hunter — runs daily at 5 AM."""
from __future__ import annotations

from datetime import datetime, timezone

from ..ai import client, skills
from ..ai.prompts import CANDIDATE_PROFILE, JOB_ARTIFACTS
from ..integrations import apollo, providers
from ..models import Application, Job
from .base import BaseAgent

LEADERSHIP_WORDS = ("director", "head", "vp", "chief", "cto")
CLOUD_WORDS = ("sre", "cloud", "infrastructure", "platform", "reliability")
AI_DATA_WORDS = ("ai", "data platform", "machine learning", "ml")
SCORE_THRESHOLD = 70
DAILY_TARGET = 25


class JobHunterAgent(BaseAgent):
    key = "job_hunter"
    name = "Executive Job Hunter"
    description = "Finds & scores executive roles, drafts artifacts, and auto-reaches hiring contacts."
    schedule_cron = "0 5 * * *"  # 5 AM

    @staticmethod
    def score_job(job: dict) -> tuple[int, dict]:
        title = (job.get("title") or "").lower()
        desc = (job.get("description") or "").lower()
        text = f"{title} {desc}"
        breakdown: dict[str, int] = {}
        if job.get("remote"):
            breakdown["remote"] = 25
        if (job.get("salary_min") or 0) >= 200_000:
            breakdown["salary_200k_plus"] = 25
        if any(w in title for w in LEADERSHIP_WORDS):
            breakdown["leadership"] = 20
        if any(w in text for w in CLOUD_WORDS):
            breakdown["cloud_sre_match"] = 20
        if any(w in text for w in AI_DATA_WORDS):
            breakdown["ai_data_platform"] = 10
        return sum(breakdown.values()), breakdown

    def execute(self) -> dict:
        raw = providers.fetch_jobs(limit=80)
        scored = []
        for job in raw:
            score, breakdown = self.score_job(job)
            if score >= SCORE_THRESHOLD:
                job["score"] = score
                job["score_breakdown"] = breakdown
                scored.append(job)
        scored.sort(key=lambda j: j["score"], reverse=True)
        top = scored[:DAILY_TARGET]

        sysp = skills.system_prompt("copywriting", "cold-email")
        saved, applied = 0, 0
        for job in top:
            artifacts = client.complete_json(JOB_ARTIFACTS.format(
                profile=CANDIDATE_PROFILE, title=job["title"], company=job["company"],
                location=job["location"], description=job["description"],
            ), system=sysp)
            row = Job(
                title=job["title"], company=job["company"], location=job["location"],
                remote=job["remote"], salary_min=job["salary_min"], salary_max=job["salary_max"],
                source=job["source"], url=job["url"], description=job["description"],
                score=job["score"], score_breakdown=job["score_breakdown"],
                resume_match=_as_text(artifacts.get("resume_match")),
                cover_letter=artifacts.get("cover_letter"),
                recruiter_msg=artifacts.get("recruiter_msg"),
                hiring_msg=artifacts.get("hiring_msg"),
            )
            self.db.add(row)
            self.db.flush()

            # Auto-apply via direct outreach: find a recruiter / hiring manager and reach out.
            contact = apollo.find_hiring_contact(job["company"])
            app_status, applied_at, notes = "New", None, "No hiring contact found"
            if contact and contact.get("email"):
                body = artifacts.get("hiring_msg") or artifacts.get("cover_letter")
                msg = self.dispatch_email(
                    entity_type="job", entity_id=row.id, to_email=contact["email"],
                    subject=f"Re: {job['title']} at {job['company']}", body=body, account="personal")
                notes = f"Contact: {contact.get('owner_name')} <{contact['email']}>"
                if msg.status == "Sent":
                    app_status, applied_at, applied = "Sent", datetime.now(timezone.utc), applied + 1
                else:
                    app_status = "Drafted"
                self.schedule_follow_ups("job", row.id)
            self.db.add(Application(job_id=row.id, status=app_status, applied_at=applied_at, notes=notes))
            saved += 1

        self.log_action("jobs_saved", entity="jobs", detail={"count": saved, "applied": applied})
        return {
            "summary": f"Found {len(scored)} qualified jobs, saved top {saved}, auto-reached {applied} hiring contacts.",
            "found": len(scored),
            "saved": saved,
            "applied": applied,
            "top_titles": [j["title"] for j in top[:10]],
        }


def _as_text(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        return "\n".join(f"- {v}" for v in value)
    return str(value)
