"""Outreach performance — is the client machine actually working, and trending up?

A read-only report over the data the engine already produces: the daily send →
reply trend, the current cold/warm/hot funnel across every business, and reply
rate. It answers "are we moving toward 15 clients/day?" and surfaces the warm and
hot leads that cold sends turn into — the ones worth acting on now.

Pure read: it never sends anything, so it can't affect the live outreach flow.
Dates are bucketed in Python (no DB-dialect date functions) so it runs anywhere.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session
from sqlalchemy import or_, func

from .lead_temperature import HOT, WARM, classify
from .models import Lead, Message, Restaurant, MailboxSyncHealth


def _day(dt: datetime | None) -> str | None:
    return (dt.astimezone(timezone.utc) if dt.tzinfo else dt).date().isoformat() if dt else None


def report(db: Session, days: int = 30) -> dict:
    days = max(7, min(int(days or 30), 90))
    today = datetime.now(timezone.utc).date()
    start_date = today - timedelta(days=days - 1)
    start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)

    # Seed every day in the window so the chart has no gaps.
    series = {(start_date + timedelta(days=i)).isoformat(): {"sent": 0, "replies": 0}
              for i in range(days)}

    msgs = (db.query(Message.direction, Message.sent_at, Message.created_at, Message.status, Message.delivery_status)
            .filter(or_(Message.created_at >= start_dt, Message.sent_at >= start_dt)).all())
    sent_total = replies_total = delivered_total = 0
    for direction, sent_at, created_at, status, delivery_status in msgs:
        if direction == "outbound" and sent_at:
            d = _day(sent_at)
            if d in series:
                series[d]["sent"] += 1
                sent_total += 1
                delivered_total += delivery_status in ("delivered", "opened", "clicked")
        elif direction == "inbound" and status not in ("Bounce Report", "Unmatched Inbound"):
            d = _day(created_at)
            if d in series:
                series[d]["replies"] += 1
                replies_total += 1

    legacy_replied = db.query(func.count()).select_from(Message).filter(
        Message.direction == "outbound", Message.status == "Replied").scalar() or 0
    sync_health = [{"account": h.account, "status": h.status, "checked_at": h.checked_at,
                    "completed_through": h.completed_through, "error_code": h.error_code}
                   for h in db.query(MailboxSyncHealth).all()]
    daily = [{"date": d, **v} for d, v in sorted(series.items())]

    # Current funnel across every business (leads + restaurant prospects).
    lead_statuses = [s for (s,) in db.query(Lead.status).all()]
    rest_statuses = [s for (s,) in db.query(Restaurant.status)
                     .filter(Restaurant.kind == "prospect").all()]
    funnel = {"cold": 0, "warm": 0, "hot": 0, "dead": 0}
    for s in lead_statuses + rest_statuses:
        funnel[classify(s)] = funnel.get(classify(s), 0) + 1
    actionable = funnel[WARM] + funnel[HOT]  # the leads worth touching now

    reply_rate = round(replies_total / sent_total, 3) if sent_total else 0.0

    return {
        "days": days,
        "totals": {
            "sent": sent_total, "recorded_sends": sent_total, "replies": replies_total, "reply_rate": reply_rate,
            "delivery_confirmed": delivered_total, "delivery_unconfirmed": sent_total - delivered_total,
            "legacy_replied_outbound_undated": legacy_replied,
            "reply_count_basis": "observed inbound events; legacy outbound Replied rows have no reply timestamp",
            "reply_rate_basis": "inbound events / recorded sends, not a cohort conversion rate",
            "warm": funnel[WARM], "hot": funnel[HOT], "actionable": actionable,
        },
        "sync_health": sync_health,
        "reply_count_complete": False,  # provider/account coverage is not guaranteed
        "timezone": "UTC", "window_start": start_dt.isoformat(),
        "funnel": funnel,
        "daily": daily,
    }
