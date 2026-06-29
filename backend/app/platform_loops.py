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
    # Instagram + Facebook: 3/day each — exactly music · BnB Global · insurance
    # (per the spec: 3 businesses × 3 posts × 2 platforms = 9 contents/day).
    # Instagram + Facebook: 3/day each — music · BnB Global · insurance · Bruno D.
    "instagram": {"per_day": 3, "auto": True,
                  "businesses": ["music", "bnbglobal", "insurance", "personal"]},
    "facebook":  {"per_day": 3, "auto": True,
                  "businesses": ["music", "bnbglobal", "insurance"]},
                  "businesses": ["music", "bnbglobal", "insurance", "personal"]},
    # LinkedIn: 1/day — BnB + insurance + foundation + Bruno D personal brand
    # (no music on LinkedIn, per the rule).
    "linkedin":  {"per_day": 1, "auto": True,
                  "businesses": ["bnbglobal", "insurance", "foundation", "personal"]},
    # Medium (blog): 1/day long-form — BnB + insurance + foundation + personal.
    "blog":      {"per_day": 1, "auto": False,
                  "businesses": ["bnbglobal", "insurance", "foundation", "personal"]},
    "x":         {"per_day": 2, "auto": True,
                  "businesses": ["bnbglobal", "personal", "music"]},
    "tiktok":    {"per_day": 1, "auto": False,
                  "businesses": ["music"]},
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
        elif res.get("duplicate"):
            continue  # near-duplicate idea — skip this slot, try the next topic
        else:
            # generation unavailable (offline) — stop trying this run
            return {"platform": platform, "ok": False, "made": made,
                    "reason": res.get("reason", "generation failed")}
    return {"platform": platform, "ok": True, "made": made, "topics": topics,
            "auto": cfg["auto"], "per_day": cfg["per_day"], "queued": have + made}


# Music gets a guaranteed minimum cadence of its own (the user wants ≥3 music
# campaigns/day automatically), posted across these channels — never LinkedIn.
MUSIC_CHANNELS = ["instagram", "facebook", "x"]
MUSIC_MIN_PER_DAY = 3


def _music_made_today(db: Session) -> int:
    start = datetime.combine(date.today(), datetime.min.time(), tzinfo=timezone.utc)
    return int(db.query(func.count()).select_from(ContentItem).filter(
        ContentItem.business == "music",
        ContentItem.status.in_(_ACTIVE),
        ContentItem.created_at >= start).scalar() or 0)


def ensure_music_cadence(db: Session, target: int = MUSIC_MIN_PER_DAY) -> dict:
    """Guarantee at least `target` music pieces are produced today, regardless of
    where music landed in the per-platform rotation."""
    if not settings.content_factory_enabled:
        return {"ok": False, "reason": "content factory disabled"}
    have = _music_made_today(db)
    need = max(0, target - have)
    seed = date.today().timetuple().tm_yday
    made = 0
    for i in range(need):
        channel = MUSIC_CHANNELS[(seed + i) % len(MUSIC_CHANNELS)]
        topic = content_analytics.best_topic_for_channel(db, channel, "music", seed + i)
        res = content_factory.generate_pack(db, topic, "music", channels=[channel])
        if res.get("ok") and channel in (res.get("channels") or []):
            made += 1
        elif res.get("duplicate"):
            continue  # near-duplicate idea — skip this slot, try the next topic
        else:
            return {"ok": False, "made": made, "had": have,
                    "reason": res.get("reason", "generation failed")}
    return {"ok": True, "made": made, "had": have, "target": target}


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
    # Guarantee the daily music minimum on top of the rotation.
    try:
        out["music_cadence"] = ensure_music_cadence(db)
    except Exception as exc:
        log.exception("music cadence failed")
        out["music_cadence"] = {"ok": False, "reason": str(exc)}
    total = sum(r.get("made", 0) for r in out.values())
    return {"made_total": total, "platforms": out}
