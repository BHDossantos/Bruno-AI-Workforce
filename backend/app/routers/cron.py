"""Token-protected cron triggers for external schedulers.

Lets Cloud Scheduler (GCP) or cron-job.org drive the daily agents, follow-ups,
and inbound sync without the in-process APScheduler — ideal for scale-to-zero
hosting. Every call must send header ``X-Cron-Token: <CRON_SECRET>``.
"""
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from .. import followups, inbound
from ..agents import AGENTS
from ..config import settings
from ..database import get_db

router = APIRouter(prefix="/cron", tags=["cron"])


def _auth(token: str | None) -> None:
    if not settings.cron_secret or token != settings.cron_secret:
        raise HTTPException(status_code=401, detail="Invalid or missing cron token")


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
    from .. import commanders
    return commanders.run_ceo(db)  # CEO → Commander → Agent hierarchy


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
