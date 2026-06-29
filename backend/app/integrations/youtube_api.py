"""YouTube publishing via the YouTube Data API v3.

Uploads videos (Shorts/clips produced by the video pipeline) to the connected
channel. Auth uses Google OAuth (provider 'youtube': client_id + client_secret +
refresh_token, or a stored access_token), and tokens auto-refresh. Guarded
throughout — degrades to a clear reason, never raises.

Note: until your Google OAuth app is verified, uploads are forced to 'private'
(set youtube_privacy_status to 'public' after verification).
"""
from __future__ import annotations

import json
import logging

import httpx

from ..config import settings
from . import connectors

log = logging.getLogger("bruno.youtube_api")
_TIMEOUT = httpx.Timeout(60.0, connect=5.0)
_API = "https://www.googleapis.com/youtube/v3"
_UPLOAD = "https://www.googleapis.com/upload/youtube/v3/videos"
_TOKEN = "https://oauth2.googleapis.com/token"


def _creds(db) -> dict | None:
    c = connectors.get_credentials(db, "youtube")
    if c and (c.get("access_token") or
              (c.get("refresh_token") and c.get("client_id") and c.get("client_secret"))):
        return c
    return None


def is_connected(db) -> bool:
    return _creds(db) is not None


def _access_token(db, c: dict) -> str | None:
    """Google access tokens expire ~hourly — refresh from the refresh token when
    we can (and persist), else use the stored access_token."""
    if c.get("refresh_token") and c.get("client_id") and c.get("client_secret"):
        try:
            r = httpx.post(_TOKEN, timeout=_TIMEOUT, data={
                "grant_type": "refresh_token", "refresh_token": c["refresh_token"],
                "client_id": c["client_id"], "client_secret": c["client_secret"]})
            tok = (r.json() or {}).get("access_token") if r.status_code == 200 else None
            if tok:
                connectors.update_credentials(db, "youtube", {**c, "access_token": tok})
                return tok
        except Exception as exc:  # pragma: no cover - network guard
            log.warning("YouTube token refresh failed: %s", exc)
    return c.get("access_token")


def verify(db) -> dict | None:
    """Confirm the token works (channels?mine=true). Returns channel title +
    subscriber count, or None."""
    c = _creds(db)
    if not c:
        return None
    token = _access_token(db, c)
    if not token:
        return None
    try:
        r = httpx.get(f"{_API}/channels", params={"part": "snippet,statistics", "mine": "true"},
                      headers={"Authorization": f"Bearer {token}"}, timeout=_TIMEOUT)
        if r.status_code != 200:
            log.warning("YouTube verify -> %s: %s", r.status_code, r.text[:200])
            return None
        items = (r.json() or {}).get("items") or []
        if not items:
            return None
        it = items[0]
        return {"title": (it.get("snippet") or {}).get("title"),
                "subscribers": (it.get("statistics") or {}).get("subscriberCount")}
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("YouTube verify failed: %s", exc)
        return None


def get_account(db) -> dict | None:
    return verify(db)


def post(db, caption: str, video_url: str | None = None) -> dict:
    """Upload a video to the connected channel (resumable upload from video_url)."""
    c = _creds(db)
    if not c:
        return {"ok": False, "reason": "YouTube not connected"}
    if not video_url:
        return {"ok": False, "reason": "YouTube needs a video — generate one via the "
                "video pipeline first"}
    token = _access_token(db, c)
    if not token:
        return {"ok": False, "reason": "token rejected (needs youtube.upload scope)"}
    title = (caption or "Untitled").strip().split("\n")[0][:95]
    meta = {"snippet": {"title": title, "description": (caption or "")[:4900]},
            "status": {"privacyStatus": settings.youtube_privacy_status,
                       "selfDeclaredMadeForKids": False}}
    try:
        # 1) Start a resumable session.
        start = httpx.post(_UPLOAD, params={"uploadType": "resumable", "part": "snippet,status"},
                           headers={"Authorization": f"Bearer {token}",
                                    "Content-Type": "application/json; charset=UTF-8"},
                           content=json.dumps(meta), timeout=_TIMEOUT)
        sess = start.headers.get("location") or start.headers.get("Location")
        if start.status_code not in (200, 201) or not sess:
            return {"ok": False, "reason": f"init failed: {start.text[:200]}"}
        # 2) Fetch the rendered clip and PUT the bytes.
        vid = httpx.get(video_url, timeout=_TIMEOUT)
        if vid.status_code != 200 or not vid.content:
            return {"ok": False, "reason": "could not fetch video_url"}
        up = httpx.put(sess, content=vid.content,
                       headers={"Authorization": f"Bearer {token}",
                                "Content-Type": "video/*"}, timeout=_TIMEOUT)
        data = up.json() if up.content else {}
        if up.status_code in (200, 201) and data.get("id"):
            return {"ok": True, "id": data["id"],
                    "url": f"https://youtu.be/{data['id']}"}
        return {"ok": False, "reason": (data.get("error") or {}).get("message") or up.text[:200]}
    except Exception as exc:  # pragma: no cover - network guard
        return {"ok": False, "reason": str(exc)}


def get_post_metrics(db, video_id: str) -> dict | None:
    """Public stats for a video (Data API v3 statistics). Normalized to
    {likes, comments, shares, views} or None — feeds the learning loop."""
    c = _creds(db)
    if not c or not video_id:
        return None
    token = _access_token(db, c)
    if not token:
        return None
    try:
        r = httpx.get(f"{_API}/videos", params={"part": "statistics", "id": video_id},
                      headers={"Authorization": f"Bearer {token}"}, timeout=_TIMEOUT)
        if r.status_code != 200:
            return None
        items = (r.json() or {}).get("items") or []
        if not items:
            return None
        s = items[0].get("statistics") or {}
        return {"likes": int(s.get("likeCount", 0) or 0), "comments": int(s.get("commentCount", 0) or 0),
                "shares": 0, "views": int(s.get("viewCount", 0) or 0)}
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("YouTube metrics failed: %s", exc)
        return None
