"""Sales performance — the funnel + revenue view.

Answers "how is the business actually doing?": how leads move Leads → Contacted →
Engaged → Won, the conversion rate at each step, real revenue from closed clients
(annualized premium + commission), this-month vs goal, and the trend over the last
few months. Funnel comes from ``Lead.status``; revenue comes from ``Client`` (the
signed customers) — the two are joined by the origin lead.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from .config import settings
from .models import Client, Lead

_NEW = ("New", "Drafted")
_ENGAGED = ("Replied", "Interested", "Follow-up Needed")
_ACTIVE_CLIENT = ("Active", "Renewed")


def _pct(n: int, d: int) -> float:
    return round(100.0 * n / d, 1) if d else 0.0


def funnel(db: Session) -> dict:
    """Lead movement Leads → Contacted → Engaged → Won, with step conversion."""
    counts = {s: int(c) for s, c in
              db.query(Lead.status, func.count()).group_by(Lead.status).all()}
    total = sum(counts.values())
    new = sum(counts.get(s, 0) for s in _NEW)
    engaged = sum(counts.get(s, 0) for s in _ENGAGED)
    won = counts.get("Closed Won", 0)
    lost = counts.get("Closed Lost", 0)
    contacted = counts.get("Contacted", 0)
    # "Reached at least this stage" (cumulative), so the funnel only narrows.
    reached_contacted = total - new
    reached_engaged = engaged + won  # responded at some point
    decided = won + lost
    stages = [
        {"key": "leads", "label": "Leads", "count": total},
        {"key": "contacted", "label": "Contacted", "count": reached_contacted},
        {"key": "engaged", "label": "Engaged / quoting", "count": reached_engaged},
        {"key": "won", "label": "Closed won", "count": won},
    ]
    return {
        "stages": stages,
        "current": {"new": new, "contacted": contacted, "engaged": engaged,
                    "won": won, "lost": lost, "total": total},
        "rates": {
            "contact_rate": _pct(reached_contacted, total),
            "response_rate": _pct(reached_engaged, reached_contacted),
            "close_rate": _pct(won, decided),   # of decided deals
            "win_from_contacted": _pct(won, reached_contacted),
        },
    }


def _annual(premium_monthly) -> float:
    return round(float(premium_monthly or 0) * 12, 2)


def revenue(db: Session) -> dict:
    """Real revenue from signed clients: annualized premium, estimated commission,
    this-month new business, and goal vs. actual."""
    pct = float(getattr(settings, "sales_commission_pct", 12.0) or 0)
    goal = float(getattr(settings, "sales_monthly_revenue_goal", 0) or 0)
    clients = db.query(Client).filter(Client.status.in_(_ACTIVE_CLIENT)).all()
    book_annual = sum(_annual(c.premium_monthly) for c in clients)
    book_commission = round(book_annual * pct / 100, 2)

    month_start = date.today().replace(day=1)
    mtd = [c for c in clients if c.signed_at and c.signed_at >= month_start]
    mtd_annual = sum(_annual(c.premium_monthly) for c in mtd)
    mtd_commission = round(mtd_annual * pct / 100, 2)

    active = len(clients)
    return {
        "commission_pct": pct,
        "active_clients": active,
        "book_annual_premium": round(book_annual, 2),
        "book_commission": book_commission,
        "avg_annual_premium": round(book_annual / active, 2) if active else 0.0,
        "mtd_new_clients": len(mtd),
        "mtd_annual_premium": round(mtd_annual, 2),
        "mtd_commission": mtd_commission,
        "monthly_goal": goal,
        "goal_pct": _pct(int(mtd_commission), int(goal)) if goal else None,
        "goal_remaining": round(max(0.0, goal - mtd_commission), 2) if goal else None,
    }


def trend(db: Session, months: int = 6) -> list[dict]:
    """New business by month for the last N months — signed clients + the annualized
    premium and commission they added."""
    pct = float(getattr(settings, "sales_commission_pct", 12.0) or 0)
    today = date.today()
    # First day of the month, N-1 months back.
    y, m = today.year, today.month
    buckets: list[dict] = []
    keys: list[tuple[int, int]] = []
    for i in range(months - 1, -1, -1):
        mm = m - i
        yy = y
        while mm <= 0:
            mm += 12
            yy -= 1
        keys.append((yy, mm))
        buckets.append({"month": f"{yy}-{mm:02d}", "clients": 0, "annual_premium": 0.0,
                        "commission": 0.0})
    index = {k: b for k, b in zip(keys, buckets)}
    earliest = date(keys[0][0], keys[0][1], 1)
    for c in db.query(Client).filter(Client.signed_at.isnot(None),
                                     Client.signed_at >= earliest).all():
        k = (c.signed_at.year, c.signed_at.month)
        b = index.get(k)
        if not b:
            continue
        b["clients"] += 1
        b["annual_premium"] = round(b["annual_premium"] + _annual(c.premium_monthly), 2)
        b["commission"] = round(b["annual_premium"] * pct / 100, 2)
    return buckets


def report(db: Session) -> dict:
    """Everything the Performance page needs in one payload."""
    return {
        "funnel": funnel(db),
        "revenue": revenue(db),
        "trend": trend(db),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
