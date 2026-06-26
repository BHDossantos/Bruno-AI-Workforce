"""Lead-category learn-and-act — learn which prospect categories actually earn
replies and bias future sourcing/outreach toward the winners.

Same attribution model as outreach_analytics: an outbound email to a lead
"replied" if that lead's entity later produced an inbound message. We aggregate
reply rate by the lead's category (Contractor, Restaurant, CPA, …) so the agents
can spend their effort on the categories that convert instead of treating every
category the same. ``category_boosts`` returns a fit-score bonus per winning
category; ``whats_working`` returns a prompt hint for the outreach copy.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from .models import Lead, Message

_MIN_SAMPLE = 6   # need this many sends in a category before trusting its rate
_BOOST = 15       # fit-score bonus applied to a proven-converting category


def category_reply_rates(db: Session) -> dict[str, dict]:
    """Per-category {sent, replied, rate} across all leads emailed so far."""
    cat_by_lead = {lid: (cat or "Uncategorized")
                   for (lid, cat) in db.query(Lead.id, Lead.category).all()}
    replied = {e for (e,) in db.query(Message.entity_id).filter(
        Message.direction == "inbound", Message.entity_id.isnot(None)).all()}
    sent = (db.query(Message.entity_id).filter(
        Message.entity_type == "lead", Message.direction == "outbound",
        Message.status == "Sent", Message.entity_id.isnot(None)).all())
    agg: dict[str, dict] = {}
    for (eid,) in sent:
        cat = cat_by_lead.get(eid)
        if not cat:
            continue
        a = agg.setdefault(cat, {"sent": 0, "replied": 0})
        a["sent"] += 1
        if eid in replied:
            a["replied"] += 1
    for a in agg.values():
        a["rate"] = round(a["replied"] / a["sent"], 3) if a["sent"] else 0.0
    return agg


def winning_categories(db: Session, top_n: int = 3) -> list[tuple[str, dict]]:
    """Categories ranked by reply rate, among those with enough data and a reply."""
    try:
        rates = category_reply_rates(db)
    except Exception:  # pragma: no cover - best-effort learning
        return []
    ranked = sorted(
        [(c, a) for c, a in rates.items() if a["sent"] >= _MIN_SAMPLE and a["rate"] > 0],
        key=lambda x: x[1]["rate"], reverse=True)
    return ranked[:top_n]


def category_boosts(db: Session, top_n: int = 3) -> dict[str, int]:
    """{category: fit bonus} for the proven-converting categories — agents add this
    when ranking a sourced batch so winning categories get worked first."""
    return {c: _BOOST for c, _ in winning_categories(db, top_n)}


def whats_working(db: Session, top_n: int = 2) -> str:
    """Prompt hint naming the best-converting prospect categories."""
    ranked = winning_categories(db, top_n)
    if not ranked:
        return ""
    winners = [f"{c} ({int(a['rate'] * 100)}% reply)" for c, a in ranked]
    return ("WHAT'S CONVERTING — these prospect categories reply most; lead with "
            "outcomes relevant to them: " + "; ".join(winners) + ".")
