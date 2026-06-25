"""The Content Factory — one idea → channel-ready content for every platform.

Pulls brand voice, checks content memory so we don't repeat ourselves (embedding
similarity → forces a fresh angle), generates a multi-channel pack in one pass,
and stores each piece with a status driven by the approval mode:

  1 generate only · 2 generate+approve · 3 auto-schedule · 4 auto-publish · 5 autonomous
"""
from __future__ import annotations

import logging
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


def _status_for_mode(db: Session, channel: str) -> tuple[str, datetime | None]:
    mode = settings.content_approval_mode
    if mode <= 1:
        return "generated", None
    if mode == 2:
        return "needs_approval", None
    if mode == 3:  # auto-schedule into the channel's learned best posting window
        from . import posting_times
        return "scheduled", posting_times.next_slot(db, channel)
    return "scheduled", datetime.now(timezone.utc)  # 4/5: publish on next content-cron tick


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
    if not client.is_live():
        return {"ok": False, "reason": "generation unavailable (set OPENAI_API_KEY)", "topic": topic}
    prior = covered_recently(db, topic)
    freshness = (f"We've already covered: {', '.join(prior)}. Take a clearly NEW angle."
                 if prior else "This is a fresh topic.")
    pack = client.complete_json(CONTENT_FACTORY.format(
        brand=brand.context(db), business=business, topic=topic, freshness=freshness))
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
            status, sched = "ready", None  # non-social pieces are drafts to use
        item = ContentItem(
            topic=topic, business=business, channel=ch,
            title=data.get("title") or data.get("subject"),
            body=data.get("body") or data.get("caption") or data.get("script"),
            hashtags=data.get("hashtags"), status=status, embedding=emb,
            meta={"angle": pack.get("angle")}, scheduled_for=sched)
        db.add(item)
        created.append(ch)
    db.commit()
    return {"ok": True, "topic": topic, "business": business, "angle": pack.get("angle"),
            "channels": created, "fresh_angle": bool(prior)}


def out(i: ContentItem) -> dict:
    return {"id": str(i.id), "topic": i.topic, "business": i.business, "channel": i.channel,
            "title": i.title, "body": i.body, "hashtags": i.hashtags, "status": i.status,
            "scheduled_for": i.scheduled_for.isoformat() if i.scheduled_for else None,
            "created_at": i.created_at.isoformat() if i.created_at else None}


def publish_due(db: Session) -> dict:
    """Publish scheduled social content that's due, via the unified social publisher."""
    from . import social
    now = datetime.now(timezone.utc)
    due = (db.query(ContentItem).filter(ContentItem.status == "scheduled",
           ContentItem.channel.in_(list(_PUBLISHABLE)),
           ContentItem.scheduled_for <= now).limit(50).all())
    published = 0
    for item in due:
        caption = " ".join(filter(None, [item.body, item.hashtags]))
        # Only post to the ONE platform this piece targets.
        is_conn, fn, _ = social.PLATFORMS.get(item.channel, (None, None, None))
        if not is_conn or not is_conn(db):
            item.status = "needs_connection"
            continue
        # TikTok is video-only — it needs a produced clip, not an image.
        if item.channel == "tiktok":
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
