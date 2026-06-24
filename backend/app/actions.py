"""Approve & Execute for Daily-Brief actions.

Each brief action has a deterministic key (e.g. 'follow_up:lead:<id>'). Executing
it performs the real work — send a follow-up email, mark a job applied — and
records state so it drops off the brief. This closes the loop:
AI prepares → you approve → AI executes → it reports back.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from . import memory, outreach
from .ai import client, skills
from .ai.prompts import FOLLOWUP_EMAIL
from .models import ActionState, Application, Job, Lead, Restaurant

log = logging.getLogger("bruno.actions")


def set_state(db: Session, key: str, status: str, result: dict | None = None) -> None:
    row = db.query(ActionState).filter(ActionState.key == key).first()
    if not row:
        row = ActionState(key=key)
        db.add(row)
    row.status = status
    row.result = result
    row.updated_at = datetime.now(timezone.utc)
    db.commit()


def dismiss(db: Session, key: str) -> dict:
    set_state(db, key, "dismissed")
    return {"ok": True, "key": key, "status": "dismissed"}


def _send_followup(db: Session, entity_type: str, row, account: str) -> dict:
    name = (getattr(row, "company_name", None) or getattr(row, "owner_name", None)
            or getattr(row, "name", None) or "there")
    context = (getattr(row, "reason", None) or getattr(row, "pain_points", None) or "our earlier note")
    sysp = skills.system_prompt("cold-email")
    mem_ctx = memory.context_block(db, name)
    if mem_ctx:
        sysp = f"{sysp}\n\n{mem_ctx}"
    art = client.complete_json(FOLLOWUP_EMAIL.format(step=1, name=name, context=context), system=sysp)
    art = art if isinstance(art, dict) else {}
    subject = art.get("subject") or f"Following up — {name}"
    msg = outreach.dispatch_email(db, entity_type=entity_type, entity_id=row.id,
                                  to_email=getattr(row, "email", None), subject=subject,
                                  body=art.get("body"), account=account, actor="brief")
    if row.status not in ("Closed Won", "Closed Lost"):
        row.status = "Follow-up Needed"
    db.commit()
    return {"ok": True, "status": msg.status,
            "message": f"Follow-up {msg.status.lower()} to {getattr(row, 'email', '')}"}


def execute(db: Session, key: str) -> dict:
    """Perform the action behind a brief key and record it as done."""
    try:
        if key.startswith("apply:"):
            job_id = key.split(":", 1)[1]
            app = db.query(Application).filter(Application.job_id == job_id).first()
            if not app:
                app = Application(job_id=job_id)
                db.add(app)
            app.status, app.applied_at = "Applied", datetime.now(timezone.utc)
            db.commit()
            job = db.query(Job).filter(Job.id == job_id).first()
            res = {"ok": True, "message": "Marked as applied", "link": job.url if job else None}

        elif key.startswith("follow_up:lead:"):
            lead = db.query(Lead).filter(Lead.id == key.split(":")[-1]).first()
            res = _send_followup(db, "lead", lead, "insurance") if lead else {"ok": False, "reason": "not found"}

        elif key.startswith("follow_up:restaurant:"):
            rest = db.query(Restaurant).filter(Restaurant.id == key.split(":")[-1]).first()
            res = _send_followup(db, "restaurant", rest, "personal") if rest else {"ok": False, "reason": "not found"}

        elif key.startswith("reply:"):
            # Replies need human nuance — open the thread; mark handled.
            res = {"ok": True, "message": "Open Texts to reply", "link": "/texts"}

        else:
            return {"ok": False, "reason": "unknown action"}

        if res.get("ok"):
            set_state(db, key, "done", res)
        return res
    except Exception as exc:  # never crash the brief
        log.exception("Action execute failed for %s", key)
        db.rollback()
        return {"ok": False, "reason": str(exc)}
