"""Token-protected cron triggers for external schedulers.

Lets Cloud Scheduler (GCP) or cron-job.org drive the daily agents, follow-ups,
and inbound sync without the in-process APScheduler — ideal for scale-to-zero
hosting. Every call must send header ``X-Cron-Token: <CRON_SECRET>``.
"""
import logging

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from .. import followups, inbound
from ..agents import AGENTS
from ..config import settings
from ..database import get_db

router = APIRouter(prefix="/cron", tags=["cron"])
log = logging.getLogger("bruno.cron")


def _auth(token: str | None) -> None:
    if not settings.cron_secret or token != settings.cron_secret:
        raise HTTPException(status_code=401, detail="Invalid or missing cron token")


def _paused(db) -> bool:
    """True when the Emergency Stop is engaged — autonomous cron work should skip."""
    from .. import control
    return control.is_paused_safe(db)


def _safe(label: str, fn):
    """Run a cron worker; never let a top-level failure 500 — external schedulers
    retry on 5xx and would hot-loop. Log it and return a 200 with the error so the
    next scheduled tick runs cleanly."""
    try:
        return fn()
    except Exception as exc:  # pragma: no cover - defensive
        log.exception("cron %s failed", label)
        return {"ok": False, "error": str(exc)}


@router.post("/agent/{key}")
def run_agent(key: str, x_cron_token: str | None = Header(default=None),
              db: Session = Depends(get_db)):
    _auth(x_cron_token)
    cls = AGENTS.get(key)
    if not cls:
        raise HTTPException(status_code=404, detail=f"Unknown agent '{key}'")
    return {"agent": key, "result": cls(db).run()}


