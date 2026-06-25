"""Content analytics — close the learning loop.

Pulls engagement for published Content-Factory pieces from the platforms,
stores it on each item, surfaces top performers, and computes which evergreen
categories perform best so the factory makes more of what lands. Guarded — it
no-ops for platforms without metric access.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from . import evergreen
from .integrations import facebook_api, instagram_api
from .models import ContentItem

log = logging.getLogger("bruno.content_analytics")


def _engagement(m: dict | None) -> int:
    if not m:
        return 0
    return int((m.get("likes") or 0) + 2 * (m.get("comments") or 0) + 3 * (m.get("shares") or 0))


def sync_metrics(db: Session) -> dict:
    """Refresh metrics for published pieces that carry a platform post id."""
    rows = (db.query(ContentItem).filter(ContentItem.status == "published").limit(200).all())
    updated = 0
    for it in rows:
        post_id = ((it.meta or {}).get("result") or {}).get("id")
        if not post_id:
            continue
        if it.channel == "instagram":
            m = instagram_api.get_media_insights(db, post_id)
        elif it.channel == "facebook":
            m = facebook_api.get_post_insights(db, post_id)
        else:
            m = None  # LinkedIn/X metrics need elevated API access — skip for now
        if m:
            it.meta = {**(it.meta or {}), "metrics": m, "engagement": _engagement(m)}
            updated += 1
    db.commit()
    return {"checked": len(rows), "updated": updated}


def top_performers(db: Session, limit: int = 10) -> list[dict]:
    rows = (db.query(ContentItem).filter(ContentItem.status == "published").limit(500).all())
    scored = [r for r in rows if (r.meta or {}).get("engagement") is not None]
    scored.sort(key=lambda r: (r.meta or {}).get("engagement", 0), reverse=True)
    return [{"topic": r.topic, "channel": r.channel, "business": r.business,
             "engagement": (r.meta or {}).get("engagement", 0),
             "metrics": (r.meta or {}).get("metrics")} for r in scored[:limit]]


def category_performance(db: Session) -> dict[str, float]:
    """Average engagement per evergreen category (topic → category mapping)."""
    topic_to_cat = {t: cat for cat, ideas in evergreen.CATEGORIES.items() for t in ideas}
    sums: dict[str, list[int]] = {}
    for r in db.query(ContentItem).filter(ContentItem.status == "published").limit(1000).all():
        eng = (r.meta or {}).get("engagement")
        cat = topic_to_cat.get(r.topic)
        if eng is not None and cat:
            sums.setdefault(cat, []).append(eng)
    return {c: round(sum(v) / len(v), 1) for c, v in sums.items() if v}


def best_topic(db: Session, business: str, seed: int) -> str:
    """Pick the next topic, biased toward the best-performing category for this
    business; falls back to the round-robin evergreen pick."""
    perf = category_performance(db)
    cats = evergreen.BUSINESS_CATEGORIES.get(business) or list(evergreen.CATEGORIES)
    ranked = [c for c in cats if c in perf]
    if ranked:
        best = max(ranked, key=lambda c: perf[c])
        ideas = evergreen.CATEGORIES.get(best) or []
        if ideas:
            return ideas[seed % len(ideas)]
    return evergreen.pick_topic(business, seed)
