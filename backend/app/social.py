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
from .integrations import facebook_api, instagram_api

log = logging.getLogger("bruno.social")

# Platform → (connected_fn, publish_fn(db, caption, image_url), needs_image)
PLATFORMS = {
    "instagram": (instagram_api.is_connected,
                  lambda db, cap, img: instagram_api.publish_post(db, img, cap), True),
    "facebook": (facebook_api.is_connected,
                 lambda db, cap, img: facebook_api.post(db, cap, img), False),
}


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
    return out
