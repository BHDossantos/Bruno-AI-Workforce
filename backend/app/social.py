"""Unified social publishing — one daily post fanned out to every connected
platform (Instagram, Facebook today; LinkedIn/X pluggable later).

The Influence Commander calls publish_daily() each cycle: it generates one image
(if hosting is configured), then posts to whichever platforms are connected.
Instagram requires an image; Facebook posts text even without one.
"""
from __future__ import annotations

import logging
from datetime import date

from . import media
from .integrations import (facebook_api, instagram_api, linkedin_api, tiktok_api,
                           twitter_api, youtube_api)

log = logging.getLogger("bruno.social")

# Platform → (connected_fn, publish_fn(db, caption, media_url), needs_image)
# media_url is an image URL for image platforms and a video URL for TikTok/YouTube.
PLATFORMS = {
    "instagram": (instagram_api.is_connected,
                  lambda db, cap, img: instagram_api.publish_post(db, img, cap), True),
    "facebook": (facebook_api.is_connected,
                 lambda db, cap, img: facebook_api.post(db, cap, img), False),
    "linkedin": (linkedin_api.is_connected,
                 lambda db, cap, img: linkedin_api.post(db, cap, img), False),
    "x": (twitter_api.is_connected,
          lambda db, cap, img: twitter_api.post(db, cap, img), False),
    "tiktok": (tiktok_api.is_connected,
               lambda db, cap, vid: tiktok_api.post(db, cap, vid), False),
    "youtube": (youtube_api.is_connected,
                lambda db, cap, vid: youtube_api.post(db, cap, vid), False),
}

# Channels that publish a video (need a produced clip, not an image/text).
VIDEO_CHANNELS = {"tiktok", "youtube"}


def connected_platforms(db) -> list[str]:
    return [k for k, (is_conn, _, _) in PLATFORMS.items() if is_conn(db)]


def publish_daily(db, caption: str, image_url: str | None = None) -> dict:
    """Post `caption` (+ an image) to every connected platform. Generates and
    hosts an image once when none is supplied and hosting is configured."""
    targets = connected_platforms(db)
    if not targets:
        return {"published": {}, "reason": "no social accounts connected"}

    # One image for all platforms (required by IG; nice-to-have for FB).
    if not image_url and media.can_generate():
        image_url = media.generate_and_host(caption, f"{date.today()}-social")

    results: dict[str, dict] = {}
    for name in targets:
        is_conn, publish, needs_image = PLATFORMS[name]
        if needs_image and not image_url:
            results[name] = {"ok": False, "reason": "no image available"}
            continue
        try:
            results[name] = publish(db, caption, image_url)
        except Exception as exc:  # one platform failing must not stop the others
            log.exception("social publish failed for %s", name)
            results[name] = {"ok": False, "reason": str(exc)}
    return {"published": results, "image_url": image_url}


def status(db) -> dict:
    """Connection + reach snapshot per platform for the dashboard."""
    out: dict[str, dict] = {}
    ig = instagram_api.get_account(db) if instagram_api.is_connected(db) else None
    out["instagram"] = {"connected": ig is not None, "followers": ig.get("followers") if ig else None}
    fb = facebook_api.get_page(db) if facebook_api.is_connected(db) else None
    out["facebook"] = {"connected": fb is not None, "followers": fb.get("followers") if fb else None}
    li = linkedin_api.get_profile(db) if linkedin_api.is_connected(db) else None
    out["linkedin"] = {"connected": li is not None, "followers": None}
    out["x"] = {"connected": twitter_api.is_connected(db), "followers": None}
    tk = tiktok_api.get_account(db) if tiktok_api.is_connected(db) else None
    out["tiktok"] = {"connected": tiktok_api.is_connected(db),
                     "followers": tk.get("followers") if tk else None}
    yt = youtube_api.get_account(db) if youtube_api.is_connected(db) else None
    out["youtube"] = {"connected": youtube_api.is_connected(db),
                      "followers": int(yt["subscribers"]) if yt and yt.get("subscribers") else None}
    return out


def snapshot(db) -> int:
    """Record current followers per connected platform (for growth charts)."""
    from .models import SocialSnapshot
    n = 0
    for plat, info in status(db).items():
        if info.get("connected"):
            db.add(SocialSnapshot(platform=plat, followers=info.get("followers")))
            n += 1
    if n:
        db.commit()
    return n


def history(db, platform: str | None = None, limit: int = 90) -> list[dict]:
    from .models import SocialSnapshot
    q = db.query(SocialSnapshot)
    if platform:
        q = q.filter(SocialSnapshot.platform == platform)
    rows = q.order_by(SocialSnapshot.captured_at.desc()).limit(limit).all()
    return [{"platform": r.platform, "followers": r.followers, "reach": r.reach,
             "captured_at": r.captured_at.isoformat() if r.captured_at else None} for r in rows]
