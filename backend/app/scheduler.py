"""APScheduler setup that runs each agent on its daily cron schedule."""
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


def _run_agent(key: str) -> None:
    cls = AGENTS[key]
    db = SessionLocal()
    try:
        log.info("Scheduled run: %s", key)
        cls(db).run()
    except Exception:  # pragma: no cover
        log.exception("Scheduled agent %s failed", key)
    finally:
        db.close()


def _sync_inbound() -> None:
    from .inbound import sync_replies

    db = SessionLocal()
    try:
        sync_replies(db)
    except Exception:  # pragma: no cover
        log.exception("Inbound sync failed")
    finally:
        db.close()


def start_scheduler() -> BackgroundScheduler | None:
    global _scheduler
    if not settings.enable_scheduler:
        log.info("Scheduler disabled (ENABLE_SCHEDULER=false)")
        return None
    _scheduler = BackgroundScheduler(timezone=settings.timezone)
    for key, cls in AGENTS.items():
        _scheduler.add_job(
            _run_agent, CronTrigger.from_crontab(cls.schedule_cron, timezone=settings.timezone),
            args=[key], id=key, replace_existing=True,
        )
        log.info("Scheduled %s at cron '%s'", key, cls.schedule_cron)
    # Poll both mailboxes for replies every 2 hours (no-op if Gmail unconfigured).
    _scheduler.add_job(_sync_inbound, IntervalTrigger(hours=2), id="inbound_sync", replace_existing=True)
    _scheduler.start()
    return _scheduler


def shutdown_scheduler() -> None:
    if _scheduler:
        _scheduler.shutdown(wait=False)
