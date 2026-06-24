"""LinkedIn posting via the official API.

Auto-publishes YOUR OWN posts to a member profile or organization page using an
OAuth token (w_member_social / w_organization_social) and the author's URN.
Text posts only for now (LinkedIn allows text-only); images require the asset
register+upload flow and can be added later. Guarded — ok:false on any failure.

LinkedIn's ToS forbids automated connections/DMs — this module only publishes
your own posts, which is permitted.
"""
from __future__ import annotations

import logging

import httpx

from . import connectors

log = logging.getLogger("bruno.linkedin_api")
_BASE = "https://api.linkedin.com/v2"
_TIMEOUT = httpx.Timeout(20.0, connect=5.0)


def _creds(db) -> dict | None:
    c = connectors.get_credentials(db, "linkedin")
    if c and c.get("access_token") and c.get("author_urn"):
        return c
    return None


def is_connected(db) -> bool:
    return _creds(db) is not None


def get_profile(db) -> dict | None:
    c = _creds(db)
    if not c:
        return None
    try:
        r = httpx.get(f"{_BASE}/userinfo",
                      headers={"Authorization": f"Bearer {c['access_token']}"}, timeout=_TIMEOUT)
        if r.status_code != 200:
            return None
        d = r.json()
        return {"name": d.get("name"), "urn": c["author_urn"]}
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("LinkedIn get_profile failed: %s", exc)
        return None


def _upload_image(c: dict, image_url: str) -> str | None:
    """Register + upload an image to LinkedIn (it needs an owned asset, not an
    external URL); return the asset URN or None."""
    try:
        reg = httpx.post(f"{_BASE}/assets?action=registerUpload", timeout=_TIMEOUT,
                         headers={"Authorization": f"Bearer {c['access_token']}",
                                  "Content-Type": "application/json"},
                         json={"registerUploadRequest": {
                             "owner": c["author_urn"],
                             "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
                             "serviceRelationships": [{
                                 "relationshipType": "OWNER",
                                 "identifier": "urn:li:userGeneratedContent"}]}})
        v = (reg.json() or {}).get("value") or {}
        asset = v.get("asset")
        upload_url = (((v.get("uploadMechanism") or {})
                      .get("com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest") or {})
                      .get("uploadUrl"))
        if not asset or not upload_url:
            return None
        img = httpx.get(image_url, timeout=30.0)
        if img.status_code != 200:
            return None
        up = httpx.put(upload_url, content=img.content, timeout=60.0,
                       headers={"Authorization": f"Bearer {c['access_token']}"})
        return asset if up.status_code in (200, 201) else None
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("LinkedIn image upload failed: %s", exc)
        return None


def post(db, message: str, image_url: str | None = None) -> dict:
    """Publish a share to the member/organization feed (image when provided)."""
    c = _creds(db)
    if not c:
        return {"ok": False, "reason": "LinkedIn not connected"}
    content: dict = {"shareCommentary": {"text": message or ""}, "shareMediaCategory": "NONE"}
    if image_url:
        asset = _upload_image(c, image_url)
        if asset:
            content["shareMediaCategory"] = "IMAGE"
            content["media"] = [{"status": "READY", "media": asset}]
    payload = {
        "author": c["author_urn"], "lifecycleState": "PUBLISHED",
        "specificContent": {"com.linkedin.ugc.ShareContent": content},
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }
    try:
        r = httpx.post(f"{_BASE}/ugcPosts", json=payload, timeout=_TIMEOUT, headers={
            "Authorization": f"Bearer {c['access_token']}",
            "X-Restli-Protocol-Version": "2.0.0", "Content-Type": "application/json"})
        if r.status_code in (200, 201):
            return {"ok": True, "id": r.json().get("id") or r.headers.get("x-restli-id")}
        return {"ok": False, "reason": r.text[:200]}
    except Exception as exc:  # pragma: no cover - network guard
        return {"ok": False, "reason": str(exc)}
