"""Per-platform posting-time optimizer.

Learns the best hour to post on each channel from when published content actually
earned engagement, then hands the platform loops a concrete next-slot datetime so
each piece is scheduled into that channel's strongest window instead of a fixed
offset. Until there's enough data per channel, it falls back to sensible
per-platform defaults. Everything is read-only and degrades gracefully.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, time, timedelta, timezone

from sqlalchemy.orm import Session

from .config import settings
from .models import ContentItem

log = logging.getLogger("bruno.posting_times")

# Sensible default posting hours (in the configured local tz) before we have
# engagement data to learn from — rough best-practice windows per platform.
DEFAULT_HOURS: dict[str, int] = {
    "linkedin": 8, "instagram": 11, "facebook": 13,
    "x": 9, "tiktok": 19, "youtube": 17, "blog": 10,
}
# Multiple intraday windows per channel so several posts/day land at DIFFERENT
# times (and the content calendar shows a realistic daily schedule, not a stack).
SLOT_HOURS: dict[str, list[int]] = {
    "instagram": [9, 13, 18],
    "facebook": [10, 14, 19],
    "linkedin": [8],
    "x": [9, 15],
    "tiktok": [19],
    "youtube": [17],
    "blog": [10],
}
_FALLBACK_HOUR = 9
_MIN_SAMPLES = 3  # need at least this many posts on a channel to trust learned timing


def _tz():
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(settings.timezone)
    except Exception:  # missing tzdata / bad name → UTC
        return timezone.utc


def learned_hours(db: Session) -> dict[str, dict]:
    """Per-channel posting-time analysis: average engagement by hour-of-day, the
    best hour, and how many published posts informed it (sample size)."""
    tz = _tz()
    buckets: dict[str, dict[int, list[int]]] = defaultdict(lambda: defaultdict(list))
    rows = (db.query(ContentItem)
            .filter(ContentItem.status == "published",
                    ContentItem.published_at.isnot(None))
            .limit(2000).all())
    for r in rows:
        eng = (r.meta or {}).get("engagement")
        if eng is None or not r.published_at:
            continue
        hour = r.published_at.astimezone(tz).hour
        buckets[r.channel][hour].append(int(eng))
    out: dict[str, dict] = {}
    for ch, by_hour in buckets.items():
        samples = sum(len(v) for v in by_hour.values())
        avg = {h: sum(v) / len(v) for h, v in by_hour.items()}
        best = max(avg, key=avg.get) if avg else None
        out[ch] = {"best_hour": best, "samples": samples,
                   "by_hour": {h: round(a, 1) for h, a in avg.items()}}
    return out


def best_hour(db: Session, channel: str, learned: dict | None = None) -> int:
    """Hour (0–23, local tz) to post on a channel — learned once there's enough
    data, otherwise the channel's sensible default."""
    info = (learned if learned is not None else learned_hours(db)).get(channel)
    if info and info.get("best_hour") is not None and info.get("samples", 0) >= _MIN_SAMPLES:
        return int(info["best_hour"])
    return DEFAULT_HOURS.get(channel, _FALLBACK_HOUR)


_PLANNED = ("generated", "needs_approval", "ready", "scheduled")


def _taken_hours(db: Session, channel: str, day, tz) -> set[int]:
    """Local-tz hours already occupied by planned content for this channel on a
    given local date — so we don't double-book a slot."""
    rows = (db.query(ContentItem)
            .filter(ContentItem.channel == channel,
                    ContentItem.scheduled_for.isnot(None),
                    ContentItem.status.in_(_PLANNED)).all())
    taken: set[int] = set()
    for r in rows:
        d = r.scheduled_for.astimezone(tz)
        if d.date() == day:
            taken.add(d.hour)
    return taken


def next_slot(db: Session, channel: str, now: datetime | None = None) -> datetime:
    """Next free posting datetime (UTC) for this channel. Spreads multiple posts
    across the channel's intraday windows, then rolls to the next day when today's
    windows are full — so the calendar shows posts across today, tomorrow, etc."""
    tz = _tz()
    now = (now or datetime.now(timezone.utc)).astimezone(tz)
    hours = sorted(set(SLOT_HOURS.get(channel) or [best_hour(db, channel)]))
    for day_offset in range(0, 21):
        day = (now + timedelta(days=day_offset)).date()
        taken = _taken_hours(db, channel, day, tz)
        for h in hours:
            slot = datetime.combine(day, time(hour=h), tzinfo=tz)
            if slot <= now or h in taken:
                continue
            return slot.astimezone(timezone.utc)
    return (now + timedelta(days=1)).astimezone(timezone.utc)


def summary(db: Session) -> dict[str, dict]:
    """Per-platform posting-time view for the dashboard: chosen hour, whether it's
    learned or default, and the sample size behind it."""
    learned = learned_hours(db)
    out: dict[str, dict] = {}
    for ch in DEFAULT_HOURS:
        info = learned.get(ch) or {}
        samples = info.get("samples", 0)
        is_learned = info.get("best_hour") is not None and samples >= _MIN_SAMPLES
        out[ch] = {
            "hour": best_hour(db, ch, learned),
            "learned": is_learned,
            "samples": samples,
            "default_hour": DEFAULT_HOURS[ch],
        }
    return out
