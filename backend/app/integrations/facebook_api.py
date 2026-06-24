"""Facebook Page publishing via the Meta Graph API.

Posts text or photo updates to a connected Facebook Page (provider 'facebook':
page_access_token + page_id). Guarded — returns None/ok:false on any failure.
"""
from __future__ import annotations

import logging

import httpx

from . import connectors

log = logging.getLogger("bruno.facebook_api")
_BASE = "https://graph.facebook.com/v21.0"
_TIMEOUT = httpx.Timeout(20.0, connect=5.0)


def _creds(db) -> dict | None:
    c = connectors.get_credentials(db, "facebook")
    if c and c.get("page_access_token") and c.get("page_id"):
        return c
    return None


def is_connected(db) -> bool:
    return _creds(db) is not None


def get_page(db) -> dict | None:
    c = _creds(db)
    if not c:
        return None
    try:
        r = httpx.get(f"{_BASE}/{c['page_id']}",
                      params={"fields": "name,fan_count,followers_count",
                              "access_token": c["page_access_token"]}, timeout=_TIMEOUT)
        if r.status_code != 200:
            return None
        d = r.json()
        return {"name": d.get("name"), "followers": d.get("followers_count") or d.get("fan_count")}
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("FB get_page failed: %s", exc)
        return None


def post(db, message: str, image_url: str | None = None) -> dict:
    """Publish a post to the Page. Text-only is allowed; an image is used when given."""
    c = _creds(db)
    if not c:
        return {"ok": False, "reason": "Facebook not connected"}
    try:
        if image_url:
            endpoint, params = f"{_BASE}/{c['page_id']}/photos", {
                "url": image_url, "caption": message or "", "access_token": c["page_access_token"]}
        else:
            endpoint, params = f"{_BASE}/{c['page_id']}/feed", {
                "message": message or "", "access_token": c["page_access_token"]}
        r = httpx.post(endpoint, params=params, timeout=_TIMEOUT)
        pid = (r.json() or {}).get("id") or (r.json() or {}).get("post_id")
        return {"ok": bool(pid), "id": pid} if pid else {"ok": False, "reason": r.text[:200]}
    except Exception as exc:  # pragma: no cover - network guard
        return {"ok": False, "reason": str(exc)}
