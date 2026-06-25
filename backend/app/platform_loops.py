"""Per-platform commander loops.

The Influence Commander's single daily run produces one idea for every channel.
That's a good baseline, but every platform has its own cadence, its own audience,
and its own "what works" — what lands on LinkedIn rarely lands the same way on
TikTok. These loops give each platform an independent optimization loop:

- enforce a per-platform daily cadence (don't over- or under-post any channel),
- pick the next topic from the category that performs best *on that platform*,
- respect each platform's terms: only platforms with an official publish path
  auto-schedule; the rest produce ready-to-post drafts (assist mode).

Each loop is self-contained and failure-isolated, so one platform stalling never
holds up the others. Everything degrades gracefully offline (no OpenAI key →
the factory simply reports it can't generate, and the loop reports zero made).
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from . import content_analytics, content_factory
from .config import settings
from .models import ContentItem

log = logging.getLogger("bruno.platform_loops")

# Per-platform loop config:
#   per_day   — target pieces queued/published for this channel each day
#   auto      — True if there's an official publish path (own-content, ToS-OK);
#               False → assist mode (drafts only, a human posts on-platform)
#   businesses— business lines that feed this platform, rotated day-to-day
LOOPS: dict[str, dict] = {
    "linkedin":  {"per_day": 1, "auto": True,
                  "businesses": ["executive", "bnbglobal"]},
    "instagram": {"per_day": 1, "auto": True,
                  "businesses": ["music", "savorymind", "bnbglobal"]},
    "facebook":  {"per_day": 1, "auto": True,
                  "businesses": ["savorymind", "bnbglobal", "music"]},
    "x":         {"per_day": 2, "auto": True,
                  "businesses": ["bnbglobal", "executive", "music"]},
    "tiktok":    {"per_day": 1, "auto": False,
                  "businesses": ["music", "savorymind"]},
    "youtube":   {"per_day": 1, "auto": False,
                  "businesses": ["bnbglobal", "music"]},
}

# Statuses that count as "already in the pipeline for today" for cadence purposes.
_ACTIVE = ("generated", "needs_approval", "ready", "scheduled", "published")


def _queued_today(db: Session, channel: str) -> int:
    """How many pieces for this channel are already in flight today."""
    start = datetime.combine(date.today(), datetime.min.time(), tzinfo=timezone.utc)
    return int(db.query(func.count()).select_from(ContentItem).filter(
        ContentItem.channel == channel,
        ContentItem.status.in_(_ACTIVE),
        ContentItem.created_at >= start).scalar() or 0)


def _pick_business(cfg: dict, seed: int) -> str:
    businesses = cfg["businesses"] or ["executive"]
    return businesses[seed % len(businesses)]


def run_platform(db: Session, platform: str, seed: int | None = None) -> dict:
    """Top up one platform's queue to its daily cadence with channel-optimized
    content. Returns a per-platform summary."""
    cfg = LOOPS.get(platform)
    if not cfg:
        return {"platform": platform, "ok": False, "reason": "unknown platform"}
    if not settings.content_factory_enabled:
        return {"platform": platform, "ok": False, "reason": "content factory disabled"}

    if seed is None:
        seed = date.today().timetuple().tm_yday
    have = _queued_today(db, platform)
    need = max(0, cfg["per_day"] - have)
    if need <= 0:
        return {"platform": platform, "ok": True, "made": 0, "queued": have,
                "per_day": cfg["per_day"], "note": "cadence already met"}

    made, topics = 0, []
    for i in range(need):
        business = _pick_business(cfg, seed + i)
        topic = content_analytics.best_topic_for_channel(db, platform, business, seed + i)
        res = content_factory.generate_pack(db, topic, business, channels=[platform])
        if res.get("ok") and platform in (res.get("channels") or []):
            made += 1
            topics.append(topic)
        else:
            # generation unavailable (offline) — stop trying this run
            return {"platform": platform, "ok": False, "made": made,
                    "reason": res.get("reason", "generation failed")}
    return {"platform": platform, "ok": True, "made": made, "topics": topics,
            "auto": cfg["auto"], "per_day": cfg["per_day"], "queued": have + made}


def run_all(db: Session, platforms: list[str] | None = None) -> dict:
    """Run every platform loop (failure-isolated). Used by the Influence Commander
    and the /cron/platform-loops trigger."""
    seed = date.today().timetuple().tm_yday
    targets = [p for p in (platforms or list(LOOPS)) if p in LOOPS]
    out: dict[str, dict] = {}
    for p in targets:
        try:
            out[p] = run_platform(db, p, seed)
        except Exception as exc:  # one platform must never stop the rest
            log.exception("platform loop failed for %s", p)
            out[p] = {"platform": p, "ok": False, "reason": str(exc)}
    total = sum(r.get("made", 0) for r in out.values())
    return {"made_total": total, "platforms": out}
