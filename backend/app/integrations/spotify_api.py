"""Spotify Web API (read-only) for the Music dashboard.

Pulls your artist profile, follower count, and top tracks (provider 'spotify':
access_token + artist_id). Spotify has no API to upload/post music, so this is
analytics only. Guarded throughout.
"""
from __future__ import annotations

import logging

import httpx

from . import connectors

log = logging.getLogger("bruno.spotify_api")
_BASE = "https://api.spotify.com/v1"
_TIMEOUT = httpx.Timeout(20.0, connect=5.0)


def _creds(db) -> dict | None:
    c = connectors.get_credentials(db, "spotify")
    if c and c.get("access_token") and c.get("artist_id"):
        return c
    return None


def is_connected(db) -> bool:
    return _creds(db) is not None


def _access_token(db, c: dict) -> str:
    """Spotify access tokens expire hourly — mint a fresh one from the refresh
    token when we have one, and persist it; otherwise use the stored token."""
    if not (c.get("refresh_token") and c.get("client_id") and c.get("client_secret")):
        return c["access_token"]
    try:
        r = httpx.post("https://accounts.spotify.com/api/token", timeout=_TIMEOUT, data={
            "grant_type": "refresh_token", "refresh_token": c["refresh_token"],
            "client_id": c["client_id"], "client_secret": c["client_secret"]})
        tok = (r.json() or {}).get("access_token") if r.status_code == 200 else None
        if tok:
            connectors.update_credentials(db, "spotify", {**c, "access_token": tok})
            return tok
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("Spotify token refresh failed: %s", exc)
    return c["access_token"]


def _get(path: str, token: str, **params) -> dict | None:
    try:
        r = httpx.get(f"{_BASE}/{path}", params=params or None,
                      headers={"Authorization": f"Bearer {token}"}, timeout=_TIMEOUT)
        return r.json() if r.status_code == 200 else None
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("Spotify API %s failed: %s", path, exc)
        return None


def overview(db) -> dict:
    c = _creds(db)
    if not c:
        return {"connected": False}
    token = _access_token(db, c)
    artist = _get(f"artists/{c['artist_id']}", token)
    if not artist:
        return {"connected": True, "error": "Could not load artist — check the token."}
    tracks = _get(f"artists/{c['artist_id']}/top-tracks", token, market="US") or {}
    return {
        "connected": True,
        "name": artist.get("name"),
        "followers": (artist.get("followers") or {}).get("total"),
        "popularity": artist.get("popularity"),
        "genres": artist.get("genres", []),
        "top_tracks": [{"name": t.get("name"), "popularity": t.get("popularity"),
                        "url": (t.get("external_urls") or {}).get("spotify")}
                       for t in tracks.get("tracks", [])[:10]],
    }
