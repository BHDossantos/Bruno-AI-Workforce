"""Auto-apply engine — a LoopCV-style runner that submits job applications for you.

Takes the ≥threshold qualified jobs the hunter already sourced + prepared, routes
each by where it lives, and submits up to a daily cap (deliverability/rate-limit
safe). Lanes:
  - ats        — company ATS pages (Greenhouse/Lever/Ashby/Workday/…): the
                 legitimately-automatable lane. Auto-submitted in compliant+aggressive.
  - easy_apply — LinkedIn/Indeed Easy Apply: only in 'aggressive' mode, driven via
                 YOUR stored session cookies (violates those platforms' ToS — opt-in).
  - other      — everything else: left for the one-click Apply Queue.

Everything is gated behind control.auto_apply_mode (off | compliant | aggressive)
and degrades to "queued" when browser automation isn't available, so it never
silently fails or submits when it shouldn't.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from . import browser, control
from .config import settings
from .models import Application, Job

log = logging.getLogger("bruno.autoapply")

# Company-ATS hosts — applications here live on the employer's own site and are the
# legitimately-automatable lane.
ATS_HOSTS = (
    "greenhouse.io", "boards.greenhouse.io", "job-boards.greenhouse.io",
    "lever.co", "jobs.lever.co", "ashbyhq.com", "jobs.ashbyhq.com",
    "myworkdayjobs.com", "bamboohr.com", "breezy.hr", "jobvite.com",
    "smartrecruiters.com", "icims.com", "workable.com", "applytojob.com",
    "teamtailor.com", "recruitee.com", "personio.com", "rippling.com",
    "ashbyhq.com", "join.com", "pinpointhq.com",
)
EASY_APPLY_HOSTS = ("linkedin.com", "indeed.com")


def _lane(url: str | None) -> str:
    host = (urlparse(url or "").hostname or "").lower()
    if not host:
        return "other"
    if any(host == h or host.endswith("." + h) or h in host for h in ATS_HOSTS):
        return "ats"
    if any(host == h or host.endswith("." + h) for h in EASY_APPLY_HOSTS):
        return "easy_apply"
    return "other"


def _cookie_domain(lane_host_url: str | None) -> str:
    host = (urlparse(lane_host_url or "").hostname or "").lower()
    if "linkedin" in host:
        return ".linkedin.com"
    if "indeed" in host:
        return ".indeed.com"
    return "." + host if host else ""


def _session_cookies(db: Session, url: str | None) -> list | None:
    """Build Playwright cookies from the user's stored session for an Easy-Apply
    portal. Stored on the linkedin/indeed connector as 'session_cookies' — a raw
    'name=value; name2=value2' string copied from the logged-in browser."""
    from .integrations import connectors
    host = (urlparse(url or "").hostname or "").lower()
    provider = "linkedin" if "linkedin" in host else ("indeed" if "indeed" in host else None)
    if not provider:
        return None
    creds = connectors.get_credentials(db, provider) or {}
    raw = creds.get("session_cookies") or creds.get("cookies")
    if not raw:
        return None
    domain = _cookie_domain(url)
    out = []
    for part in str(raw).split(";"):
        if "=" not in part:
            continue
        name, _, value = part.strip().partition("=")
        if name and value:
            out.append({"name": name.strip(), "value": value.strip(),
                        "domain": domain, "path": "/"})
    return out or None


def _today_start() -> datetime:
    return datetime.combine(date.today(), datetime.min.time(), tzinfo=timezone.utc)


def _applied_today(db: Session) -> int:
    """How many the engine already submitted today (so we honor the daily cap)."""
    return int(db.query(Application).filter(
        Application.applied_at >= _today_start(),
        Application.notes.ilike("%auto-applied%")).count())


def run_auto_apply(db: Session, limit: int | None = None) -> dict:
    """Submit qualified, prepared applications up to the daily cap. Returns a
    summary; never raises (one bad job can't stop the batch)."""
    mode = control.auto_apply_mode(db)
    if mode == "off":
        return {"ok": False, "mode": "off", "reason": "auto-apply is off — turn it on to submit",
                "submitted": 0, "queued": 0}
    if control.is_paused_safe(db):
        return {"ok": False, "mode": mode, "reason": "emergency stop engaged", "submitted": 0, "queued": 0}

    cap = limit if limit is not None else settings.auto_apply_daily_cap
    remaining = max(0, cap - _applied_today(db))
    automation = browser.is_automation_ready()
    threshold = settings.job_score_threshold

    submitted = queued = review = failed = 0
    if remaining <= 0:
        return {"ok": True, "mode": mode, "submitted": 0, "queued": 0,
                "reason": f"daily cap of {cap} already reached", "capped": True}

    # Jobs not yet handled: no Application, or one still 'New'/'Preparing'.
    handled = {a.job_id: a for a in db.query(Application).all()}
    done = {"Applied", "Sent", "Skipped", "Replied", "Interested", "Closed Won", "Closed Lost"}
    jobs = (db.query(Job).filter(Job.score >= threshold)
            .order_by(Job.score.desc(), Job.found_at.desc()).limit(max(remaining * 4, 20)).all())

    for job in jobs:
        if remaining <= 0:
            break
        app = handled.get(job.id)
        if app and app.status in done:
            continue
        lane = _lane(job.url)
        # Decide whether THIS lane is auto-submittable in the current mode.
        if lane == "other":
            queued += 1
            continue
        if lane == "easy_apply" and mode != "aggressive":
            queued += 1
            continue
        if not automation:
            queued += 1  # would auto-submit, but Playwright/browser isn't available here
            continue
        cookies = _session_cookies(db, job.url) if lane == "easy_apply" else None
        if lane == "easy_apply" and not cookies:
            queued += 1  # aggressive mode but no stored session — can't log in, so queue
            continue
        try:
            task = browser.autoprepare_for_job(db, job)
            if not task:
                failed += 1
                continue
            result = browser.run(db, str(task.id), auto_submit=True, cookies=cookies)
            ok = bool(result and result.status == "submitted")
            if not app:
                app = Application(job_id=job.id)
                db.add(app)
            if ok:
                app.status = "Applied"
                app.applied_at = datetime.now(timezone.utc)
                app.notes = f"auto-applied via {lane}"
                submitted += 1
                remaining -= 1
            else:
                app.status = app.status or "New"
                app.notes = f"auto-apply prepared ({lane}) — needs review"
                review += 1
            db.commit()
        except Exception as exc:  # one bad job must not stop the batch
            log.warning("auto-apply failed for job %s: %s", job.id, exc)
            db.rollback()
            failed += 1

    return {"ok": True, "mode": mode, "cap": cap, "submitted": submitted,
            "queued": queued, "needs_review": review, "failed": failed,
            "automation": automation}
