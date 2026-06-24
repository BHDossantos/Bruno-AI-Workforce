"""Instagram Graph API integration.

Pulls live account data (followers, media, insights) and publishes posts for a
connected IG Business/Creator account. Credentials come from the Connections
platform (provider 'instagram': access_token + ig_user_id) and are used at call
time. Every call is guarded — on any failure it returns None/empty so the
dashboard degrades to its planning view rather than erroring.
"""
from __future__ import annotations

import logging

import httpx

from . import connectors

log = logging.getLogger("bruno.instagram_api")
_BASE = "https://graph.facebook.com/v21.0"
_TIMEOUT = httpx.Timeout(20.0, connect=5.0)


def _creds(db) -> dict | None:
    c = connectors.get_credentials(db, "instagram")
    if c and c.get("access_token") and c.get("ig_user_id"):
        return c
    return None


def is_connected(db) -> bool:
    return _creds(db) is not None


def _get(path: str, token: str, **params) -> dict | None:
    params["access_token"] = token
    try:
        r = httpx.get(f"{_BASE}/{path}", params=params, timeout=_TIMEOUT)
        if r.status_code != 200:
            log.warning("IG API %s -> %s: %s", path, r.status_code, r.text[:200])
            return None
        return r.json()
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("IG API call failed %s: %s", path, exc)
        return None


def get_account(db) -> dict | None:
    """Account profile: username, followers, media count, bio, avatar."""
    c = _creds(db)
    if not c:
        return None
    data = _get(c["ig_user_id"], c["access_token"],
                fields="username,followers_count,follows_count,media_count,"
                       "biography,profile_picture_url,name")
    if not data:
        return None
    return {
        "username": data.get("username"), "name": data.get("name"),
        "followers": data.get("followers_count"), "follows": data.get("follows_count"),
        "media_count": data.get("media_count"), "biography": data.get("biography"),
        "profile_picture_url": data.get("profile_picture_url"),
    }


def get_recent_media(db, limit: int = 12) -> list[dict]:
    """Recent posts with engagement."""
    c = _creds(db)
    if not c:
        return []
    data = _get(f"{c['ig_user_id']}/media", c["access_token"],
                fields="caption,media_type,media_url,permalink,timestamp,"
                       "like_count,comments_count,thumbnail_url", limit=limit)
    return [
        {"caption": m.get("caption"), "type": m.get("media_type"),
         "permalink": m.get("permalink"), "timestamp": m.get("timestamp"),
         "likes": m.get("like_count"), "comments": m.get("comments_count"),
         "media_url": m.get("thumbnail_url") or m.get("media_url")}
        for m in (data or {}).get("data", [])
    ]


def get_insights(db) -> dict | None:
    """Account insights (reach, profile views) for the last day. Requires the
    instagram_manage_insights permission."""
    c = _creds(db)
    if not c:
        return None
    data = _get(f"{c['ig_user_id']}/insights", c["access_token"],
                metric="reach,profile_views,accounts_engaged", period="day")
    out: dict = {}
    for row in (data or {}).get("data", []):
        vals = row.get("values") or [{}]
        out[row.get("name")] = vals[-1].get("value")
    return out or None


def publish_post(db, image_url: str, caption: str) -> dict:
    """Publish a single image post (2-step: create container, then publish).
    Requires a publicly-reachable image_url and the instagram_content_publish
    permission (Meta app review)."""
    c = _creds(db)
    if not c:
        return {"ok": False, "reason": "Instagram not connected"}
    try:
        create = httpx.post(f"{_BASE}/{c['ig_user_id']}/media",
                            params={"image_url": image_url, "caption": caption or "",
                                    "access_token": c["access_token"]}, timeout=_TIMEOUT)
        cid = (create.json() or {}).get("id")
        if not cid:
            return {"ok": False, "reason": create.text[:200]}
        pub = httpx.post(f"{_BASE}/{c['ig_user_id']}/media_publish",
                        params={"creation_id": cid, "access_token": c["access_token"]},
                        timeout=_TIMEOUT)
        pid = (pub.json() or {}).get("id")
        return {"ok": bool(pid), "id": pid} if pid else {"ok": False, "reason": pub.text[:200]}
    except Exception as exc:  # pragma: no cover - network guard
        return {"ok": False, "reason": str(exc)}


def overview(db) -> dict:
    """One call for the dashboard: connection status + live account + recent media."""
    if not is_connected(db):
        return {"connected": False}
    acct = get_account(db)
    if not acct:
        return {"connected": True, "error": "Could not load account — check the token/permissions."}
    return {"connected": True, "account": acct,
            "insights": get_insights(db), "recent_media": get_recent_media(db, 8)}
