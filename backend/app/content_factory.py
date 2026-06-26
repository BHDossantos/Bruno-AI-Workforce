"""The Content Factory — one idea → channel-ready content for every platform.

Pulls brand voice, checks content memory so we don't repeat ourselves (embedding
similarity → forces a fresh angle), generates a multi-channel pack in one pass,
and stores each piece with a status driven by the approval mode:

  1 generate only · 2 generate+approve · 3 auto-schedule · 4 auto-publish · 5 autonomous
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from . import brand, memory
from .ai import client
from .ai.prompts import CONTENT_FACTORY
from .config import settings
from .models import ContentItem

log = logging.getLogger("bruno.content_factory")

# Channels the factory produces; which can be auto-published to a connected account.
CHANNELS = ["blog", "linkedin", "instagram", "tiktok", "youtube", "x", "facebook", "email", "podcast"]
_PUBLISHABLE = {"linkedin", "instagram", "facebook", "x"}  # via the social publisher
_SIMILAR = 0.88  # cosine above this == "we've covered this"


def _dedupe_hashtags(s: str | None) -> str | None:
    """Keep only the first occurrence of each hashtag (case-insensitive), so a
    post never shows '#AI #Growth #AI #Growth'."""
    if not s:
        return s
    seen, out = set(), []
    for tok in re.findall(r"#\w+", s):
        k = tok.lower()
        if k not in seen:
            seen.add(k)
            out.append(tok)
    return " ".join(out) if out else None


def compose_caption(body: str | None, hashtags: str | None) -> str:
    """Build a publish-ready caption: body + only the hashtags not already present
    in the body, de-duplicated — so tags are never doubled."""
    body = (body or "").strip()
    in_body = {t.lower() for t in re.findall(r"#\w+", body)}
    tags, seen = [], set()
    for tok in re.findall(r"#\w+", hashtags or ""):
        k = tok.lower()
        if k in in_body or k in seen:
            continue
        seen.add(k)
        tags.append(tok)
    return (f"{body}\n\n{' '.join(tags)}".strip() if tags else body)


def _status_for_mode(db: Session, channel: str) -> tuple[str, datetime | None]:
    # Always assign a concrete posting slot so EVERY generated piece lands on a
    # specific day/time in the content calendar (today vs tomorrow vs later).
    from . import control, posting_times
    slot = posting_times.next_slot(db, channel)
    # Semi/manual mode: content waits in the Approval Queue until you approve it.
    # Only full-auto mode auto-schedules to publish without review.
    if control.get_mode(db) != "auto":
        return "needs_approval", slot
    mode = settings.content_approval_mode
    if mode <= 1:
        return "generated", slot
    if mode == 2:
        return "needs_approval", slot
    if mode == 3:  # auto-schedule into the channel's learned best posting window
        return "scheduled", slot
    return "scheduled", datetime.now(timezone.utc)  # 4/5: publish on next content-cron tick


def _whats_working(db: Session) -> str:
    """A learning signal for the generator: the angles/topics currently earning the
    most engagement, so new content leans into what's proven to resonate."""
    try:
        from . import content_analytics
        top = content_analytics.top_performers(db, 5)
    except Exception:  # pragma: no cover - learning is best-effort
        return ""
    winners = [t.get("topic") for t in top if t.get("engagement")]
    if not winners:
        return ""
    return ("WHAT'S WORKING (lean into these proven angles, don't copy them): "
            + "; ".join(w for w in winners if w))


def covered_recently(db: Session, topic: str) -> list[str]:
    """Titles of prior content on a very similar topic (for a fresh-angle nudge)."""
    qv = client.embed(topic)
    if not qv:
        return []
    rows = (db.query(ContentItem).filter(ContentItem.embedding.isnot(None))
            .order_by(ContentItem.created_at.desc()).limit(500).all())
    hits = [r for r in rows if memory._cosine(qv, r.embedding or []) >= _SIMILAR]
    return list({r.topic for r in hits})[:5]


def generate_pack(db: Session, topic: str, business: str = "executive",
                  channels: list[str] | None = None) -> dict:
    """Produce + store channel content for one idea. Returns a summary."""
    channels = [c for c in (channels or CHANNELS) if c in CHANNELS]
    # Music is a fan-facing romance brand — never let it land on LinkedIn (the user
    # explicitly asked for no music there). This guard is pure so it always applies.
    if business == "music":
        channels = [c for c in channels if c != "linkedin"]
    if not client.is_live():
        return {"ok": False, "reason": "generation unavailable (set OPENAI_API_KEY)", "topic": topic}
    # Inject the Bruno D brand bible so output builds the universe + drives streams.
    guidance = ""
    if business == "music":
        from . import music_brand
        guidance = music_brand.promo_context(db)
    elif business == "foundation":
        guidance = (f"This is for the {settings.foundation_name} (a nonprofit). "
                    f"Mission: {settings.foundation_mission} Tagline: {settings.foundation_tagline}. "
                    f"Pillars: {settings.foundation_pillars}. Lead with impact and people "
                    "(students, communities, artists); invite support (donate/volunteer/partner). "
                    "Warm, credible, never salesy; no fundraising guarantees or financial claims.")
    prior = covered_recently(db, topic)
    freshness = (f"We've already covered: {', '.join(prior)}. Take a clearly NEW angle."
                 if prior else "This is a fresh topic.")
    # Learn & act: lean into what's actually earning engagement.
    guidance = (guidance + "\n\n" + _whats_working(db)).strip()
    # Apply best-practice marketing frameworks (copywriting, social, psychology,
    # content strategy) from the packaged skills.
    from .ai import skills
    sysp = skills.system_prompt("copywriting", "social", "marketing-psychology",
                                "content-strategy")
    pack = client.complete_json(CONTENT_FACTORY.format(
        brand=brand.context(db), business=business, topic=topic,
        freshness=freshness, guidance=guidance), system=sysp)
    pack = pack if isinstance(pack, dict) else {}
    if not pack:
        return {"ok": False, "reason": "generation unavailable (set OPENAI_API_KEY)", "topic": topic}

    emb = client.embed(topic)
    created = []
    for ch in channels:
        data = pack.get(ch)
        if not isinstance(data, dict):
            continue
        status, sched = _status_for_mode(db, ch)
        if ch not in _PUBLISHABLE and status == "scheduled":
            status = "ready"  # non-social pieces (blog/email/podcast) are drafts to
            # grab manually — keep the date so they still show by day on the calendar
        item = ContentItem(
            topic=topic, business=business, channel=ch,
            title=data.get("title") or data.get("subject"),
            body=data.get("body") or data.get("caption") or data.get("script"),
            hashtags=_dedupe_hashtags(data.get("hashtags")), status=status, embedding=emb,
            meta={"angle": pack.get("angle")}, scheduled_for=sched)
        db.add(item)
        created.append(ch)
    db.commit()
    return {"ok": True, "topic": topic, "business": business, "angle": pack.get("angle"),
            "channels": created, "fresh_angle": bool(prior)}


