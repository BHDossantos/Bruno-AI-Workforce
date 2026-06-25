"""Video pipeline — turn a Content-Factory script into real media assets.

For a content item it: generates an AI voiceover (ElevenLabs) and a cover image,
hosts them publicly, and kicks off an async AI video-clip generation. A cron
polls the video job and attaches the finished URL. Every stage is independent
and guarded — whatever's configured runs; the rest is skipped.

Assets land on ContentItem.meta.media = {voiceover_url, cover_url, video_status,
video_job, video_url}. (Stitching audio+video into one file needs a render step
like Remotion/FFmpeg — a future infra add; the assets are produced here.)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from . import media
from .integrations import elevenlabs, storage, video_gen
from .models import ContentItem

log = logging.getLogger("bruno.video_pipeline")


def available() -> dict:
    return {"voiceover": elevenlabs.is_configured(), "video": video_gen.is_configured(),
            "hosting": storage.is_configured()}


def start_for_content(db: Session, content_id: str) -> dict:
    item = db.query(ContentItem).filter(ContentItem.id == content_id).first()
    if not item:
        return {"ok": False, "reason": "content not found"}
    script = item.body or item.title or item.topic
    media_meta = dict((item.meta or {}).get("media") or {})

    # 1) Voiceover → host as mp3.
    if elevenlabs.is_configured() and storage.is_configured() and not media_meta.get("voiceover_url"):
        audio = elevenlabs.tts(script)
        if audio:
            url = storage.upload_public(audio, f"vo/{item.id}.mp3", "audio/mpeg")
            if url:
                media_meta["voiceover_url"] = url

    # 2) Cover image → host.
    if not media_meta.get("cover_url"):
        cover = media.generate_and_host(item.title or item.topic, f"cover-{item.id}")
        if cover:
            media_meta["cover_url"] = cover

    # 3) Kick off async video-clip generation.
    if video_gen.is_configured() and not media_meta.get("video_url"):
        job = video_gen.create(f"{item.topic}. {item.title or ''}")
        if job:
            media_meta["video_job"] = job
            media_meta["video_status"] = "pending"

    item.meta = {**(item.meta or {}), "media": media_meta}
    db.commit()
    return {"ok": True, "media": media_meta, "available": available()}


def sync_pending(db: Session) -> dict:
    """Poll in-flight video jobs and attach finished clip URLs."""
    rows = (db.query(ContentItem)
            .filter(ContentItem.meta.isnot(None))
            .order_by(ContentItem.created_at.desc()).limit(300).all())
    done = checked = 0
    for it in rows:
        mm = (it.meta or {}).get("media") or {}
        if mm.get("video_status") != "pending" or not mm.get("video_job"):
            continue
        checked += 1
        status, url = video_gen.poll(mm["video_job"])
        if status == "completed" and url:
            mm["video_url"], mm["video_status"] = url, "ready"
            it.meta = {**(it.meta or {}), "media": mm}
            it.published_at = it.published_at  # touch
            done += 1
        elif status == "failed":
            mm["video_status"] = "failed"
            it.meta = {**(it.meta or {}), "media": mm}
    db.commit()
    return {"checked": checked, "ready": done}
