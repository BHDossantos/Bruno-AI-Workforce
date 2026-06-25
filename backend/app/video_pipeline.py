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
import os
import shutil
import subprocess
import tempfile

from sqlalchemy.orm import Session

from .ai import client
from .integrations import elevenlabs, storage, video_gen
from .models import ContentItem

log = logging.getLogger("bruno.video_pipeline")


def _ffmpeg() -> str | None:
    return shutil.which("ffmpeg")


def available() -> dict:
    return {"voiceover": elevenlabs.is_configured(), "video": video_gen.is_configured(),
            "hosting": storage.is_configured(), "render": _ffmpeg() is not None}


def _render_slideshow(cover: bytes, audio: bytes) -> bytes | None:
    """Stitch a still cover image + voiceover into an MP4 (duration = audio)."""
    if not (_ffmpeg() and cover and audio):
        return None
    d = tempfile.mkdtemp(prefix="bruno_vid_")
    try:
        img, aud, out = f"{d}/cover.png", f"{d}/vo.mp3", f"{d}/out.mp4"
        with open(img, "wb") as f:
            f.write(cover)
        with open(aud, "wb") as f:
            f.write(audio)
        cmd = [_ffmpeg(), "-y", "-loop", "1", "-i", img, "-i", aud,
               "-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p",
               "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
               "-c:a", "aac", "-b:a", "192k", "-shortest", out]
        subprocess.run(cmd, check=True, capture_output=True, timeout=300)
        with open(out, "rb") as f:
            return f.read()
    except Exception as exc:  # pragma: no cover - needs ffmpeg + assets
        log.warning("ffmpeg render failed: %s", exc)
        return None
    finally:
        shutil.rmtree(d, ignore_errors=True)


def start_for_content(db: Session, content_id: str) -> dict:
    item = db.query(ContentItem).filter(ContentItem.id == content_id).first()
    if not item:
        return {"ok": False, "reason": "content not found"}
    script = item.body or item.title or item.topic
    mm = dict((item.meta or {}).get("media") or {})

    # 1) Voiceover (keep bytes for the render).
    audio = elevenlabs.tts(script) if elevenlabs.is_configured() else None
    if audio and storage.is_configured() and not mm.get("voiceover_url"):
        url = storage.upload_public(audio, f"vo/{item.id}.mp3", "audio/mpeg")
        if url:
            mm["voiceover_url"] = url

    # 2) Cover image (keep bytes for the render).
    cover = client.generate_image(f"Vertical social cover for: {item.title or item.topic}") \
        if client.is_live() else None
    if cover and storage.is_configured() and not mm.get("cover_url"):
        url = storage.upload_public(cover, f"cover/{item.id}.png", "image/png")
        if url:
            mm["cover_url"] = url

    # 3a) Render a finished narrated MP4 from image + voiceover (no paid video API).
    if not mm.get("video_url") and audio and cover and _ffmpeg():
        mp4 = _render_slideshow(cover, audio)
        if mp4 and storage.is_configured():
            vurl = storage.upload_public(mp4, f"video/{item.id}.mp4", "video/mp4")
            if vurl:
                mm["video_url"], mm["video_status"] = vurl, "ready"

    # 3b) Optionally also kick a higher-quality AI clip from a provider.
    if video_gen.is_configured() and not mm.get("video_job") and mm.get("video_status") != "ready":
        job = video_gen.create(f"{item.topic}. {item.title or ''}")
        if job:
            mm["video_job"], mm["video_status"] = job, "pending"

    item.meta = {**(item.meta or {}), "media": mm}
    db.commit()
    return {"ok": True, "media": mm, "available": available()}


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
