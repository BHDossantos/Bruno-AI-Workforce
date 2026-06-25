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


def category_performance(db: Session, channel: str | None = None) -> dict[str, float]:
    """Average engagement per evergreen category (topic → category mapping).

    Pass ``channel`` to scope to a single platform — what lands on Instagram is
    not what lands on LinkedIn, so each platform loop optimizes on its own data."""
    topic_to_cat = {t: cat for cat, ideas in evergreen.CATEGORIES.items() for t in ideas}
    q = db.query(ContentItem).filter(ContentItem.status == "published")
    if channel:
        q = q.filter(ContentItem.channel == channel)
    sums: dict[str, list[int]] = {}
    for r in q.limit(1000).all():
        eng = (r.meta or {}).get("engagement")
        cat = topic_to_cat.get(r.topic)
        if eng is not None and cat:
            sums.setdefault(cat, []).append(eng)
    return {c: round(sum(v) / len(v), 1) for c, v in sums.items() if v}


def _best_from_categories(perf: dict[str, float], business: str, seed: int) -> str:
    """Pick a topic from the best-performing category among a business's categories;
    fall back to the round-robin evergreen pick when there's no signal yet."""
    cats = evergreen.BUSINESS_CATEGORIES.get(business) or list(evergreen.CATEGORIES)
    ranked = [c for c in cats if c in perf]
    if ranked:
        best = max(ranked, key=lambda c: perf[c])
        ideas = evergreen.CATEGORIES.get(best) or []
        if ideas:
            return ideas[seed % len(ideas)]
    return evergreen.pick_topic(business, seed)


def best_topic(db: Session, business: str, seed: int) -> str:
    """Pick the next topic, biased toward the best-performing category for this
    business (across all channels); falls back to the round-robin evergreen pick."""
    return _best_from_categories(category_performance(db), business, seed)


def best_topic_for_channel(db: Session, channel: str, business: str, seed: int) -> str:
    """Channel-aware topic pick: bias to the category that performs best on THIS
    platform, then fall back to the cross-channel pick, then round-robin."""
    perf = category_performance(db, channel) or category_performance(db)
    return _best_from_categories(perf, business, seed)


def channel_summary(db: Session) -> dict[str, dict]:
    """Per-channel performance rollup for the growth dashboard: how many pieces
    we've published, average engagement, and the top-performing category."""
    topic_to_cat = {t: cat for cat, ideas in evergreen.CATEGORIES.items() for t in ideas}
    rows = db.query(ContentItem).filter(ContentItem.status == "published").limit(2000).all()
    by_ch: dict[str, dict] = {}
    cat_eng: dict[str, dict[str, list[int]]] = {}
    for r in rows:
        ch = r.channel
        d = by_ch.setdefault(ch, {"published": 0, "engagements": []})
        d["published"] += 1
        eng = (r.meta or {}).get("engagement")
        if eng is not None:
            d["engagements"].append(int(eng))
            cat = topic_to_cat.get(r.topic)
            if cat:
                cat_eng.setdefault(ch, {}).setdefault(cat, []).append(int(eng))
    out: dict[str, dict] = {}
    for ch, d in by_ch.items():
        engs = d["engagements"]
        cats = {c: round(sum(v) / len(v), 1) for c, v in cat_eng.get(ch, {}).items() if v}
        out[ch] = {
            "published": d["published"],
            "avg_engagement": round(sum(engs) / len(engs), 1) if engs else 0.0,
            "total_engagement": sum(engs),
            "top_category": max(cats, key=cats.get) if cats else None,
        }
    return out
