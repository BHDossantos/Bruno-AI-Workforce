"""APScheduler setup — the always-on 24/7 engine.

This drives the ENTIRE business autonomously from a single long-running process:
every agent on its daily cron PLUS the per-platform content loops, publishing,
lead passes, auto-outreach, newsletters, music releases, follow-ups, inbound
sync and the weekly board report. With this running, the only operational
requirement for full autonomy is:

  • deploy with at least one always-on instance (Cloud Run: --min-instances=1),
    so the scheduler isn't reaped when the service scales to zero, and
  • set OPENAI_API_KEY so the content/outreach can actually be written.

Every job is failure-isolated (one failure never stops the others) and every
worker is independently idempotent (cadence caps, daily send caps, same-day
dedupe), so overlapping runs or an external Cloud Scheduler hitting /cron/* in
parallel can never double-post or double-send.
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .agents import AGENTS
from .config import settings
from .database import SessionLocal

log = logging.getLogger("bruno.scheduler")
_scheduler: BackgroundScheduler | None = None

# Insurance-only autonomy (AUTONOMY_PROFILE=insurance) runs just these — every
# other agent/job (music, bnb, savorymind, instagram, job-hunter, foundation,
# content publishing, board report…) is skipped so it stops burning AI spend.
_INSURANCE_AGENTS = {"insurance", "commercial_finder", "home_finder", "auto_finder",
                     "homeowner", "referral_partner", "follow_up_agent", "review_referral"}
_INSURANCE_JOBS = {"client_autoscale", "leads", "auto_outreach", "flush_drafts",
                   "followups", "booking_nudges", "lifecycle", "outreach_digest",
                   "refresh_tokens", "selfcheck", "referrals"}


def _insurance_only() -> bool:
    return (settings.autonomy_profile or "all").strip().lower() == "insurance"


def scheduled_plan() -> tuple[dict, dict]:
    """(agents, jobs) that WOULD be scheduled given the current autonomy profile.
    Pure/testable — start_scheduler registers exactly these."""
    ins = _insurance_only()
    agents = {k: v for k, v in AGENTS.items() if not ins or k in _INSURANCE_AGENTS}
    jobs = {k: v for k, v in _JOBS.items() if not ins or k in _INSURANCE_JOBS}
    return agents, jobs


def _with_db(fn, label: str):
    """Run a worker with a fresh DB session, failure-isolated. Skips entirely when
    the Emergency Stop is engaged."""
    db = SessionLocal()
    try:
        from . import control
        if control.is_paused_safe(db):
            log.info("Skipping %s — agents paused (emergency stop)", label)
            return None
        return fn(db)
    except Exception:  # pragma: no cover - defensive; one job must never break others
        log.exception("Scheduled job %s failed", label)
    finally:
        db.close()


def _run_agent(key: str) -> None:
    _with_db(lambda db: AGENTS[key](db).run(), f"agent:{key}")


# ── Whole-business workers (mirror the /cron/* endpoints, no token needed) ─────
def _run_ceo(db):
    from . import alerts, commanders
    result = commanders.run_ceo(db)
    alerts.check_run("daily cycle", result)
    return result


def _run_platform_loops(db):
    from . import platform_loops
    return platform_loops.run_all(db)


def _publish_due(db):
    from . import content_factory
    return content_factory.publish_due(db)


def _publish_blog_due(db):
    from . import content_factory
    return content_factory.publish_blog_due(db)


def _run_leads(db):
    """Lead-gen + cold-email pass for every outreach business (4×/day).
    Insurance-only mode drops the SavoryMind/BnB passes."""
    keys = ["commercial_finder", "home_finder", "auto_finder", "insurance", "referral_partner"]
    if not _insurance_only():
        keys += ["savorymind", "bnbglobal"]
    out = {}
    for key in keys:
        cls = AGENTS.get(key)
        if cls:
            try:
                out[key] = cls(db).run()
            except Exception as exc:  # one agent must not stop the rest
                out[key] = {"error": str(exc)}
    return out


def _auto_outreach(db):
    from . import bulk_outreach, contacts_outreach
    return {
        "leads": bulk_outreach.dispatch_leads(db),
        "restaurants": bulk_outreach.dispatch_restaurants(db),
        "contacts": contacts_outreach.run(db),
    }


def _flush_hot_drafts(db):
    """Auto-send the personalized DRAFTED emails + texts — HOT LEADS FIRST — so a
    fresh EverQuote lead gets its first touch on its own instead of waiting for a
    manual 'Send drafts' click. Only fires when the operator has enabled auto-send
    (full-auto mode OR Outreach Autopilot); otherwise the drafts wait for review.
    Bounded per run + compliance-gated (daily cap, texting hours, opt-out) so it
    paces itself and protects deliverability."""
    from . import control, outreach, sms_engine
    if control.is_paused_safe(db):
        return {"skipped": "paused"}
    if control.get_mode(db) != "auto" and not control.outreach_autopilot(db):
        return {"skipped": "auto-send off (turn on Outreach Autopilot to enable)"}
    return {
        "email": outreach.send_email_drafts(db, limit=25),
        "sms": sms_engine.send_sms_drafts(db, limit=25),
    }


def _run_newsletters(db):
    from . import newsletters
    return newsletters.run(db)


def _run_music_releases(db):
    from . import music_release
    return music_release.run_due(db)


def _run_referrals(db):
    from . import referrals
    return referrals.run(db)


def _run_board_report(db):
    from . import board_report
    return board_report.build(db)


def _refresh_tokens(db):
    from .integrations import oauth_refresh
    return oauth_refresh.refresh_all(db)


def _sync_content_metrics(db):
    from . import content_analytics
    return content_analytics.sync_metrics(db)


def _sync_inbound(db):
    from .inbound import sync_replies
    return sync_replies(db)


def _run_followups(db):
    from . import lead_sequence
    from .followups import process_due_followups
    # Enroll any newly-contacted lead into the multi-touch cadence (hot first),
    # then execute everything due across email / SMS / call today.
    enrolled = lead_sequence.enroll_active_leads(db)
    processed = process_due_followups(db)
    return {"enrolled": enrolled, **processed}


def _run_lifecycle(db):
    from . import lead_lifecycle
    return lead_lifecycle.run(db)


def _run_booking_nudges(db):
    from . import booking_nudge
    return booking_nudge.run(db)


def _run_outreach_digest(db):
    from . import outreach_digest
    return outreach_digest.send(db)


def _run_selfcheck(db):
    from . import selfcheck
    return selfcheck.run(db)


def _run_auto_apply(db):
    from . import autoapply
    return autoapply.run_auto_apply(db)


def _run_client_autoscale(db):
    from . import client_goal
    return client_goal.autoscale(db)


# job_id -> (worker, cron expression). These run the marketing/advertising/sales
# engine around the clock so the platform operates without any external scheduler.
_JOBS: dict[str, tuple] = {
    # Full CEO → Commander → Agent cycle each morning (rolls up objectives).
    "ceo_daily":        (_run_ceo, "0 6 * * *"),
    # Content cadence: top every platform up to its daily target, 4×/day.
    "platform_loops":   (_run_platform_loops, "0 7,11,15,19 * * *"),
    # Publish scheduled social posts that are due — hourly so timed posts go out.
    "publish_content":  (_publish_due, "5 * * * *"),
    # Publish approved blog posts to Medium daily.
    "publish_blog":     (_publish_blog_due, "20 12 * * *"),
    # Size the outreach machine to the daily client target before sourcing starts,
    # so the day's lead + send volume is calibrated to actually hit the goal.
    "client_autoscale": (_run_client_autoscale, "30 5 * * *"),
    # Lead sourcing + cold email, 4×/day (insurance + SavoryMind + BnB Global).
    "leads":            (_run_leads, "0 8,12,16,20 * * *"),
    # Drain the outreach backlog (leads + restaurants + warm contacts), 2×/day.
    "auto_outreach":    (_auto_outreach, "30 9,15 * * *"),
    # Auto-send personalized DRAFTS — hot leads first — hourly during the day so a
    # fresh EverQuote lead gets its first email/text fast (speed wins). Only acts
    # when Outreach Autopilot / full-auto is on; otherwise drafts wait for review.
    "flush_drafts":     (_flush_hot_drafts, "20 8-20 * * *"),
    # Per-funnel newsletters to warm repliers, Mon/Wed/Fri.
    "newsletters":      (_run_newsletters, "0 11 * * 1,3,5"),
    # Build any due music release kit (release-as-eras), daily.
    "music_releases":   (_run_music_releases, "0 10 * * *"),
    # Ask engaged leads for referrals, weekly.
    "referrals":        (_run_referrals, "0 13 * * 2"),
    # Weekly executive board report.
    "board_report":     (_run_board_report, "0 8 * * 1"),
    # Keep OAuth tokens fresh so connections never silently expire.
    "refresh_tokens":   (_refresh_tokens, "0 5 * * *"),
    # Refresh engagement metrics for the learning loop, daily.
    "content_metrics":  (_sync_content_metrics, "0 21 * * *"),
    # Move the pipeline itself — repair statuses, log every stage transition,
    # flag speed breaches + return-eligible dead-ends. Every 3 hours so the
    # cockpit + AI timeline stay live without manual card-moving.
    "lifecycle":        (_run_lifecycle, "20 */3 * * *"),
    # Send any due follow-ups, daily.
    "followups":        (_run_followups, "0 11 * * *"),
    # Nudge interested-but-not-booked prospects toward the calendar, daily.
    "booking_nudges":   (_run_booking_nudges, "30 12 * * *"),
    # Email the operator the day's outreach numbers + top actions, every morning.
    "outreach_digest":  (_run_outreach_digest, "0 8 * * *"),
    # Self-check + auto-correct core features daily (re-seed, refresh creds, flag).
    "selfcheck":        (_run_selfcheck, "0 4 * * *"),
    # Auto-apply to qualified jobs (self-gates: only acts when its mode != off),
    # after the 5 AM job sourcing — so it works the freshly-prepared queue.
    "auto_apply":       (_run_auto_apply, "30 9 * * *"),
}


def start_scheduler() -> BackgroundScheduler | None:
    global _scheduler
    if not settings.enable_scheduler:
        log.info("Scheduler disabled (ENABLE_SCHEDULER=false)")
        return None
    _scheduler = BackgroundScheduler(timezone=settings.timezone)

    # Insurance-only mode: register just the insurance agents/jobs so the rest of
    # the businesses stop making scheduled AI calls (the main cost driver).
    ins = _insurance_only()
    agents, jobs = scheduled_plan()

    # Each agent on its own daily schedule (job hunter, instagram planner, etc.).
    for key, cls in agents.items():
        _scheduler.add_job(
            _run_agent, CronTrigger.from_crontab(cls.schedule_cron, timezone=settings.timezone),
            args=[key], id=f"agent:{key}", replace_existing=True,
        )

    # The whole-business workers (content loops, publishing, leads, outreach, …).
    for job_id, (fn, cron) in jobs.items():
        _scheduler.add_job(
            lambda fn=fn, job_id=job_id: _with_db(fn, job_id),
            CronTrigger.from_crontab(cron, timezone=settings.timezone),
            id=job_id, replace_existing=True,
        )
        log.info("Scheduled %s at cron '%s'", job_id, cron)

    # Poll both mailboxes for replies every 2 hours (no-op if Gmail unconfigured).
    _scheduler.add_job(lambda: _with_db(_sync_inbound, "inbound_sync"),
                       IntervalTrigger(hours=2), id="inbound_sync", replace_existing=True)
    _scheduler.start()
    log.info("24/7 engine started — %d agents + %d business jobs%s",
             len(agents), len(jobs), " (insurance-only)" if ins else "")
    return _scheduler


def shutdown_scheduler() -> None:
    if _scheduler:
        _scheduler.shutdown(wait=False)
