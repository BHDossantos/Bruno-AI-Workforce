"""Release-as-eras engine — turn ONE song into a full content kit.

Independent artists who release "song, song, song" are forgettable; audiences
remember ERAS. Given a song, this builds the 15-20 piece kit the brand needs —
music-video treatment, lyric video, sax/acoustic/piano versions, behind-the-song,
the ONE repeatable TikTok line, reel cuts, teasers, and cross-posts — all on-brand
via the Bruno D bible, all pointed at streams/follows, and never on LinkedIn.

Pieces are stored as ContentItems in "ready" status (drafts to review/produce, not
auto-blasted) tagged with the release id, so they show up in the factory/calendar.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from . import brand, music_brand
from .ai import client
from .ai.prompts import MUSIC_RELEASE_KIT
from .models import ContentItem, MusicRelease

log = logging.getLogger("bruno.music_release")

# (deliverable key, human label, channel) — the kit's shape. ~14 pieces + key line.
DELIVERABLES: list[tuple[str, str, str]] = [
    ("music_video", "Music video (cinematic treatment)", "youtube"),
    ("lyric_video", "Lyric video", "youtube"),
    ("behind_the_song", "Behind the song", "youtube"),
    ("sax_version", "Live sax version", "instagram"),
    ("acoustic_version", "Acoustic version", "instagram"),
    ("piano_version", "Piano version", "instagram"),
    ("story_version", "The real story behind it", "instagram"),
    ("teaser", "Pre-release teaser", "instagram"),
    ("tiktok_hook", "The one repeatable line", "tiktok"),
    ("reel_1", "Reel cut 1", "instagram"),
    ("reel_2", "Reel cut 2", "tiktok"),
    ("reel_3", "Reel cut 3", "instagram"),
    ("x_post", "X post", "x"),
    ("facebook_post", "Facebook post", "facebook"),
]


def _piece(raw) -> dict:
    """Normalize an AI deliverable into title/body/hashtags regardless of shape."""
    if isinstance(raw, str):
        return {"title": None, "body": raw, "hashtags": None}
    if isinstance(raw, dict):
        body = raw.get("body") or raw.get("script") or raw.get("treatment") or \
            raw.get("caption") or raw.get("concept") or raw.get("notes")
        hashtags = raw.get("hashtags")
        if isinstance(hashtags, list):
            hashtags = " ".join(str(h) for h in hashtags)
        return {"title": raw.get("title"), "body": body, "hashtags": hashtags}
    return {"title": None, "body": None, "hashtags": None}


def build_kit(db: Session, release: MusicRelease) -> dict:
    """Generate the full content kit for one release and store each piece."""
    if not client.is_live():
        return {"ok": False, "reason": "generation unavailable (set OPENAI_API_KEY)"}

    pack = client.complete_json(MUSIC_RELEASE_KIT.format(
        brand=brand.context(db), promo=music_brand.promo_context(db),
        title=release.title, era=release.era or "(new era)",
        story=release.story or "(write something true and cinematic)",
        city=release.city or " / ".join(music_brand.CITIES),
        language=release.language or "English with Spanish-flavored lyrics"))
    pack = pack if isinstance(pack, dict) else {}
    if not pack:
        return {"ok": False, "reason": "generation unavailable (set OPENAI_API_KEY)"}

    # Remove any prior pieces for this release so re-running is idempotent.
    rid = str(release.id)
    db.query(ContentItem).filter(
        ContentItem.business == "music",
        ContentItem.meta["release_id"].astext == rid).delete(synchronize_session=False)

    created = []
    for key, label, channel in DELIVERABLES:
        p = _piece(pack.get(key))
        if not p["body"] and not p["title"]:
            continue
        db.add(ContentItem(
            topic=f"{release.title} — {label}", business="music", channel=channel,
            title=p["title"] or label, body=p["body"], hashtags=p["hashtags"],
            status="ready",  # human-in-the-loop: review/produce, never auto-blasted
            meta={"release_id": rid, "deliverable": key, "era": release.era,
                  "song": release.title}))
        created.append(key)

    key_line = pack.get("key_line")
    if isinstance(key_line, str) and key_line.strip():
        release.key_line = key_line.strip()
    release.status = "Kit Built"
    db.commit()
    return {"ok": True, "release": release.title, "pieces": len(created),
            "deliverables": created, "key_line": release.key_line}


def pieces_for(db: Session, release_id) -> list[ContentItem]:
    return (db.query(ContentItem).filter(
        ContentItem.business == "music",
        ContentItem.meta["release_id"].astext == str(release_id))
        .order_by(ContentItem.created_at.asc()).all())


def run_due(db: Session, within_days: int = 28) -> dict:
    """Auto-build kits for upcoming planned releases (the 4-week cadence): any
    'Planned' release whose date is within ``within_days`` and has no kit yet."""
    horizon = date.today() + timedelta(days=within_days)
    rows = (db.query(MusicRelease).filter(
        MusicRelease.status == "Planned",
        MusicRelease.release_date.isnot(None),
        MusicRelease.release_date <= horizon).limit(10).all())
    built = []
    for r in rows:
        res = build_kit(db, r)
        if res.get("ok"):
            built.append({"release": r.title, "pieces": res["pieces"]})
    return {"built": len(built), "releases": built, "checked": len(rows)}
