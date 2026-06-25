"""TikTok publishing via the Content Posting API (Direct Post).

Publishes a video to the connected TikTok account using a user access token with
the ``video.publish`` scope (provider 'tiktok': access_token [+ open_id]). TikTok
is video-only, so ``post`` requires a hosted ``video_url`` (produced by the video
pipeline). Until the developer app passes TikTok's audit, posts are forced to the
account's private visibility (SELF_ONLY); set ``tiktok_privacy_level`` to a public
value once approved. Guarded throughout — degrades to a clear reason, never raises.
"""
from __future__ import annotations

import logging

import httpx

from ..config import settings
from . import connectors

log = logging.getLogger("bruno.tiktok_api")
_TIMEOUT = httpx.Timeout(30.0, connect=5.0)
_BASE = "https://open.tiktokapis.com/v2"


def _creds(db) -> dict | None:
    c = connectors.get_credentials(db, "tiktok")
    if c and c.get("access_token"):
        return c
    return None


def is_connected(db) -> bool:
    return _creds(db) is not None


def verify(db) -> dict | None:
    """Confirm the token works (GET /user/info/). Returns display name + follower
    count on success, None on failure — used by the connection tester."""
    c = _creds(db)
    if not c:
        return None
    try:
        r = httpx.get(f"{_BASE}/user/info/",
                      params={"fields": "open_id,display_name,follower_count"},
                      headers={"Authorization": f"Bearer {c['access_token']}"},
                      timeout=_TIMEOUT)
        if r.status_code == 200:
            d = ((r.json() or {}).get("data") or {}).get("user") or {}
            return {"display_name": d.get("display_name"),
                    "followers": d.get("follower_count")}
        log.warning("TikTok verify -> %s: %s", r.status_code, r.text[:200])
        return None
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("TikTok verify failed: %s", exc)
        return None


def get_account(db) -> dict | None:
    """Account snapshot for the dashboard (display name + followers)."""
    return verify(db)


def post(db, caption: str, video_url: str | None = None) -> dict:
    """Publish a video to TikTok via Direct Post (PULL_FROM_URL).

    Requires a publicly fetchable ``video_url`` whose domain is verified on the
    TikTok app. Returns {ok, publish_id} or {ok: False, reason}."""
    c = _creds(db)
    if not c:
        return {"ok": False, "reason": "TikTok not connected"}
    if not video_url:
        return {"ok": False, "reason": "TikTok needs a video — generate one via the "
                "video pipeline first (no image/text-only posts)"}
    payload = {
        "post_info": {
            "title": (caption or "")[:2200],
            "privacy_level": settings.tiktok_privacy_level,
            "disable_comment": False,
        },
        "source_info": {"source": "PULL_FROM_URL", "video_url": video_url},
    }
    try:
        r = httpx.post(f"{_BASE}/post/publish/video/init/", json=payload,
                       headers={"Authorization": f"Bearer {c['access_token']}",
                                "Content-Type": "application/json; charset=UTF-8"},
                       timeout=_TIMEOUT)
        data = r.json() if r.content else {}
        err = (data.get("error") or {})
        if r.status_code == 200 and err.get("code") in (None, "ok"):
            return {"ok": True, "publish_id": (data.get("data") or {}).get("publish_id")}
        return {"ok": False, "reason": err.get("message") or r.text[:200]}
    except Exception as exc:  # pragma: no cover - network guard
        return {"ok": False, "reason": str(exc)}
