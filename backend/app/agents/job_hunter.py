"""Agent 1: Executive Job Hunter — runs daily at 5 AM."""
from __future__ import annotations

from datetime import datetime, timezone

from .. import memory
from ..ai import client, skills
from ..ai.prompts import CANDIDATE_PROFILE, JOB_ARTIFACTS
from ..config import settings
from ..integrations import apollo, providers
from ..models import Application, Job
from .base import BaseAgent

# Tuned to Bruno's résumé: Director-level SRE / Cloud Ops leadership.
LEADERSHIP_WORDS = ("director", "head of", "head ", "vp", "vice president", "chief",
                    "cto", "principal", "senior manager", "sr manager")
CLOUD_WORDS = ("sre", "site reliability", "cloud", "infrastructure", "platform",
               "devops", "kubernetes", "terraform", "reliability", "observability")
AI_DATA_WORDS = ("ai", "artificial intelligence", "data platform", "machine learning",
                 "ml", "mlops", "data engineering")


class JobHunterAgent(BaseAgent):
    key = "job_hunter"
    name = "Executive Job Hunter"
    description = "Finds & scores executive roles, drafts artifacts, and auto-reaches hiring contacts."
    schedule_cron = "0 5 * * *"  # 5 AM

    @staticmethod
    def score_job(job: dict) -> tuple[int, dict]:
        """0-100 fit score weighted to title/skill match so genuinely-relevant
        roles clear the 75% bar even when a board hides the salary."""
        title = (job.get("title") or "").lower()
        desc = (job.get("description") or "").lower()
        text = f"{title} {desc}"
        breakdown: dict[str, int] = {}
        if any(w in title for w in LEADERSHIP_WORDS):
            breakdown["leadership"] = 30
        if any(w in text for w in CLOUD_WORDS):
            breakdown["cloud_sre_match"] = 30
        if any(w in text for w in AI_DATA_WORDS):
            breakdown["ai_data_platform"] = 15
        if job.get("remote"):
            breakdown["remote"] = 15
        if (job.get("salary_min") or 0) >= 200_000:
            breakdown["salary_200k_plus"] = 10
        return min(100, sum(breakdown.values())), breakdown

    def execute(self) -> dict:
        threshold = settings.job_score_threshold
        target = settings.job_daily_target
        raw = providers.fetch_jobs(limit=settings.job_fetch_limit)
        scored = []
        for job in raw:
            score, breakdown = self.score_job(job)
            if score >= threshold:
                job["score"] = score
                job["score_breakdown"] = breakdown
                scored.append(job)
        scored.sort(key=lambda j: j["score"], reverse=True)
        top = scored[:target]

        # Don't re-add jobs we already have (dedupe by apply URL across runs).
        existing_urls = {u for (u,) in self.db.query(Job.url).filter(Job.url.isnot(None)).all()}
        top = [j for j in top if j.get("url") not in existing_urls][:target]

        # ── Phase 1: persist scored jobs FAST (no AI) and commit, so the apply
        # queue always has the roles even if enrichment is slow/errors. ──────────
        pairs: list[tuple[Job, dict]] = []
        for job in top:
            row = Job(
                title=job["title"], company=job["company"], location=job["location"],
                remote=job["remote"], salary_min=job["salary_min"], salary_max=job["salary_max"],
                source=job["source"], url=job["url"], description=job["description"],
                score=job["score"], score_breakdown=job["score_breakdown"],
            )
            self.db.add(row)
            pairs.append((row, job))
        self.db.commit()
        saved = len(pairs)

        # ── Phase 2: AI application materials + a 'New' Application (queued for
        # one-click apply). Resilient per-job. We do NOT bot-submit anywhere. ─────
        sysp = skills.system_prompt("copywriting", "cold-email")
        enriched = applied = 0
        for row, job in pairs:
            try:
                mem_ctx = memory.context_block(self.db, job.get("company") or "")
                jsysp = f"{sysp}\n\n{mem_ctx}" if mem_ctx else sysp
                artifacts = client.complete_json(JOB_ARTIFACTS.format(
                    profile=CANDIDATE_PROFILE, title=job["title"], company=job["company"],
                    location=job["location"], description=job["description"],
                ), system=jsysp)
                artifacts = artifacts if isinstance(artifacts, dict) else {}
                row.resume_match = _as_text(artifacts.get("resume_match"))
                row.cover_letter = artifacts.get("cover_letter")
                row.recruiter_msg = artifacts.get("recruiter_msg")
                row.hiring_msg = artifacts.get("hiring_msg")

                # Optional: if a hiring contact is found (Apollo), email them directly.
                contact = apollo.find_hiring_contact(job["company"])
                app_status, applied_at, notes = "New", None, "Queued for one-click apply"
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
                enriched += 1
                self.db.commit()
            except Exception:  # one bad job must not drop the rest
                self.db.rollback()

        self.log_action("jobs_saved", entity="jobs", detail={"count": saved, "applied": applied})
        return {
            "summary": f"Found {len(scored)} qualified jobs, queued top {saved} for one-click apply "
                       f"({applied} hiring contacts emailed directly).",
            "found": len(scored),
            "saved": saved,
            "enriched": enriched,
            "applied": applied,
            "top_titles": [j["title"] for j in top[:10]],
        }


def _as_text(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        return "\n".join(f"- {v}" for v in value)
    return str(value)
