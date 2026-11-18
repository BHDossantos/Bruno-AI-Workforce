"""Workforce map — the whole AI team on one page.

A single read that powers the cockpit view: every agent grouped into departments
around the center, what each department does, whether it's running right now,
today's numbers, the human-approval gate ("nothing goes out without your yes"),
the shared knowledge every agent reads, and a live activity log.

Read-only aggregation over existing state (scheduler plan, control mode, the
message log, the action log) — no new tables, no writes.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ActionLog, Message
from ..security import require_role

router = APIRouter(prefix="/workforce", tags=["workforce"])
_read = require_role("admin", "operator", "viewer")


# Departments — a meaningful grouping of the real agents/jobs, insurance-first. Each
# names the workers it covers; `active` is computed live from the actual switches so
# the map reflects what's truly running (e.g. Calls follows the Phone-calls toggle).
_DEPARTMENTS = [
    {"key": "leads", "name": "Leads", "icon": "🎯", "tagline": "finds & qualifies prospects",
     "agents": ["EverQuote intake", "Commercial finder", "Home finder", "Auto finder",
                "Lead scorer", "CSV import"]},
    {"key": "email", "name": "Email", "icon": "📧", "tagline": "writes & sends cold email",
     "agents": ["Cold-email writer", "Draft sender", "Deliverability watchdog", "Reply syncer"]},
    {"key": "texting", "name": "Texting", "icon": "💬", "tagline": "SMS openers & follow-ups",
     "agents": ["SMS opener", "Non-replier follow-up", "EverQuote cadence", "Opt-out guard"]},
    {"key": "calls", "name": "Calls", "icon": "📞", "tagline": "auto-dials & transfers to you",
     "agents": ["Auto-dialer", "Voicemail drop", "Live-answer transfer", "Call logger"]},
    {"key": "conversation", "name": "Conversation", "icon": "🗣️", "tagline": "nurtures & books",
     "agents": ["Follow-up cadence", "Booking nudger", "Conversation engine", "Renewal pipeline"]},
    {"key": "content", "name": "Content", "icon": "✍️", "tagline": "newsletters & social",
     "agents": ["Content factory", "Newsletter writer", "Social loops", "LinkedIn founder"]},
]

# Shared knowledge every agent reads before it acts.
_KNOWLEDGE = [
    "Your email signature & from-addresses",
    "Brand names per business",
    "Sales scripts & templates (incl. the trucking playbook)",
    "Compliance rails — opt-out, legal hours, daily caps",
    "Business & connection registry",
]


def _active(db: Session) -> dict:
    """Which departments are running right now, from the live switches."""
    from .. import auto_dial, businesses, control
    paused = control.is_paused_safe(db)
    autop = control.outreach_autopilot(db) or control.get_mode(db) == "auto"
    outreach_on = autop and not paused
    content_on = businesses.is_on("content") and not paused
    return {
        "leads": not paused,
        "email": outreach_on,
        "texting": outreach_on,
        "calls": outreach_on and auto_dial.auto_dial_enabled(),
        "conversation": not paused,
        "content": content_on,
    }


def _counts(db: Session) -> tuple[dict, dict, int, int]:
    now = datetime.now(timezone.utc)
    today = datetime.combine(now.date(), datetime.min.time(), tzinfo=timezone.utc)
    week = today - timedelta(days=6)

    def sent(channel: str, since: datetime) -> int:
        return db.query(func.count()).select_from(Message).filter(
            Message.channel == channel, Message.direction == "outbound",
            Message.sent_at.isnot(None), Message.sent_at >= since).scalar() or 0

    def replies(since: datetime) -> int:
        return db.query(func.count()).select_from(Message).filter(
            Message.direction == "inbound", Message.created_at >= since).scalar() or 0

    today_n = {"email": sent("email", today), "sms": sent("sms", today),
               "call": sent("call", today), "replies": replies(today)}
    week_n = {"email": sent("email", week), "sms": sent("sms", week),
              "call": sent("call", week), "replies": replies(week)}
    drafted = db.query(func.count()).select_from(Message).filter(
        Message.direction == "outbound", Message.status == "Drafted").scalar() or 0
    actions = db.query(func.count()).select_from(Message).filter(
        Message.direction == "inbound",
        func.lower(func.coalesce(Message.status, "")).in_(("interested", "follow-up needed")),
        Message.created_at >= today - timedelta(days=30)).scalar() or 0
    return today_n, week_n, int(drafted), int(actions)


def _activity(db: Session, limit: int = 12) -> list[dict]:
    rows = (db.query(ActionLog).order_by(ActionLog.created_at.desc()).limit(limit).all())
    out = []
    for r in rows:
        when = getattr(r, "created_at", None)
        out.append({
            "time": when.strftime("%H:%M") if when else "",
            "actor": (r.actor or "agent"),
            "action": r.action,
            "detail": (r.entity or "") + ((" " + str(r.entity_id)) if r.entity_id else ""),
        })
    return out


@router.get("/map")
def workforce_map(db: Session = Depends(get_db), _=Depends(_read)):
    """Everything the AI workforce is and is doing, on one page."""
    from .. import auto_dial, control
    active = _active(db)
    today_n, week_n, drafted, actions = _counts(db)
    departments = [
        {**d, "count": len(d["agents"]), "active": active.get(d["key"], True)}
        for d in _DEPARTMENTS
    ]
    mode = control.get_mode(db)
    return {
        "departments": departments,
        "total_agents": sum(len(d["agents"]) for d in _DEPARTMENTS),
        "knowledge": _KNOWLEDGE,
        "today": today_n,
        "week": week_n,
        "waits_for_you": {
            "mode": mode,                                  # manual | semi | auto
            "autopilot": control.outreach_autopilot(db),
            "paused": control.is_paused_safe(db),
            "calls_on": auto_dial.auto_dial_enabled(),
            "pending_drafts": drafted,                     # waiting for your "send"
            "open_actions": actions,                       # replies needing a human
            "approve_from_phone": mode != "auto",          # nothing sends without your yes
        },
        "activity": _activity(db),
    }