@router.post("/run-all")
def run_all(x_cron_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    _auth(x_cron_token)
    if _paused(db):
        return {"paused": True, "skipped": "run-all"}

    def _do():
        from .. import alerts, commanders
        result = commanders.run_ceo(db)  # CEO → Commander → Agent hierarchy
        alerts.check_run("daily cycle", result)  # email admin only if something errored
        return result
    return _safe("run-all", _do)


@router.post("/publish-content")
def cron_publish_content(x_cron_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    """Publish scheduled Content-Factory pieces that are due (to connected accounts)."""
    _auth(x_cron_token)
    from .. import content_factory
    return content_factory.publish_due(db)


@router.post("/selftest")
def cron_selftest(x_cron_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    """Full live health check across every service + connected channel — runnable
    from the shell with the cron token (mirrors the dashboard System Status page)."""
    _auth(x_cron_token)
    from .. import selftest
    return selftest.run(db)


@router.post("/platform-loops")
def cron_platform_loops(platform: str | None = None,
                        x_cron_token: str | None = Header(default=None),
                        db: Session = Depends(get_db)):
    """Run the per-platform content loops: top each platform up to its daily
    cadence with channel-optimized content. Pass ?platform=instagram to run one."""
    _auth(x_cron_token)
    if _paused(db):
        return {"paused": True, "skipped": "platform-loops"}
    from .. import platform_loops
    return platform_loops.run_all(db, [platform] if platform else None)


@router.post("/publish-blog")
def cron_publish_blog(x_cron_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    """Publish approved blog pieces to Medium (no-op if Medium isn't connected)."""
    _auth(x_cron_token)
    from .. import content_factory
    return content_factory.publish_blog_due(db)


@router.post("/sync-content-metrics")
def cron_sync_content_metrics(x_cron_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    """Refresh engagement metrics for published content (feeds the learning loop)."""
    _auth(x_cron_token)
    from .. import content_analytics
    return content_analytics.sync_metrics(db)


@router.post("/sync-video")
def cron_sync_video(x_cron_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    """Poll in-flight AI video jobs and attach finished clips (no-op without keys)."""
    _auth(x_cron_token)
    from .. import video_pipeline
    return video_pipeline.sync_pending(db)


@router.post("/sync-bank")
def cron_sync_bank(x_cron_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    """Pull bank balances + transactions from Plaid (no-op if no bank linked)."""
    _auth(x_cron_token)
    from ..integrations import plaid_api
    return plaid_api.sync(db)


@router.post("/refresh-tokens")
def cron_refresh_tokens(x_cron_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    """Auto-refresh OAuth tokens so social connections never silently expire."""
    _auth(x_cron_token)
    from ..integrations import oauth_refresh
    return oauth_refresh.refresh_all(db)


@router.post("/leads")
def cron_leads(x_cron_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    """Lead-gen + auto cold-email pass: the insurance, SavoryMind and BnB Global
    agents each find fresh prospects AND send their cold emails in one run.
    Schedule this a few times a day so you wake up to outreach already sent."""
    _auth(x_cron_token)
    if _paused(db):
        return {"paused": True, "skipped": "leads"}
    out = {}
    for key in ("insurance", "savorymind", "bnbglobal"):
        cls = AGENTS.get(key)
        if cls:
            try:
                out[key] = cls(db).run()
            except Exception as exc:  # one agent failing must not stop the other
                out[key] = {"error": str(exc)}
    from .. import alerts
    alerts.check_run("lead + cold-email pass", out)
    return out


@router.post("/newsletters")
def cron_newsletters(x_cron_token: str | None = Header(default=None),
                     db: Session = Depends(get_db)):
    """Send each funnel's newsletter to its warm subscribers (3x/week)."""
    _auth(x_cron_token)

    def _do():
        from .. import alerts, newsletters
        out = newsletters.run(db)
        alerts.check_run("newsletters", out)
        return out
    return _safe("newsletters", _do)


@router.post("/auto-outreach")
def cron_auto_outreach(x_cron_token: str | None = Header(default=None),
                       db: Session = Depends(get_db)):
    """Fully automatic outreach: email every pending lead + restaurant prospect +
    warm imported contacts, daily. Each send respects the mailbox daily cap +
    warmup, so a big backlog drains safely over a few days rather than all at once."""
    _auth(x_cron_token)

    def _do():
        from .. import alerts, bulk_outreach, contacts_outreach
        out = {
            "leads": bulk_outreach.dispatch_leads(db),
            "restaurants": bulk_outreach.dispatch_restaurants(db),
            "contacts": contacts_outreach.run(db),
        }
        alerts.check_run("auto outreach", out)
        return out
    return _safe("auto-outreach", _do)


@router.post("/contacts-insurance")
def cron_contacts_insurance(x_cron_token: str | None = Header(default=None),
                            db: Session = Depends(get_db)):
    """Warm insurance outreach to your imported personal contacts (email; SMS only
    if CONTACTS_SMS_ENABLED). Drips through the list in daily batches."""
    _auth(x_cron_token)
    from .. import alerts, contacts_outreach
    out = contacts_outreach.run(db)
    alerts.check_run("contacts insurance outreach", out)
    return out


@router.post("/referrals")
def cron_referrals(x_cron_token: str | None = Header(default=None),
                   db: Session = Depends(get_db)):
    """Ask engaged insurance leads (replied/interested/won) for referrals — your
    warmest source of new warm leads. One ask per lead."""
    _auth(x_cron_token)
    from .. import alerts, referrals
    out = referrals.run(db)
    alerts.check_run("referral requests", out)
    return out


@router.post("/board-report")
def cron_board_report(x_cron_token: str | None = Header(default=None),
                      db: Session = Depends(get_db)):
    """Weekly executive board review — build it and email it (no-op email without SMTP)."""
    _auth(x_cron_token)

    def _do():
        from .. import board_report
        from ..config import settings as cfg
        from ..integrations import mailer
        report = board_report.build(db)
        emailed = False
        if cfg.report_to_email:
            recs = "".join(
                f"<li><b>{r.get('action','')}</b> — {r.get('rationale','')} "
                f"<i>({r.get('confidence','')}%)</i></li>" for r in report.get("recommendations", []))
            html = (f"<h2>{report.get('headline','Weekly Board Report')}</h2>"
                    f"<p>Expected pipeline: ${report.get('expected_pipeline',0):,}</p>"
                    f"<h3>Recommendations</h3><ul>{recs}</ul>"
                    f"<p><b>Challenge:</b> {report.get('challenge','')}</p>")
            emailed = mailer.send_email(to=cfg.report_to_email,
                                        subject="Bruno AI — Weekly Board Report", html=html)
        return {"ok": True, "emailed": emailed,
                "recommendations": len(report.get("recommendations", []))}
    return _safe("board-report", _do)


@router.post("/music-releases")
def cron_music_releases(x_cron_token: str | None = Header(default=None),
                        db: Session = Depends(get_db)):
    """Release-as-eras cadence: auto-build the full content kit for any planned
    release whose date is within the next 4 weeks and has no kit yet."""
    _auth(x_cron_token)

    def _do():
        from .. import alerts, music_release
        out = music_release.run_due(db)
        alerts.check_run("music release kits", out)
        return out
    return _safe("music-releases", _do)


@router.post("/followups")
def cron_followups(x_cron_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    _auth(x_cron_token)
    return followups.process_due_followups(db)


@router.post("/inbound")
def cron_inbound(x_cron_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    _auth(x_cron_token)
    return inbound.sync_replies(db)


@router.post("/test-email")
def cron_test_email(to: str, account: str = "personal",
                    x_cron_token: str | None = Header(default=None)):
    """Send ONE test email so you can verify a mailbox sends + see the signature.

    Example: POST /cron/test-email?to=you@gmail.com&account=insurance
    """
    _auth(x_cron_token)
    from .. import email_template
    from ..integrations import gmail

    if not gmail.is_configured(account):
        return {"ok": False, "reason": f"'{account}' mailbox not configured "
                f"(set its app password / OAuth)"}
    html = email_template.render(
        "This is a test from your Bruno AI Workforce.<br><br>"
        "If you can read this and see the signature below, sending works — "
        "the autopilot is ready to send real outreach. \U0001F389",
        account,
    )
    mid = gmail.send_message(to, "Bruno AI — test email", html, account=account)
    return {"ok": bool(mid), "id": mid, "account": account, "to": to}
