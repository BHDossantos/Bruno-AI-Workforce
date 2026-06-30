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
import urllib.parse

import httpx

from ..config import settings

log = logging.getLogger("bruno.meta_tokens")
_TIMEOUT = httpx.Timeout(20.0, connect=5.0)
_GRAPH = "https://graph.facebook.com/v19.0"
_DIALOG = "https://www.facebook.com/v19.0/dialog/oauth"
# Scopes for the one-click connect: read + publish to the Page and its linked
# Instagram business account (so both Facebook and Instagram connect at once).
_SCOPES = ("pages_show_list,pages_read_engagement,pages_manage_posts,"
           "business_management,instagram_basic,instagram_content_publish,"
           "instagram_manage_insights")


def _app_creds(creds: dict) -> tuple[str, str]:
    app_id = creds.get("app_id") or settings.facebook_app_id
    app_secret = creds.get("app_secret") or settings.facebook_app_secret
    return app_id, app_secret


# ── One-click OAuth (Facebook Login) ─────────────────────────────────────────
def oauth_configured() -> bool:
    """True when the in-app 'Connect with Facebook/Instagram' button can run."""
    return bool(settings.facebook_app_id and settings.facebook_app_secret
                and settings.meta_redirect_uri)


def build_auth_url(state: str) -> str:
    """The Facebook consent URL to send the user to for one-click connect."""
    params = {
        "client_id": settings.facebook_app_id,
        "redirect_uri": settings.meta_redirect_uri,
        "state": state,
        "response_type": "code",
        "scope": _SCOPES,
    }
    return f"{_DIALOG}?{urllib.parse.urlencode(params)}"


def _code_to_user_token(code: str) -> str | None:
    """Exchange an OAuth code for a (short-lived) user access token."""
    try:
        r = httpx.get(f"{_GRAPH}/oauth/access_token", timeout=_TIMEOUT, params={
            "client_id": settings.facebook_app_id,
            "client_secret": settings.facebook_app_secret,
            "redirect_uri": settings.meta_redirect_uri, "code": code})
        if r.status_code == 200:
            return (r.json() or {}).get("access_token")
        log.warning("Meta code exchange -> %s: %s", r.status_code, r.text[:200])
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("Meta code exchange failed: %s", exc)
    return None


def _ig_account(page_id: str, page_token: str) -> dict | None:
    """The Instagram business account linked to a Page (id + username), if any."""
    try:
        r = httpx.get(f"{_GRAPH}/{page_id}", timeout=_TIMEOUT, params={
            "fields": "instagram_business_account{id,username}", "access_token": page_token})
        if r.status_code != 200:
            return None
        iga = (r.json() or {}).get("instagram_business_account") or {}
        return iga or None
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("Meta IG-account lookup failed: %s", exc)
        return None


def connect_from_code(code: str) -> dict:
    """Full one-click connect: code → long-lived Page token + linked IG account.

    Returns {facebook: {...creds}, instagram: {...creds}} for the connections to
    store. Either key may be absent if that surface isn't available (e.g. no IG
    business account linked to the Page). Empty dict on failure."""
    user_token = _code_to_user_token(code)
    if not user_token:
        return {}
    long_user = _exchange(user_token, settings.facebook_app_id, settings.facebook_app_secret) or user_token
    page = _page_token(long_user, None)
    if not (page and page.get("access_token")):
        return {}
    out: dict = {"facebook": {
        "access_token": page["access_token"], "page_id": page.get("id"),
        "page_name": page.get("name"), "token_type": "long_lived"}}
    iga = _ig_account(page.get("id"), page["access_token"])
    if iga and iga.get("id"):
        # IG publishing uses the PAGE token together with the IG business id.
        out["instagram"] = {
            "access_token": page["access_token"], "ig_user_id": iga["id"],
            "username": iga.get("username"), "page_id": page.get("id"),
            "token_type": "long_lived"}
    log.info("Meta one-click connect resolved page=%s ig=%s",
             bool(out.get("facebook")), bool(out.get("instagram")))
    return out


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
