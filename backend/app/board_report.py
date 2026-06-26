"""Weekly Board Report — the Sunday executive review that recommends and challenges.

Unlike the daily brief (what to do today) or the daily report (what happened
today), this looks at the WEEK: it compares this 7-day window to the prior one,
spots the trends, and asks the model to act like a board member — decide where to
focus, what to pause, and push back — every call tied to the numbers and the
objective priorities. Degrades to rule-based recommendations when offline.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from . import objectives, scoring
from .ai import client
from .ai.prompts import BOARD_REPORT
from .models import (Application, ContentItem, Job, Lead, Message, Opportunity,
                     Restaurant, SocialSnapshot)


def _window(db: Session, start: datetime, end: datetime) -> dict:
    def c(model, col, *extra) -> int:
        return int(db.query(func.count()).select_from(model)
                   .filter(col >= start, col < end, *extra).scalar() or 0)
    return {
        "emails_sent": c(Message, Message.created_at, Message.channel == "email",
                         Message.direction == "outbound"),
        "replies": c(Message, Message.created_at, Message.direction == "inbound"),
        "leads_sourced": c(Lead, Lead.created_at),
        "restaurants_sourced": c(Restaurant, Restaurant.created_at,
                                 Restaurant.kind == "prospect"),
        "content_published": c(ContentItem, ContentItem.published_at),
        "jobs_sourced": c(Job, Job.found_at),
        "applications": c(Application, Application.applied_at),
        "opportunities_added": c(Opportunity, Opportunity.created_at),
    }


def _trend(this_v: int, last_v: int) -> dict:
    if last_v == 0:
        pct = 100.0 if this_v else 0.0
    else:
        pct = round((this_v - last_v) / last_v * 100, 1)
    return {"this_week": this_v, "last_week": last_v, "delta_pct": pct,
            "trend": "up" if this_v > last_v else "down" if this_v < last_v else "flat"}


_LABELS = {
    "emails_sent": "Outreach emails", "replies": "Replies received",
    "leads_sourced": "Leads sourced", "restaurants_sourced": "Restaurant prospects",
    "content_published": "Posts published", "jobs_sourced": "Jobs sourced",
    "applications": "Applications", "opportunities_added": "Opportunities added",
}


def _fallback(metrics: list[dict], pipeline: int) -> dict:
    """Rule-based recommendations when the model is offline — still actionable."""
    recs = []
    for m in metrics:
        if m["trend"] == "down" and m["last_week"] >= 3:
            recs.append({"action": f"Recover {m['label'].lower()} — down {abs(m['delta_pct'])}% WoW",
                         "rationale": f"{m['this_week']} vs {m['last_week']} last week.",
                         "confidence": 70})
    if not any(m["key"] == "replies" and m["this_week"] for m in metrics):
        recs.append({"action": "Tighten targeting/messaging — no replies this week",
                     "rationale": "Reply volume is the leading indicator of revenue.",
                     "confidence": 65})
    recs = recs[:5] or [{"action": "Keep the engine running and add 3 opportunities",
                         "rationale": "Pipeline compounds; feed it weekly.", "confidence": 60}]
    return {"headline": f"Steady week — ~${round(pipeline/1000)}k expected pipeline open.",
            "recommendations": recs,
            "challenge": "If you could only work ONE objective next week, which dollar "
                         "are you leaving on the table by splitting focus?"}


def build(db: Session) -> dict:
    now = datetime.now(timezone.utc)
    this_start, last_start = now - timedelta(days=7), now - timedelta(days=14)
    this_w = _window(db, this_start, now)
    last_w = _window(db, last_start, this_start)

    metrics = [{"key": k, "label": _LABELS[k], **_trend(this_w[k], last_w[k])}
               for k in _LABELS]

    actions = scoring.build_actions(db)
    pipeline = round(sum(a["value"] * a["probability"] for a in actions))
    top_actions = actions[:5]

    weights = objectives.weights(db)
    payload = {"metrics": metrics, "expected_pipeline": pipeline,
               "top_actions": [{"title": a["title"], "expected_value":
                                round(a["value"] * a["probability"])} for a in top_actions]}

    ai = client.complete_json(
        BOARD_REPORT.format(metrics=_dump(payload), objectives=_dump(weights)))
    review = ai if isinstance(ai, dict) and ai.get("recommendations") else _fallback(metrics, pipeline)

    return {
        "generated_at": now.isoformat(),
        "period": {"from": this_start.date().isoformat(), "to": now.date().isoformat()},
        "metrics": metrics,
        "expected_pipeline": pipeline,
        "top_actions": top_actions,
        "headline": review.get("headline"),
        "recommendations": review.get("recommendations", []),
        "challenge": review.get("challenge"),
    }


def _dump(obj) -> str:
    import json
    return json.dumps(obj, default=str)
