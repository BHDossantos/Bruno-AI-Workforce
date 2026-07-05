"""Ask-your-book Assistant — natural-language questions over the whole pipeline.

"Who needs follow-up today?", "hottest leads", "who's waiting on a quote?",
"who should I call today?", "who did we respond to too slowly?", "dead-ends to
revive", "new leads today", "what did we bind this week?". A rule-based intent
router (keyword match — works fully offline, no AI key) dispatches to the right
query and returns a short answer plus the matching leads, each with a one-line
reason and a suggested next action.

Ties together everything the sales OS already tracks (scoring, temperature,
stages, lifecycle flags, the return queue, the book of business).
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from . import lead_scoring, lead_temperature
from .insurance_commander import INSURANCE_SEGMENTS, _LOST, _WON, stage_for
from .models import ActionLog, Client, FollowUp, Lead

log = logging.getLogger("bruno.assistant")

_LIMIT = 15


def _row(lead: Lead, reason: str) -> dict:
    return {"lead_id": str(lead.id),
            "name": lead.company_name or lead.owner_name or lead.email or "Lead",
            "email": lead.email, "phone": lead.phone,
            "stage": stage_for(lead.status, lead.times_contacted or 0),
            "reason": reason}


def _open_insurance(db: Session):
    return db.query(Lead).filter(Lead.segment.in_(INSURANCE_SEGMENTS),
                                 func.lower(Lead.status).notin_(_WON | _LOST))


def _need_followup(db: Session) -> tuple[str, list[dict]]:
    today = date.today()
    ins_ids = {str(i) for (i,) in db.query(Lead.id).filter(
        Lead.segment.in_(INSURANCE_SEGMENTS)).all()}
    due_lead_ids = [fid for (etype, fid) in db.query(
        FollowUp.entity_type, FollowUp.entity_id).filter(
        FollowUp.entity_type == "lead", FollowUp.completed.is_(False),
        FollowUp.due_date <= today).all() if str(fid) in ins_ids]
    leads = db.query(Lead).filter(Lead.id.in_(due_lead_ids)).limit(_LIMIT).all() if due_lead_ids else []
    return (f"{len(due_lead_ids)} lead(s) have a follow-up due — here are the first {len(leads)}.",
            [_row(l, "Follow-up is due — reach out today.") for l in leads])


def _hottest(db: Session) -> tuple[str, list[dict]]:
    leads = _open_insurance(db).all()
    scored = sorted(leads, key=lambda l: lead_scoring.score_lead(l)["score"], reverse=True)[:_LIMIT]
    return (f"Your {len(scored)} highest-scoring open leads — call the top of this list first.",
            [_row(l, f"Score {lead_scoring.score_lead(l)['score']}/100 · {lead_temperature.classify(l.status)}")
             for l in scored])


def _waiting_on_quote(db: Session) -> tuple[str, list[dict]]:
    leads = [l for l in _open_insurance(db).all()
             if stage_for(l.status, l.times_contacted or 0) in ("Quote Sent", "Reached", "Needs Follow-up")][:_LIMIT]
    return (f"{len(leads)} engaged lead(s) waiting on a quote or a next step.",
            [_row(l, "Engaged — send or follow up on the quote.") for l in leads])


def _call_today(db: Session) -> tuple[str, list[dict]]:
    # Untouched brand-new leads first (speed wins), then the highest scorers.
    fresh = _open_insurance(db).filter(Lead.times_contacted == 0).limit(_LIMIT).all()
    rows = [_row(l, "Brand-new — respond fast (speed wins).") for l in fresh]
    if len(rows) < _LIMIT:
        _, hot = _hottest(db)
        seen = {r["lead_id"] for r in rows}
        for r in hot:
            if r["lead_id"] not in seen:
                rows.append(r)
            if len(rows) >= _LIMIT:
                break
    return (f"Your call list for today — {len(rows)} lead(s), newest-and-hottest first.", rows[:_LIMIT])


def _flagged_leads(db: Session, action: str, reason: str) -> tuple[str, list[dict]]:
    ids = {eid for (eid,) in db.query(ActionLog.entity_id).filter(
        ActionLog.action == action, ActionLog.entity == "lead").all() if eid}
    leads = db.query(Lead).filter(Lead.id.in_(ids)).limit(_LIMIT).all() if ids else []
    return (f"{len(ids)} lead(s) flagged.", [_row(l, reason) for l in leads])


def _revive(db: Session) -> tuple[str, list[dict]]:
    from . import lead_return
    q = lead_return.queue(db, limit=_LIMIT)
    return (f"{len(q)} dead-end(s) worth reviving with a fresh angle.",
            [{"lead_id": r["lead_id"], "name": r["name"], "email": r["email"], "phone": r["phone"],
              "stage": "Return", "reason": r["angle"]} for r in q])


def _new_today(db: Session) -> tuple[str, list[dict]]:
    start = datetime.combine(date.today(), datetime.min.time(), tzinfo=timezone.utc)
    leads = _open_insurance(db).filter(Lead.created_at >= start).limit(_LIMIT).all()
    return (f"{len(leads)} new lead(s) in today.",
            [_row(l, "New today — first touch under 60s wins.") for l in leads])


def _bound_week(db: Session) -> tuple[str, list[dict]]:
    since = date.today() - timedelta(days=7)
    rows = (db.query(Client).filter(Client.business == "insurance",
            Client.status != "Cancelled", Client.signed_at >= since)
            .order_by(Client.signed_at.desc()).limit(_LIMIT).all())
    return (f"{len(rows)} policy(ies) bound in the last 7 days.",
            [{"lead_id": str(c.id), "name": c.name, "email": c.email, "phone": c.phone,
              "stage": "Policy Bound",
              "reason": f"{c.line or 'policy'} · {c.carrier or 'carrier'} · "
                        f"${float(c.premium_monthly or 0):.0f}/mo"} for c in rows])


# Intent → (trigger keywords, handler). First best keyword match wins.
_INTENTS: list[tuple[str, list[str], object]] = [
    ("need_followup", ["follow up", "followup", "follow-up", "haven't followed", "chase", "overdue"], _need_followup),
    ("waiting_quote", ["quote", "waiting", "proposal", "pending"], _waiting_on_quote),
    ("call_today", ["call today", "who should i call", "call list", "who to call", "dial"], _call_today),
    ("speed_slow", ["slow", "too slow", "speed", "late", "responded late"], None),
    ("revive", ["revive", "dead", "dead-end", "return", "re-engage", "resurrect", "lost cause", "cold"], _revive),
    ("new_today", ["new lead", "new today", "just came in", "today's lead", "fresh"], _new_today),
    ("bound_week", ["bound", "closed", "won", "sold", "this week", "policies"], _bound_week),
    ("hottest", ["hot", "hottest", "best lead", "most likely", "buy", "top lead", "priority"], _hottest),
]


def _match(question: str) -> str:
    q = f" {(question or '').lower()} "
    best, best_score = "hottest", 0
    for key, triggers, _ in _INTENTS:
        s = sum(1 for kw in triggers if kw in q)
        if s > best_score:
            best, best_score = key, s
    return best if best_score > 0 else "help"


def ask(db: Session, question: str) -> dict:
    """Answer a natural-language question about the book of business."""
    intent = _match(question)
    if intent == "help":
        return {"ok": True, "intent": "help",
                "title": "Ask me about your book",
                "answer": "Try: “who needs follow-up today?”, “hottest leads”, “who's waiting "
                          "on a quote?”, “who should I call today?”, “who did we respond to too "
                          "slowly?”, “dead-ends to revive”, “new leads today”, “what did we bind "
                          "this week?”.",
                "leads": [], "count": 0}
    if intent == "speed_slow":
        answer, leads = _flagged_leads(db, "speed_breach", "First response was over the 60s goal — apologise and move fast.")
    else:
        handler = dict((k, h) for k, _, h in _INTENTS)[intent]
        answer, leads = handler(db)
    return {"ok": True, "intent": intent, "title": _TITLES.get(intent, "Results"),
            "answer": answer, "leads": leads, "count": len(leads)}


_TITLES: dict[str, str] = {
    "need_followup": "Follow-ups due", "waiting_quote": "Waiting on a quote",
    "call_today": "Call list for today", "speed_slow": "Responded too slowly",
    "revive": "Dead-ends to revive", "new_today": "New leads today",
    "bound_week": "Bound this week", "hottest": "Hottest leads",
}
