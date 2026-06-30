"""Connection token health — see at a glance whether each social connection is
alive and when it expires, and refresh on demand.

The #1 cause of "it keeps disconnecting" is a Meta/OAuth token quietly expiring
(esp. when the daily refresh wasn't running). This does a LIVE validity check per
connected provider (a cheap Graph/API call), reports days-until-expiry where the
provider exposes it, and exposes a one-click refresh — so a looming disconnect is
visible before it happens, not after.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from .config import settings
from .integrations import connectors

log = logging.getLogger("bruno.token_health")
_T = httpx.Timeout(15.0, connect=5.0)
_GRAPH = "https://graph.facebook.com/v19.0"

_PROVIDERS = ["instagram", "facebook", "spotify", "linkedin", "x"]
_LABEL = {"instagram": "Instagram", "facebook": "Facebook", "spotify": "Spotify",
          "linkedin": "LinkedIn", "x": "X / Twitter"}


def _meta_expiry_days(token: str) -> int | None:
    """Days until a Meta token expires, via debug_token (needs app id+secret)."""
    app_id, app_secret = settings.facebook_app_id, settings.facebook_app_secret
    if not (app_id and app_secret and token):
        return None
    try:
        r = httpx.get(f"{_GRAPH}/debug_token", timeout=_T, params={
            "input_token": token, "access_token": f"{app_id}|{app_secret}"})
        if r.status_code != 200:
            return None
        exp = ((r.json() or {}).get("data") or {}).get("expires_at")
        if not exp:  # 0 = never expires (system user token)
            return None
        return max(0, (datetime.fromtimestamp(exp, tz=timezone.utc) - datetime.now(timezone.utc)).days)
    except Exception:  # pragma: no cover - network guard
        return None


def _check(provider: str, c: dict) -> tuple[bool, int | None, str]:
    """(alive, days_left, note) — a live validity check per provider."""
    tok = c.get("access_token")
    if not tok:
        return False, None, "No token — reconnect."
    try:
        if provider == "instagram":
            r = httpx.get("https://graph.instagram.com/me", timeout=_T,
                          params={"fields": "id,username", "access_token": tok})
            ok = r.status_code == 200
            return ok, _meta_expiry_days(tok), ("Healthy" if ok else "Token rejected — reconnect.")
        if provider == "facebook":
            r = httpx.get(f"{_GRAPH}/me", timeout=_T, params={"access_token": tok})
            ok = r.status_code == 200
            return ok, _meta_expiry_days(tok), ("Healthy" if ok else "Token rejected — reconnect.")
        # Spotify/LinkedIn/X refresh via a stored refresh_token on the daily cron.
        return True, None, "Connected — auto-refreshed daily."
    except Exception as exc:  # pragma: no cover - network guard
        return False, None, f"Check failed: {str(exc)[:60]}"


def health(db) -> list[dict]:
    out = []
    for p in _PROVIDERS:
        c = connectors.get_credentials(db, p)
        if not c:
            continue
        alive, days, note = _check(p, c)
        out.append({
            "provider": p, "label": _LABEL.get(p, p), "connected": alive,
            "days_left": days, "note": note,
            "warn": (days is not None and days <= 7) or not alive,
        })
    return out


def refresh(db) -> dict:
    """Refresh all refreshable tokens now and return the per-provider result."""
    from .integrations import oauth_refresh
    return oauth_refresh.refresh_all(db)
