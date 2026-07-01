"""Funnel & performance analytics across every channel.

Builds a real marketing/sales funnel (Sourced → Contacted → Opened → Replied →
Interested → Won) from the lead/restaurant lifecycle statuses, plus reply rates,
SMS, jobs, and a 14-day activity series — so you can see what's working.
"""
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Application, ContentItem, Lead, Message, Restaurant, SocialSnapshot
from ..security import require_role

router = APIRouter(prefix="/analytics", tags=["analytics"])
_read = require_role("admin", "operator", "viewer")

# How far each status sits along the funnel.
_STAGE_INDEX = {
    "New": 0, "Drafted": 1, "Sent": 2, "Opened": 3, "Replied": 4,
    "Follow-up Needed": 4, "Interested": 5, "Closed Won": 6, "Closed Lost": 2,
}
# Funnel levels shown to the user: (label, minimum stage index to count).
_FUNNEL = [("Sourced", 0), ("Contacted", 2), ("Opened", 3),
           ("Replied", 4), ("Interested", 5), ("Won", 6)]


def _funnel(statuses: list[str]) -> list[dict]:
    idx = [_STAGE_INDEX.get(s, 0) for s in statuses]
    return [{"stage": label, "count": sum(1 for i in idx if i >= threshold)}
            for label, threshold in _FUNNEL]


@router.get("/overview")
def overview(db: Session = Depends(get_db), _=Depends(_read)):
    lead_statuses = [s for (s,) in db.query(Lead.status).all()]
    rest_statuses = [s for (s,) in db.query(Restaurant.status)
                     .filter(Restaurant.kind == "prospect").all()]
    all_statuses = lead_statuses + rest_statuses

    emails_sent = db.query(func.count()).select_from(Message).filter(
        Message.channel == "email", Message.sent_at.isnot(None)).scalar() or 0
    emails_drafted = db.query(func.count()).select_from(Message).filter(
        Message.channel == "email", Message.status == "Drafted").scalar() or 0
    replies = db.query(func.count()).select_from(Message).filter(
        Message.direction == "inbound").scalar() or 0
    sms_sent = db.query(func.count()).select_from(Message).filter(
        Message.channel == "sms", Message.direction == "outbound").scalar() or 0
    interested = sum(1 for s in all_statuses if _STAGE_INDEX.get(s, 0) >= 5)
    won = sum(1 for s in all_statuses if s == "Closed Won")
    applied = db.query(func.count()).select_from(Application).filter(
        Application.status.in_(["Applied", "Sent"])).scalar() or 0
    queued = db.query(func.count()).select_from(Application).filter(
        Application.status == "New").scalar() or 0

    # 14-day activity: outbound sends + inbound replies per day.
    since = datetime.now(timezone.utc) - timedelta(days=14)
    sent_by_day = dict(db.query(func.date(Message.sent_at), func.count())
                       .filter(Message.sent_at >= since, Message.direction == "outbound")
                       .group_by(func.date(Message.sent_at)).all())
    repl_by_day = dict(db.query(func.date(Message.created_at), func.count())
                       .filter(Message.created_at >= since, Message.direction == "inbound")
                       .group_by(func.date(Message.created_at)).all())
    activity = []
    for d in range(14, -1, -1):
        day = date.today() - timedelta(days=d)
        activity.append({"date": day.isoformat(),
                         "sent": int(sent_by_day.get(day, 0)),
                         "replied": int(repl_by_day.get(day, 0))})

    reply_rate = round(100 * replies / emails_sent, 1) if emails_sent else 0.0
    return {
        "kpis": {
            "leads_total": len(lead_statuses),
            "restaurant_prospects": len(rest_statuses),
            "emails_sent": emails_sent,
            "emails_drafted": emails_drafted,
            "replies": replies,
            "reply_rate_pct": reply_rate,
            "interested": interested,
            "won": won,
            "sms_sent": sms_sent,
            "jobs_queued": queued,
            "jobs_applied": applied,
        },
        "funnel": _funnel(all_statuses),
        "channels": {
            "insurance": _funnel([s for s, seg in db.query(Lead.status, Lead.segment).all()]),
            "savorymind": _funnel(rest_statuses),
        },
        "activity_14d": activity,
    }


