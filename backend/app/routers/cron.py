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
    out: dict = {}
    for key, cls in AGENTS.items():
        try:
            out[key] = cls(db).run()
        except Exception as exc:  # pragma: no cover
            out[key] = {"error": str(exc)}
    return out


@router.post("/followups")
def cron_followups(x_cron_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    _auth(x_cron_token)
    return followups.process_due_followups(db)


@router.post("/inbound")
def cron_inbound(x_cron_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    _auth(x_cron_token)
    return inbound.sync_replies(db)
