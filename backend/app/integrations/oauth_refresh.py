"""OAuth token auto-refresh — keeps connections alive with zero manual re-pasting.

Run daily via /cron/refresh-tokens. For each connected provider that supplies a
refresh token (+ client id/secret), this mints a fresh access token and saves it
back. Instagram long-lived tokens are extended in place. Everything is guarded —
a provider that can't refresh is simply skipped.
"""
from __future__ import annotations

import logging

import httpx

from . import connectors

log = logging.getLogger("bruno.oauth_refresh")
_TIMEOUT = httpx.Timeout(20.0, connect=5.0)


def _spotify(db, c: dict) -> str:
    if not (c.get("refresh_token") and c.get("client_id") and c.get("client_secret")):
        return "skip (no refresh token)"
    r = httpx.post("https://accounts.spotify.com/api/token", timeout=_TIMEOUT, data={
        "grant_type": "refresh_token", "refresh_token": c["refresh_token"],
        "client_id": c["client_id"], "client_secret": c["client_secret"]})
    tok = (r.json() or {}).get("access_token") if r.status_code == 200 else None
    if not tok:
        return f"error ({r.status_code})"
    connectors.update_credentials(db, "spotify", {**c, "access_token": tok})
    return "refreshed"


def _instagram(db, c: dict) -> str:
    """Extend the 60-day long-lived token (Instagram refreshes the same token)."""
    if not c.get("access_token"):
        return "skip"
    r = httpx.get("https://graph.instagram.com/refresh_access_token", timeout=_TIMEOUT,
                  params={"grant_type": "ig_refresh_token", "access_token": c["access_token"]})
    tok = (r.json() or {}).get("access_token") if r.status_code == 200 else None
    if not tok:
        return f"error ({r.status_code})"
    connectors.update_credentials(db, "instagram", {**c, "access_token": tok})
    return "extended"


def _refresh_grant(db, provider: str, c: dict, url: str) -> str:
    """Generic OAuth2 refresh_token grant (LinkedIn, X)."""
    if not (c.get("refresh_token") and c.get("client_id") and c.get("client_secret")):
        return "skip (no refresh token)"
    r = httpx.post(url, timeout=_TIMEOUT, data={
        "grant_type": "refresh_token", "refresh_token": c["refresh_token"],
        "client_id": c["client_id"], "client_secret": c["client_secret"]})
    body = r.json() if r.status_code == 200 else {}
    tok = body.get("access_token")
    if not tok:
        return f"error ({r.status_code})"
    new = {**c, "access_token": tok}
    if body.get("refresh_token"):
        new["refresh_token"] = body["refresh_token"]  # rotating refresh tokens
    connectors.update_credentials(db, provider, new)
    return "refreshed"


_PROVIDERS = {
    "spotify": lambda db, c: _spotify(db, c),
    "instagram": lambda db, c: _instagram(db, c),
    "linkedin": lambda db, c: _refresh_grant(db, "linkedin", c, "https://www.linkedin.com/oauth/v2/accessToken"),
    "x": lambda db, c: _refresh_grant(db, "x", c, "https://api.twitter.com/2/oauth2/token"),
}


def refresh_all(db) -> dict:
    out: dict[str, str] = {}
    for provider, fn in _PROVIDERS.items():
        c = connectors.get_credentials(db, provider)
        if not c:
            continue
        try:
            out[provider] = fn(db, c)
        except Exception as exc:  # never let one provider break the rest
            log.warning("refresh %s failed: %s", provider, exc)
            out[provider] = f"error ({exc})"
    return out
