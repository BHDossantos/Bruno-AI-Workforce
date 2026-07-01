"""Today's money actions — the single "do these now to get clients" cockpit.

Ranks the highest-value things to do right now against the daily client goal:
close the hot leads, drain the send backlog, run the due follow-ups, and nudge
the interested-but-not-booked. Each action maps to a one-click endpoint that
already exists — this module only READS and prioritizes, it never sends.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func

from . import client_goal
from .insurance_lines import LABELS, line_for
from .lead_temperature import HOT, WARM, classify
from .models import FollowUp, Lead, Restaurant

# Expected deal value per business, for ranking actions by money on the table.
_VALUE = {"insurance": 1800, "consulting": 6000, "savorymind": 1200}
_PENDING = (None, "New", "Drafted")


def _lead_value(segment: str | None) -> int:
    if segment == "consulting":
        return _VALUE["consulting"]
    return _VALUE["insurance"]


def _hot_leads(db, limit: int = 25) -> list[dict]:
    """The individual warm/hot prospects worth acting on now, richest first."""
    out: list[dict] = []
    for lead in (db.query(Lead).filter(Lead.email.isnot(None)).all()):
        temp = classify(lead.status)
        if temp not in (HOT, WARM):
            continue
        biz = "BnB Global" if lead.segment == "consulting" else "Insurance"
        out.append({
            "id": str(lead.id), "entity_type": "lead",
            "name": lead.company_name or lead.owner_name or lead.email,
            "business": biz,
            "line": LABELS.get(line_for(lead.category, lead.segment, lead.industry)),
            "email": lead.email, "status": lead.status, "temperature": temp,
            "value": _lead_value(lead.segment),
        })
    for r in (db.query(Restaurant).filter(
            Restaurant.kind == "prospect", Restaurant.email.isnot(None)).all()):
        temp = classify(r.status)
        if temp not in (HOT, WARM):
            continue
        out.append({
            "id": str(r.id), "entity_type": "restaurant", "name": r.name or r.email,
            "business": "SavoryMind", "line": None, "email": r.email,
            "status": r.status, "temperature": temp, "value": _VALUE["savorymind"],
        })
    # Hot before warm, then by deal value.
    out.sort(key=lambda x: (0 if x["temperature"] == HOT else 1, -x["value"]))
    return out[:limit]


def actions(db) -> dict:
    today = date.today()
    cutoff = datetime.now(timezone.utc) - timedelta(days=2)

    def _count(model, *filters) -> int:
        return int(db.query(func.count()).select_from(model).filter(*filters).scalar() or 0)

    lead_backlog = _count(Lead, Lead.status.in_(_PENDING), Lead.email.isnot(None))
    rest_backlog = _count(Restaurant, Restaurant.kind == "prospect",
                          Restaurant.status.in_(_PENDING), Restaurant.email.isnot(None))
    backlog = lead_backlog + rest_backlog

    due_followups = _count(FollowUp, FollowUp.due_date <= today, FollowUp.completed.is_(False))

    not_booked = (_count(Lead, Lead.status == "Interested", Lead.email.isnot(None),
                         Lead.last_contacted_at.isnot(None), Lead.last_contacted_at <= cutoff)
                  + _count(Restaurant, Restaurant.kind == "prospect",
                           Restaurant.status == "Interested", Restaurant.email.isnot(None),
                           Restaurant.last_contacted_at.isnot(None),
                           Restaurant.last_contacted_at <= cutoff))

    # Renewals: active policies expiring within 30 days — retention revenue at risk.
    from .models import Client
    renewing = _count(
        Client, Client.expires_at.isnot(None), Client.expires_at >= today,
        Client.expires_at <= today + timedelta(days=30), Client.status != "Cancelled")

    hot = _hot_leads(db)
    hot_count = sum(1 for h in hot if h["temperature"] == HOT)

    cards = []
    if renewing:
        cards.append({
            "key": "renewals", "title": f"Review {renewing} policy renewal{'s' if renewing != 1 else ''} (≤30 days)",
            "why": "Existing clients renewing soon — reach out now to keep the book and re-quote.",
            "count": renewing, "value": 0,
            "cta": "Review renewals", "action": "link", "link": "/clients-crm?expiring=1",
        })
    if hot_count:
        cards.append({
            "key": "close_hot", "title": f"Close {hot_count} hot lead{'s' if hot_count != 1 else ''}",
            "why": "They signaled buying intent — reply and get them on the calendar today.",
            "count": hot_count, "value": sum(h["value"] for h in hot if h["temperature"] == HOT),
            "cta": "Review hot leads", "action": "link", "link": "/inbox",
        })
    if not_booked:
        cards.append({
            "key": "nudge_bookings", "title": f"Nudge {not_booked} interested → book a call",
            "why": "Interested but hasn't booked. One nudge with your calendar link.",
            "count": not_booked, "value": not_booked * _VALUE["insurance"],
            "cta": "Nudge bookings", "action": "nudge-bookings", "link": "/followups",
        })
    if due_followups:
        cards.append({
            "key": "followups", "title": f"Send {due_followups} due follow-up{'s' if due_followups != 1 else ''}",
            "why": "Scheduled touches that are due — persistence is where most replies come from.",
            "count": due_followups, "value": 0,
            "cta": "Send due now", "action": "run-followups", "link": "/followups",
        })
    if backlog:
        cards.append({
            "key": "send_backlog", "title": f"Send {backlog} queued outreach email{'s' if backlog != 1 else ''}",
            "why": "New prospects waiting — get them into the funnel (respects your daily cap).",
            "count": backlog, "value": 0,
            "cta": "Send all pending", "action": "send-now", "link": "/deliverability",
        })

    return {
        "goal": client_goal.status(db),
        "actions": cards,
        "hot_leads": hot,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
