"""Adaptive learning layer — the workforce gets smarter over time.

A lightweight online-learning core (a multi-armed bandit) that turns outcomes
into better decisions. Each decision has "arms" (e.g. content category × channel);
we track each arm's mean reward and how many times it's been tried, then pick the
next action with **UCB1** — mostly exploiting the best performer while exploring
under-sampled arms. Two properties matter:

- It **compounds**: more data → sharper choices.
- It **adapts to change**: new arms are tried first, and the exploration term
  keeps re-testing, so when the world shifts (new platform, new audience, new
  content) it re-learns instead of staying stuck on a stale winner.

Deterministic and interpretable — no training infra, and you can see exactly what
it has learned (see learnings()).
"""
from __future__ import annotations

import logging
import math

from sqlalchemy.orm import Session

from . import evergreen
from .models import ContentItem

log = logging.getLogger("bruno.learning")

_EXPLORE = 1.4  # UCB exploration weight (higher = explore more)


def pick(arms: dict[str, tuple[float, int]]) -> str | None:
    """Choose an arm. arms = {label: (mean_reward, trials)}. Untried arms are
    tried first; otherwise UCB1 over reward normalized to the best arm."""
    if not arms:
        return None
    untried = sorted(l for l, (_m, t) in arms.items() if t <= 0)
    if untried:
        return untried[0]  # always try a new/never-used option first
    max_mean = max((m for m, _t in arms.values()), default=0.0) or 1.0
    total = sum(t for _m, t in arms.values())
    best, best_score = None, float("-inf")
    for label, (mean, trials) in sorted(arms.items()):
        score = mean / max_mean + _EXPLORE * math.sqrt(math.log(total + 1) / trials)
        if score > best_score:
            best, best_score = label, score
    return best


def _topic_to_cat() -> dict[str, str]:
    return {t: cat for cat, ideas in evergreen.CATEGORIES.items() for t in ideas}


def content_arms(db: Session, channel: str,
                 categories: list[str] | None = None) -> dict[str, tuple[float, int]]:
    """Per-category (mean engagement, trials) for a channel — the bandit's arms.
    Restrict to ``categories`` (a business's set) or use all categories."""
    cats = categories or list(evergreen.CATEGORIES)
    t2c = _topic_to_cat()
    agg: dict[str, list[int]] = {c: [] for c in cats}
    rows = (db.query(ContentItem)
            .filter(ContentItem.status == "published", ContentItem.channel == channel)
            .limit(2000).all())
    for r in rows:
        cat = t2c.get(r.topic)
        eng = (r.meta or {}).get("engagement")
        if cat in agg and eng is not None:
            agg[cat].append(int(eng))
    return {c: ((sum(v) / len(v) if v else 0.0), len(v)) for c, v in agg.items()}


def pick_category(db: Session, channel: str, business: str) -> str | None:
    """Bandit-pick the next content category for a channel within a business."""
    cats = evergreen.BUSINESS_CATEGORIES.get(business) or list(evergreen.CATEGORIES)
    return pick(content_arms(db, channel, cats))


def learnings(db: Session) -> dict:
    """What the system has learned so far — per-channel category performance
    (with sample sizes) + the bandit's next pick + best posting hours."""
    from . import posting_times
    channels = ["instagram", "facebook", "linkedin", "tiktok", "x"]
    content = []
    for ch in channels:
        arms = content_arms(db, ch)
        ranked = sorted(((c, m, t) for c, (m, t) in arms.items() if t > 0),
                        key=lambda x: x[1], reverse=True)
        content.append({
            "channel": ch,
            "samples": sum(t for _c, _m, t in [(c, m, t) for c, (m, t) in arms.items()]),
            "next_pick": pick(arms),
            "arms": [{"category": c, "avg_engagement": round(m, 1), "samples": t}
                     for c, m, t in ranked[:6]],
        })
    return {
        "method": "UCB1 multi-armed bandit — exploits winners, keeps exploring so it adapts to change",
        "content": content,
        "posting_times": posting_times.summary(db),
    }
