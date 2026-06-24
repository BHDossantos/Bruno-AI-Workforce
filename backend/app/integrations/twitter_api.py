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
