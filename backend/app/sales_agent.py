"""Sales Agent — the autonomous outbound seller.

One hands-free pass that works your leads the way a good SDR would: draft any
missing openers, then push each lead through an **email → text → call** cadence,
all of it already paced and compliance-gated by the underlying engines (daily
caps, texting hours, opt-out/DNC). It never spams a lead who replied or went hot —
those are pulled OUT of the machine and surfaced to you in the "needs you" queue.

This module ORCHESTRATES the existing engines rather than re-implementing them, so
there's one place that means "sell my book now" and one status that answers "what
did the agent do and who needs me?".
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from .models import Lead, Message

log = logging.getLogger("bruno.sales_agent")

# Leads that have engaged — pulled out of the outbound machine and handed to you.
NEEDS_YOU_STATUSES = ("Replied", "Interested", "Follow-up Needed")
# Still in the outbound cadence.
WORKING_STATUSES = ("New", "Drafted", "Contacted")
DONE_STATUSES = ("Closed Won", "Closed Lost")


def _day_start() -> datetime:
    return datetime.combine(date.today(), datetime.min.time(), tzinfo=timezone.utc)


def run(db: Session, *, autonomous: bool = True) -> dict:
    """Run one full outbound selling pass — email → text → call — reusing the
    existing engines (each self-paces and honors caps/hours/opt-out). Returns a
    per-channel tally of what actually went out. Safe to run on demand or on a
    schedule; idempotent within a lead's cadence (never double-sends a step)."""
    from . import auto_dial, everquote, outreach, sms_engine, sms_followups
    from .followups import process_due_followups

    result: dict = {"ran_at": datetime.now(timezone.utc).isoformat()}

    # 0) Make sure every in-market lead has an opener drafted (idempotent).
    try:
        result["drafted"] = everquote.personalize_batch(db)
    except Exception as exc:  # drafting must never break the pass
        result["drafted"] = {"error": str(exc)[:160]}

    # 1) EMAIL — send queued first-touch + sequence emails (ramp-aware daily cap).
    try:
        result["email"] = outreach.send_email_drafts(db, limit=50, account="insurance")
    except Exception as exc:
        result["email"] = {"error": str(exc)[:160]}

    # 2) TEXT — first-touch texts + the emailed-but-silent SMS follow-ups.
    try:
        result["text"] = sms_engine.send_sms_drafts(db, limit=25, account="insurance")
    except Exception as exc:
        result["text"] = {"error": str(exc)[:160]}
    try:
        result["text_followups"] = (sms_followups.run(db)
                                    if sms_followups.is_enabled() else {"skipped": "disabled"})
    except Exception as exc:
        result["text_followups"] = {"error": str(exc)[:160]}

    # 3) Sequence steps that are due (call tasks, nurture, breakup).
    try:
        result["followups"] = process_due_followups(db)
    except Exception as exc:
        result["followups"] = {"error": str(exc)[:160]}

    # 4) CALL — auto-dial the hottest, transfer live answers to you.
    try:
        result["calls"] = auto_dial.run(db)
    except Exception as exc:
        result["calls"] = {"error": str(exc)[:160]}

    log.info("sales_agent.run: %s", result)
    return result


def _touch_counts(db: Session, since: datetime) -> dict:
    rows = dict(db.query(Message.channel, func.count()).filter(
        Message.direction == "outbound", Message.sent_at >= since).group_by(Message.channel).all())
    return {"emails": int(rows.get("email", 0)), "texts": int(rows.get("sms", 0)),
            "calls": int(rows.get("call", 0))}


def needs_attention(db: Session, limit: int = 50) -> list[dict]:
    """Leads that engaged (replied / interested / follow-up needed) — pulled out of
    the outbound machine because they need a human, hottest first."""
    rows = (db.query(Lead).filter(Lead.status.in_(NEEDS_YOU_STATUSES))
            .order_by(Lead.score.desc(), Lead.last_contacted_at.desc()).limit(limit).all())
    out = []
    for l in rows:
        out.append({
            "id": str(l.id), "name": l.owner_name or l.company_name or l.email or "Lead",
            "email": l.email, "phone": l.phone, "status": l.status, "score": l.score or 0,
            "reason": l.reason,
            "last_contacted_at": l.last_contacted_at.isoformat() if l.last_contacted_at else None,
        })
    return out


def status(db: Session) -> dict:
    """What the Sales Agent is doing: whether it's live, today's touches by channel,
    the book split across the cadence, and how many need you."""
    from . import control

    counts = dict(db.query(Lead.status, func.count()).group_by(Lead.status).all())
    working = sum(int(counts.get(s, 0)) for s in WORKING_STATUSES)
    engaged = sum(int(counts.get(s, 0)) for s in NEEDS_YOU_STATUSES)
    won = int(counts.get("Closed Won", 0))
    lost = int(counts.get("Closed Lost", 0))

    paused = control.is_paused_safe(db)
    autopilot_on = control.get_mode(db) == "auto" or control.outreach_autopilot(db)
    return {
        "live": bool(autopilot_on and not paused),
        "paused": paused,
        "autopilot_on": autopilot_on,
        "today": _touch_counts(db, _day_start()),
        "pipeline": {"working": working, "needs_you": engaged, "won": won, "lost": lost},
        "needs_you_count": engaged,
    }
