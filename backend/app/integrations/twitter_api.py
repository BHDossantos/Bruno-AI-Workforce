"""X (Twitter) posting via API v2.

Publishes text posts to your X account using an OAuth 2.0 user token with the
tweet.write scope (provider 'x': access_token). Text-only for now (media upload
is a separate v1.1 flow). Requires a paid X API tier. Guarded throughout.
"""
from __future__ import annotations

import logging

import httpx

from . import connectors

log = logging.getLogger("bruno.twitter_api")
_TIMEOUT = httpx.Timeout(20.0, connect=5.0)


def _creds(db) -> dict | None:
    c = connectors.get_credentials(db, "x")
    if c and c.get("access_token"):
        return c
    return None


def is_connected(db) -> bool:
    return _creds(db) is not None


def verify(db) -> dict | None:
    """Confirm the token actually works (GET /2/users/me). Returns the account
    handle on success, None on failure — used by the connection tester."""
    c = _creds(db)
    if not c:
        return None
    try:
        r = httpx.get("https://api.twitter.com/2/users/me",
                      headers={"Authorization": f"Bearer {c['access_token']}"},
                      timeout=_TIMEOUT)
        if r.status_code == 200:
            d = (r.json() or {}).get("data") or {}
            return {"username": d.get("username"), "name": d.get("name")}
        log.warning("X verify -> %s: %s", r.status_code, r.text[:200])
        return None
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("X verify failed: %s", exc)
        return None


def post(db, message: str, image_url: str | None = None) -> dict:
    """Publish a tweet (text). image_url is ignored for now."""
    c = _creds(db)
    if not c:
        return {"ok": False, "reason": "X not connected"}
    try:
        r = httpx.post("https://api.twitter.com/2/tweets",
                       json={"text": (message or "")[:280]},
                       headers={"Authorization": f"Bearer {c['access_token']}",
                                "Content-Type": "application/json"}, timeout=_TIMEOUT)
        if r.status_code in (200, 201):
            return {"ok": True, "id": (r.json().get("data") or {}).get("id")}
        return {"ok": False, "reason": r.text[:200]}
    except Exception as exc:  # pragma: no cover - network guard
        return {"ok": False, "reason": str(exc)}


def get_post_metrics(db, tweet_id: str) -> dict | None:
    """Public engagement for a tweet (API v2 public_metrics). Normalized to
    {likes, comments, shares, views} or None — feeds the learning loop."""
    c = _creds(db)
    if not c or not tweet_id:
        return None
    try:
        r = httpx.get(f"https://api.twitter.com/2/tweets/{tweet_id}",
                      params={"tweet.fields": "public_metrics"},
                      headers={"Authorization": f"Bearer {c['access_token']}"}, timeout=_TIMEOUT)
        if r.status_code != 200:
            return None
        pm = ((r.json() or {}).get("data") or {}).get("public_metrics") or {}
        return {"likes": pm.get("like_count", 0), "comments": pm.get("reply_count", 0),
                "shares": (pm.get("retweet_count", 0) + pm.get("quote_count", 0)),
                "views": pm.get("impression_count", 0)}
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("X metrics failed: %s", exc)
        return None
