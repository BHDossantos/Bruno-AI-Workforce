"""Bulk / automatic outreach dispatch.

Sends the cold email/pitch to every pending lead and restaurant prospect. Used by
the manual "Send all pending" buttons AND the daily auto-outreach cron, so leads
never sit in Drafted. Every send goes through outreach.dispatch_email, which
enforces the daily send cap + mailbox warmup + real-email guard — so even
"send everything" is safely paced and won't get the Gmail account flagged.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from . import outreach
from .models import Lead, Restaurant

_PENDING = (None, "New", "Drafted")


def dispatch_leads(db: Session, segment: str | None = None, limit: int = 1000,
                   autonomous: bool = True) -> dict:
    q = db.query(Lead).filter(Lead.status.in_(_PENDING), Lead.email.isnot(None))
    if segment:
        q = q.filter(Lead.segment == segment)
    rows = q.order_by(Lead.score.desc()).limit(limit).all()
    sent = failed = retired = 0
    for lead in rows:
        # Retire un-sendable (synthetic/placeholder) addresses so they stop sitting
        # in the queue forever and inflating the backlog.
        if not outreach.is_real_email(lead.email):
            lead.status = "Skipped"
            retired += 1
            continue
        account = "insurance" if lead.segment in ("commercial", "personal") else "personal"
        subject = f"A quick idea for {lead.company_name or lead.owner_name}"
        try:
            msg = outreach.dispatch_email(db, entity_type="lead", entity_id=lead.id,
                                          to_email=lead.email, subject=subject,
                                          body=lead.cold_email, account=account, actor="bulk",
                                          autonomous=autonomous)
            if msg.status in ("Sent", "Drafted"):
                if msg.status == "Sent" and lead.status in (None, "New", "Drafted"):
                    lead.status = "Sent"
                sent += 1
            else:
                failed += 1
        except Exception:
            failed += 1
    db.commit()
    return {"pending": len(rows), "dispatched": sent, "failed": failed, "retired": retired}


def dispatch_restaurants(db: Session, limit: int = 1000, autonomous: bool = True) -> dict:
    rows = (db.query(Restaurant).filter(
        Restaurant.kind == "prospect", Restaurant.status.in_(_PENDING),
        Restaurant.email.isnot(None)).limit(limit).all())
    sent = failed = retired = 0
    for r in rows:
        if not outreach.is_real_email(r.email):
            r.status = "Skipped"  # retire un-sendable synthetic/placeholder rows
            retired += 1
            continue
        subject = f"Growing revenue at {r.name} with SavoryMind"
        try:
            msg = outreach.dispatch_email(db, entity_type="restaurant", entity_id=r.id,
                                          to_email=r.email, subject=subject,
                                          body=r.pitch_email, account="personal", actor="bulk",
                                          autonomous=autonomous)
            if msg.status in ("Sent", "Drafted"):
                if msg.status == "Sent" and r.status in (None, "New", "Drafted"):
                    r.status = "Sent"
                sent += 1
            else:
                failed += 1
        except Exception:
            failed += 1
    db.commit()
    return {"pending": len(rows), "dispatched": sent, "failed": failed, "retired": retired}
