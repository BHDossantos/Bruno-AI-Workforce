"""AI Daily Mission — the one morning card that says 'here's today's job'.

Rolls the pipeline into the exact categories a producer works each morning:
today's leads, the priority ones, who needs a quote, who needs a call, renewals
due, referral opportunities, and the expected revenue if today's board is
worked. Pure aggregation over data the sales OS already tracks — no AI key.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from . import insurance_commander as ic, lead_scoring
from .config import settings
from .models import Client, FollowUp, Lead

log = logging.getLogger("bruno.mission")

_ASSUMED_ANNUAL_PREMIUM = 1500.0


def _commission_per_policy() -> float:
    return round(_ASSUMED_ANNUAL_PREMIUM * float(settings.insurance_commission_rate or 0.12))


def build(db: Session) -> dict:
    start = datetime.combine(date.today(), datetime.min.time(), tzinfo=timezone.utc)
    today = date.today()

    open_leads = (db.query(Lead).filter(
        Lead.segment.in_(ic.INSURANCE_SEGMENTS),
        func.lower(Lead.status).notin_(ic._WON | ic._LOST)).all())

    leads_today = int(db.query(func.count()).select_from(Lead).filter(
        Lead.segment.in_(ic.INSURANCE_SEGMENTS), Lead.created_at >= start).scalar() or 0)

    priority = need_quotes = need_calls = 0
    for l in open_leads:
        stage = ic.stage_for(l.status, l.times_contacted or 0)
        score = lead_scoring.score_lead(l)["score"]
        if score >= 70:
            priority += 1
        if stage in ("Reached", "Needs Follow-up"):
            need_quotes += 1
        if (l.times_contacted or 0) == 0:
            need_calls += 1

    # Follow-ups due today add to the call/touch list.
    ins_ids = {str(l.id) for l in open_leads}
    due_followups = sum(1 for (etype, fid) in db.query(
        FollowUp.entity_type, FollowUp.entity_id).filter(
        FollowUp.entity_type == "lead", FollowUp.completed.is_(False),
        FollowUp.due_date <= today).all() if str(fid) in ins_ids)
    need_calls += due_followups

    # Renewals due in the next 30 days.
    soon = today + timedelta(days=30)
    need_renewal = int(db.query(func.count()).select_from(Client).filter(
        Client.business == "insurance", Client.status != "Cancelled",
        Client.expires_at.isnot(None), Client.expires_at <= soon,
        Client.expires_at >= today).scalar() or 0)

    # Referral opportunities: active clients on the book to ask.
    need_referral = int(db.query(func.count()).select_from(Client).filter(
        Client.business == "insurance",
        func.lower(Client.status).in_(["active", "renewed"])).scalar() or 0)

    # Quotes already sent that could bind today = the clearest expected revenue.
    quotes_sent = sum(1 for l in open_leads
                      if ic.stage_for(l.status, l.times_contacted or 0) == "Quote Sent")
    expected_revenue = round(quotes_sent * _commission_per_policy()
                             + priority * 0.2 * _commission_per_policy())

    return {
        "date": today.isoformat(),
        "leads_today": leads_today,
        "priority": priority,
        "need_quotes": need_quotes,
        "need_calls": need_calls,
        "need_renewal": need_renewal,
        "need_referral": need_referral,
        "expected_revenue": expected_revenue,
        "headline": (f"Today's mission: {need_calls} to call, {need_quotes} to quote, "
                     f"{need_renewal} renewal(s) — ~${expected_revenue:,} in reach."),
    }
