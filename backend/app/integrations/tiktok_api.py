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
import urllib.parse

import httpx

from ..config import settings
from . import connectors

log = logging.getLogger("bruno.tiktok_api")
_TIMEOUT = httpx.Timeout(30.0, connect=5.0)
_BASE = "https://open.tiktokapis.com/v2"
_AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
_SCOPES = "user.info.basic,video.publish,video.upload"


# ── Login Kit (OAuth) ──────────────────────────────────────────────────────────
def oauth_configured() -> bool:
    return bool(settings.tiktok_client_key and settings.tiktok_client_secret
                and settings.tiktok_redirect_uri)


def build_auth_url(state: str) -> str:
    """The TikTok consent URL to send the user to (Login Kit)."""
    params = {
        "client_key": settings.tiktok_client_key,
        "scope": _SCOPES,
        "response_type": "code",
        "redirect_uri": settings.tiktok_redirect_uri,
        "state": state,
    }
    return f"{_AUTH_URL}?{urllib.parse.urlencode(params)}"


def exchange_code(code: str) -> dict | None:
    """Exchange an authorization code for tokens. Returns the creds dict to store
    (access_token, refresh_token, open_id, scope) or None on failure."""
    try:
        r = httpx.post(f"{_BASE}/oauth/token/",
                       data={"client_key": settings.tiktok_client_key,
                             "client_secret": settings.tiktok_client_secret,
                             "code": code, "grant_type": "authorization_code",
                             "redirect_uri": settings.tiktok_redirect_uri},
                       headers={"Content-Type": "application/x-www-form-urlencoded"},
                       timeout=_TIMEOUT)
        d = r.json() if r.content else {}
        if r.status_code == 200 and d.get("access_token"):
            return {"access_token": d["access_token"],
                    "refresh_token": d.get("refresh_token"),
                    "open_id": d.get("open_id"), "scope": d.get("scope")}
        log.warning("TikTok token exchange -> %s: %s", r.status_code, r.text[:200])
        return None
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("TikTok token exchange failed: %s", exc)
        return None


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


def get_post_metrics(db, video_id: str) -> dict | None:
    """Public engagement for a TikTok video (Video Query API). Normalized to
    {likes, comments, shares, views} or None — feeds the learning loop. Requires
    the video.list scope; degrades safely when unavailable."""
    c = _creds(db)
    if not c or not video_id:
        return None
    try:
        r = httpx.post(
            f"{_BASE}/video/query/",
            params={"fields": "like_count,comment_count,share_count,view_count"},
            json={"filters": {"video_ids": [video_id]}},
            headers={"Authorization": f"Bearer {c['access_token']}",
                     "Content-Type": "application/json"}, timeout=_TIMEOUT)
        if r.status_code != 200:
            return None
        vids = ((r.json() or {}).get("data") or {}).get("videos") or []
        if not vids:
            return None
        v = vids[0]
        return {"likes": int(v.get("like_count", 0) or 0),
                "comments": int(v.get("comment_count", 0) or 0),
                "shares": int(v.get("share_count", 0) or 0),
                "views": int(v.get("view_count", 0) or 0)}
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("TikTok metrics failed: %s", exc)
        return None
