"""Meta (Instagram/Facebook) token upgrade.

Short-lived Meta tokens last ~1-2 hours; long-lived ones last ~60 days and our
daily refresh cron keeps them alive after that. This upgrades whatever token gets
pasted on the Connections page to long-lived on connect, so a short-lived token
can never silently die. Needs a Meta app id + secret (from settings, or passed in
the credentials). Fully guarded: if it can't upgrade, it returns the creds
unchanged so connecting never breaks.
"""
from __future__ import annotations

import logging

import httpx

from ..config import settings

log = logging.getLogger("bruno.meta_tokens")
_TIMEOUT = httpx.Timeout(20.0, connect=5.0)
_GRAPH = "https://graph.facebook.com/v19.0"


def _app_creds(creds: dict) -> tuple[str, str]:
    app_id = creds.get("app_id") or settings.facebook_app_id
    app_secret = creds.get("app_secret") or settings.facebook_app_secret
    return app_id, app_secret


def _exchange(token: str, app_id: str, app_secret: str) -> str | None:
    """Short-lived → long-lived user token via fb_exchange_token."""
    try:
        r = httpx.get(f"{_GRAPH}/oauth/access_token", timeout=_TIMEOUT, params={
            "grant_type": "fb_exchange_token", "client_id": app_id,
            "client_secret": app_secret, "fb_exchange_token": token})
        if r.status_code == 200:
            return (r.json() or {}).get("access_token")
        log.warning("Meta token exchange -> %s: %s", r.status_code, r.text[:200])
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("Meta token exchange failed: %s", exc)
    return None


def _page_token(user_token: str, page_id: str | None) -> dict | None:
    """Resolve the long-lived PAGE token (and id/name) from a long-lived user token.
    Picks the page matching page_id if given, else the first managed page."""
    try:
        r = httpx.get(f"{_GRAPH}/me/accounts", timeout=_TIMEOUT,
                      params={"access_token": user_token})
        if r.status_code != 200:
            return None
        pages = (r.json() or {}).get("data") or []
        if not pages:
            return None
        chosen = next((p for p in pages if str(p.get("id")) == str(page_id)), pages[0])
        return {"access_token": chosen.get("access_token"), "id": chosen.get("id"),
                "name": chosen.get("name")}
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("Meta page-token lookup failed: %s", exc)
        return None


def upgrade(provider: str, creds: dict) -> dict:
    """Return creds with a long-lived token when possible; unchanged otherwise.
    - facebook: stores the long-lived PAGE token (+ page_id/name).
    - instagram: stores the long-lived user token (used with the IG business id).
    """
    if provider not in ("facebook", "instagram"):
        return creds
    token = creds.get("access_token")
    app_id, app_secret = _app_creds(creds)
    if not (token and app_id and app_secret):
        return creds  # nothing we can do without app credentials — keep as pasted

    long_user = _exchange(token, app_id, app_secret)
    if not long_user:
        return creds

    out = {**creds, "access_token": long_user, "token_type": "long_lived"}
    if provider == "facebook":
        page = _page_token(long_user, creds.get("page_id"))
        if page and page.get("access_token"):
            out["access_token"] = page["access_token"]
            out["page_id"] = page.get("id") or creds.get("page_id")
            if page.get("name"):
                out.setdefault("page_name", page["name"])
    log.info("Upgraded %s token to long-lived on connect", provider)
    return out