# Planned-but-not-published statuses — the drafts a "regenerate" should replace.
_REGEN_STATUSES = ["generated", "needs_approval", "ready", "scheduled"]


def regenerate_item(db: Session, content_id: str) -> dict:
    """Dismiss one stale draft and rewrite it (same topic/business/channel) at the
    current quality bar."""
    item = db.query(ContentItem).filter(ContentItem.id == content_id).first()
    if not item:
        return {"ok": False, "reason": "content not found"}
    topic, business, channel = item.topic, item.business or "executive", item.channel
    item.status = "dismissed"
    db.commit()
    return generate_pack(db, topic, business, channels=[channel])


def regenerate_stale(db: Session, business: str | None = None,
                     channel: str | None = None) -> dict:
    """Clear the un-published draft backlog and let the engine rewrite fresh
    content at the new quality bar. Dismisses planned (not yet published) pieces,
    then re-runs the per-platform loops + music cadence to refill the cadence."""
    from . import platform_loops
    q = db.query(ContentItem).filter(ContentItem.status.in_(_REGEN_STATUSES))
    if business:
        q = q.filter(ContentItem.business == business)
    if channel:
        q = q.filter(ContentItem.channel == channel)
    stale = q.all()
    for it in stale:
        it.status = "dismissed"
    db.commit()
    result = platform_loops.run_all(db, [channel] if channel else None)
    return {"ok": True, "cleared": len(stale),
            "regenerated": result.get("made_total", 0), "detail": result}


def out(i: ContentItem) -> dict:
    return {"id": str(i.id), "topic": i.topic, "business": i.business, "channel": i.channel,
            "title": i.title, "body": i.body, "hashtags": i.hashtags, "status": i.status,
            "scheduled_for": i.scheduled_for.isoformat() if i.scheduled_for else None,
            "created_at": i.created_at.isoformat() if i.created_at else None}


def publish_due(db: Session) -> dict:
    """Publish scheduled social content that's due, via the unified social publisher."""
    from . import control, social
    if control.is_paused_safe(db):
        return {"due": 0, "published": 0, "paused": True}
    now = datetime.now(timezone.utc)
    due = (db.query(ContentItem).filter(ContentItem.status == "scheduled",
           ContentItem.channel.in_(list(_PUBLISHABLE)),
           ContentItem.scheduled_for <= now).limit(50).all())
    published = 0
    for item in due:
        caption = compose_caption(item.body, item.hashtags)
        # Only post to the ONE platform this piece targets.
        is_conn, fn, _ = social.PLATFORMS.get(item.channel, (None, None, None))
        if not is_conn or not is_conn(db):
            item.status = "needs_connection"
            continue
        # Video channels (TikTok/YouTube) need a produced clip, not an image.
        if item.channel in social.VIDEO_CHANNELS:
            video_url = (item.meta or {}).get("video_url")
            if not video_url:
                item.status = "needs_video"
                continue
            res = fn(db, caption, video_url)
        else:
            res = fn(db, caption, None)
        item.status = "published" if res.get("ok") else "failed"
        item.meta = {**(item.meta or {}), "result": res}
        if res.get("ok"):
            item.published_at = now
            published += 1
    db.commit()
    return {"due": len(due), "published": published}


def publish_blog_due(db: Session) -> dict:
    """Publish approved blog pieces to Medium (when connected). Blog items are
    'ready' drafts until you approve one (→ scheduled); this posts those. The
    Medium connection's publish_status (default 'draft') controls whether they go
    out live or land as a Medium draft for final review."""
    from .integrations import medium_api
    if not medium_api.is_connected(db):
        return {"due": 0, "published": 0, "reason": "Medium not connected"}
    now = datetime.now(timezone.utc)
    due = (db.query(ContentItem).filter(ContentItem.status == "scheduled",
           ContentItem.channel == "blog").limit(25).all())
    published = 0
    for item in due:
        tags = [t.strip("# ") for t in (item.hashtags or "").split() if t.strip("# ")]
        res = medium_api.post_article(db, item.title or item.topic, item.body or "", tags)
        item.status = "published" if res.get("ok") else "failed"
        item.meta = {**(item.meta or {}), "result": res}
        if res.get("ok"):
            item.published_at = now
            published += 1
    db.commit()
    return {"due": len(due), "published": published}