@router.get("/growth")
def growth(db: Session = Depends(get_db), _=Depends(_read)):
    """Content & audience growth across every platform: follower trend per
    platform, per-channel content cadence + engagement, and the platform loops'
    target cadence — so you can see what the media engine is producing and how
    each channel is performing."""
    from .. import content_analytics, platform_loops, posting_times, social

    # Per-platform connection + current followers, and 30-day follower delta.
    conn = social.status(db)
    snaps = db.query(SocialSnapshot.platform, SocialSnapshot.followers,
                     SocialSnapshot.captured_at).order_by(
        SocialSnapshot.captured_at.asc()).limit(2000).all()
    first_by_plat: dict[str, int] = {}
    last_by_plat: dict[str, int] = {}
    series: dict[str, list[dict]] = {}
    for plat, foll, when in snaps:
        if foll is None:
            continue
        first_by_plat.setdefault(plat, foll)
        last_by_plat[plat] = foll
        series.setdefault(plat, []).append(
            {"date": when.date().isoformat() if when else None, "followers": foll})

    ch_summary = content_analytics.channel_summary(db)
    times = posting_times.summary(db)

    # Per-channel content published in the last 14 days (cadence view).
    since = datetime.now(timezone.utc) - timedelta(days=14)
    pub_by_ch = dict(db.query(ContentItem.channel, func.count())
                     .filter(ContentItem.status == "published",
                             ContentItem.published_at >= since)
                     .group_by(ContentItem.channel).all())

    platforms = []
    for name, cfg in platform_loops.LOOPS.items():
        followers = (conn.get(name) or {}).get("followers")
        platforms.append({
            "platform": name,
            "connected": bool((conn.get(name) or {}).get("connected")),
            "followers": followers,
            "follower_delta": (last_by_plat.get(name, 0) - first_by_plat.get(name, 0))
                              if name in last_by_plat else None,
            "per_day_target": cfg["per_day"],
            "auto_publish": cfg["auto"],
            "published_14d": int(pub_by_ch.get(name, 0)),
            "published_total": (ch_summary.get(name) or {}).get("published", 0),
            "avg_engagement": (ch_summary.get(name) or {}).get("avg_engagement", 0.0),
            "top_category": (ch_summary.get(name) or {}).get("top_category"),
            "best_hour": (times.get(name) or {}).get("hour"),
            "best_hour_learned": (times.get(name) or {}).get("learned", False),
        })

    total_followers = sum(v for v in last_by_plat.values())
    return {
        "kpis": {
            "total_followers": total_followers,
            "connected_platforms": sum(1 for p in platforms if p["connected"]),
            "published_14d": sum(p["published_14d"] for p in platforms),
            "daily_target": sum(cfg["per_day"] for cfg in platform_loops.LOOPS.values()),
        },
        "platforms": platforms,
        "follower_series": series,
        "by_category": content_analytics.category_performance(db),
        "top_content": content_analytics.top_performers(db, 10),
    }


@router.get("/revenue")
def revenue(cost: float | None = None, db: Session = Depends(get_db), _=Depends(_read)):
    """Revenue & ROI by business — revenue won, weighted pipeline, win/reply rates,
    and (with ?cost=) cost-per-lead, cost-per-won and ROI."""
    from .. import revenue_analytics
    return revenue_analytics.report(db, cost=cost)


@router.get("/outreach")
def outreach_performance(days: int = 30, db: Session = Depends(get_db), _=Depends(_read)):
    """Outreach performance: the daily send→reply trend, current cold/warm/hot
    funnel, and reply rate — is the client machine trending toward the goal?"""
    from .. import outreach_performance
    return outreach_performance.report(db, days=days)


