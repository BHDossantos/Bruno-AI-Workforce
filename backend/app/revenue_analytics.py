"""Revenue & ROI analytics — the money view, not vanity metrics.

Per business: leads, contacted, replied, won, revenue won, weighted pipeline
value, reply/win rates, and (when a spend figure is given) cost-per-lead,
cost-per-meeting and ROI. Built from the same lead/restaurant data the rest of
the app uses, so it's always consistent with the pipeline.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from .lead_temperature import HOT, WARM, classify
from .models import Client, Lead, Restaurant

# Expected deal value per business line (commission / contract) — used to
# ESTIMATE revenue from lead status before a real client record exists.
_VALUE = {"insurance": 1800, "consulting": 6000, "savorymind": 1200}
_WON = {"won", "closed won", "client", "customer", "signed"}
# Probability of a still-open lead closing, by temperature (for pipeline value).
_PROB = {HOT: 0.5, WARM: 0.2, "cold": 0.03, "dead": 0.0}

# Report business label -> Client Book business key, so the CRM's real premium
# rolls into the money view under the same business bucket.
_BOOK_KEY = {"Insurance": "insurance", "BnB Global": "bnb", "SavoryMind": "savorymind"}


def actual_annual_revenue(db: Session) -> dict[str, float]:
    """REAL annualized revenue per Client Book business — monthly premium × 12
    for every non-cancelled client. This is actual booked revenue, not an
    estimate, so it's reported alongside (never blended into) the lead-based
    estimate below."""
    rows = db.query(Client.business, Client.premium_monthly).filter(
        Client.status != "Cancelled").all()
    out: dict[str, float] = {}
    for business, premium in rows:
        if premium is None:
            continue
        key = business or "insurance"
        out[key] = out.get(key, 0.0) + float(premium) * 12
    return {k: round(v, 2) for k, v in out.items()}


def _won(status: str | None) -> bool:
    return (status or "").strip().lower() in _WON


def _line(rows: list, value: int) -> dict:
    leads = len(rows)
    contacted = replied = won = 0
    pipeline = 0.0
    for status in rows:
        temp = classify(status)
        if _won(status):
            won += 1
            continue
        if temp in (HOT, WARM):
            replied += 1
        if status not in (None, "New"):
            contacted += 1
        pipeline += value * _PROB.get(temp, 0.03)
    revenue = won * value
    return {
        "leads": leads, "contacted": contacted, "replied": replied, "won": won,
        "revenue_won": int(revenue), "pipeline_value": int(pipeline),
        "reply_rate": round(replied / contacted, 3) if contacted else 0.0,
        "win_rate": round(won / contacted, 3) if contacted else 0.0,
    }


def by_line(db: Session) -> dict:
    """Insurance conversion broken out by line of business — Home / Auto / Life /
    Commercial — so you can see which line actually converts and where to focus.
    Direct prospects and the referral partners that feed each line are both
    classified into their line (partners rarely reach a 'won' status, so revenue
    stays clean)."""
    from .insurance_lines import LABELS, LINES, line_for
    rows = db.query(Lead.status, Lead.category, Lead.segment, Lead.industry).filter(
        Lead.segment.in_(["commercial", "personal", "referral_partner"])).all()
    buckets: dict[str, list] = {ln: [] for ln in LINES}
    for status, category, segment, industry in rows:
        buckets[line_for(category, segment, industry)].append(status)
    lines = {LABELS[ln]: _line(buckets[ln], _VALUE["insurance"]) for ln in LINES}
    totals = {k: sum(v[k] for v in lines.values())
              for k in ("leads", "contacted", "replied", "won", "revenue_won", "pipeline_value")}
    return {"lines": lines, "totals": totals}


def report(db: Session, cost: float | None = None) -> dict:
    ins_rows = [s for (s,) in db.query(Lead.status).filter(Lead.segment.in_(["commercial", "personal"])).all()]
    con_rows = [s for (s,) in db.query(Lead.status).filter(Lead.segment == "consulting").all()]
    sav_rows = [s for (s,) in db.query(Restaurant.status).filter(Restaurant.kind == "prospect").all()]

    businesses = {
        "Insurance": _line(ins_rows, _VALUE["insurance"]),
        "BnB Global": _line(con_rows, _VALUE["consulting"]),
        "SavoryMind": _line(sav_rows, _VALUE["savorymind"]),
    }
    # Roll the Client Book's REAL premium in as actual_annual_revenue, alongside
    # (not replacing) the lead-based revenue_won estimate — so the money view
    # shows both what's estimated from the pipeline and what's actually booked.
    real = actual_annual_revenue(db)
    for label, book_key in _BOOK_KEY.items():
        businesses[label]["actual_annual_revenue"] = real.get(book_key, 0.0)
    totals = {k: sum(b[k] for b in businesses.values())
              for k in ("leads", "contacted", "replied", "won", "revenue_won", "pipeline_value")}
    totals["actual_annual_revenue"] = round(sum(real.values()), 2)

    # Cost/ROI only when a spend figure is supplied (we don't fabricate costs).
    cost_metrics = None
    if cost and cost > 0:
        cost_metrics = {
            "spend": round(cost, 2),
            "cost_per_lead": round(cost / totals["leads"], 2) if totals["leads"] else None,
            "cost_per_won": round(cost / totals["won"], 2) if totals["won"] else None,
            "roi": round((totals["revenue_won"] - cost) / cost, 2) if cost else None,
        }

    return {"businesses": businesses, "totals": totals, "cost_metrics": cost_metrics}
