"""AI CEO Dashboard — the whole business on one page.

Rolls the book of business + pipeline into the numbers an owner actually cares
about: annualized revenue (commission), policies in force, retention, average
first-response time, close rate, lead spend and ROI. Pure aggregation over data
the sales OS already tracks — no new tables, no AI key.
"""
from __future__ import annotations

import logging
import re

from sqlalchemy import func
from sqlalchemy.orm import Session

from . import insurance_commander as ic
from .config import settings
from .models import Client, Lead

log = logging.getLogger("bruno.ceo")


def _num(v) -> float:
    """Parse EverQuote's cost field (a string like '649') into dollars.
    EverQuote reports lead cost in cents, so 649 → $6.49."""
    d = re.sub(r"[^\d.]", "", str(v or ""))
    try:
        return float(d) / 100 if d else 0.0
    except ValueError:
        return 0.0


def dashboard(db: Session) -> dict:
    rate = float(settings.insurance_commission_rate or 0.12)

    clients = db.query(Client).filter(Client.business == "insurance").all()
    active = [c for c in clients if (c.status or "").lower() not in ("cancelled", "lapsed")]
    cancelled = [c for c in clients if (c.status or "").lower() == "cancelled"]

    annual_premium = sum(float(c.premium_monthly or 0) * 12 for c in active)
    commission = round(annual_premium * rate)
    policies = len(active)

    total_ever = len(active) + len(cancelled)
    retention = round(100 * len(active) / total_ever) if total_ever else None

    # Close rate: bound policies vs the insurance leads we actually worked.
    worked = int(db.query(func.count()).select_from(Lead).filter(
        Lead.segment.in_(ic.INSURANCE_SEGMENTS), Lead.times_contacted > 0).scalar() or 0)
    denom = worked + policies
    close_rate = round(100 * policies / denom) if denom else None

    speed = ic.speed(db)

    # Lead spend + ROI from EverQuote lead costs on file.
    spend = 0.0
    for (intake,) in db.query(Lead.intake).filter(Lead.segment.in_(ic.INSURANCE_SEGMENTS)).all():
        eq = (intake or {}).get("everquote") if isinstance(intake, dict) else None
        if eq:
            spend += _num(eq.get("cost"))
    spend = round(spend, 2)
    roi = round(commission / spend, 1) if spend > 0 else None

    return {
        "revenue_annualized": commission,      # agency commission = the revenue line
        "annual_premium": round(annual_premium),
        "policies_in_force": policies,
        "commission": commission,
        "retention_pct": retention,
        "avg_response_seconds": speed.get("avg_seconds"),
        "response_target_seconds": speed.get("target_seconds"),
        "close_rate_pct": close_rate,
        "lead_spend": spend,
        "roi": roi,
        "commission_rate": rate,
    }