@router.get("/pipeline")
def pipeline(db: Session = Depends(get_db), _=Depends(_read)):
    """Sales pipeline across all three lead businesses — Insurance (NH/MA/FL),
    BnB Global consulting (US+EU), and SavoryMind (US+EU) — with funnel stages,
    pipeline value, top industries, and SavoryMind geography."""
    from .. import scoring

    def _lead_block(segments: list[str]) -> dict:
        rows = db.query(Lead.status, Lead.industry, Lead.score).filter(
            Lead.segment.in_(segments)).all()
        statuses = [s for (s, _i, _sc) in rows]
        inds: dict[str, int] = {}
        for _s, ind, _sc in rows:
            if ind:
                inds[ind] = inds.get(ind, 0) + 1
        top_industries = sorted(inds.items(), key=lambda kv: kv[1], reverse=True)[:6]
        return {
            "total": len(rows),
            "funnel": _funnel(statuses),
            "emailed": sum(1 for s in statuses if _STAGE_INDEX.get(s, 0) >= 2),
            "replied": sum(1 for s in statuses if _STAGE_INDEX.get(s, 0) >= 4),
            "won": sum(1 for s in statuses if s == "Closed Won"),
            "avg_score": round(sum(sc for _s, _i, sc in rows) / len(rows), 1) if rows else 0,
            "top_industries": [{"name": n, "count": c} for n, c in top_industries],
        }

    rest_rows = db.query(Restaurant.status, Restaurant.city).filter(
        Restaurant.kind == "prospect").all()
    rest_statuses = [s for (s, _c) in rest_rows]
    cities: dict[str, int] = {}
    for _s, c in rest_rows:
        if c:
            cities[c] = cities.get(c, 0) + 1
    top_cities = sorted(cities.items(), key=lambda kv: kv[1], reverse=True)[:8]

    # Expected pipeline value (value × probability) per objective, from scoring.
    actions = scoring.build_actions(db)

    def _value(objective: str) -> int:
        return round(sum(a["value"] * a["probability"] for a in actions
                         if a.get("objective") == objective))

    return {
        "businesses": {
            "insurance": {**_lead_block(["commercial", "personal"]),
                          "scope": "NH · MA · FL", "value": _value("insurance")},
            "consulting": {**_lead_block(["consulting"]),
                           "scope": "US + Europe", "value": _value("consulting")},
            "savorymind": {
                "total": len(rest_rows), "funnel": _funnel(rest_statuses),
                "emailed": sum(1 for s in rest_statuses if _STAGE_INDEX.get(s, 0) >= 2),
                "replied": sum(1 for s in rest_statuses if _STAGE_INDEX.get(s, 0) >= 4),
                "won": sum(1 for s in rest_statuses if s == "Closed Won"),
                "scope": "US + Europe",
                "top_cities": [{"name": n, "count": c} for n, c in top_cities],
            },
        },
    }


@router.get("/learnings")
def learnings(db: Session = Depends(get_db), _=Depends(_read)):
    """What the adaptive layer has learned — per-channel category performance with
    sample sizes, the bandit's next pick, learned posting hours, and which outreach
    subject-line styles earn the most replies."""
    from .. import learning, lead_intel, outreach_analytics
    data = learning.learnings(db)
    rates = outreach_analytics.reply_rates(db)
    data["outreach"] = sorted(
        ([{"style": st, **a} for st, a in rates.items() if st != "none"]),
        key=lambda x: x.get("rate", 0), reverse=True)
    cat_rates = lead_intel.category_reply_rates(db)
    data["lead_categories"] = sorted(
        ([{"category": c, **a} for c, a in cat_rates.items()]),
        key=lambda x: (x.get("rate", 0), x.get("sent", 0)), reverse=True)
    return data


@router.get("/posting-times")
def posting_times_view(db: Session = Depends(get_db), _=Depends(_read)):
    """Best posting hour per platform (learned from engagement, default until
    there's enough data) plus the full hour-by-hour engagement breakdown."""
    from .. import posting_times
    from ..config import settings
    return {"timezone": settings.timezone,
            "summary": posting_times.summary(db),
            "detail": posting_times.learned_hours(db)}
