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
    # Need an artist + a way to authenticate: either client_id/secret (preferred,
    # auto-refreshing) or a stored access_token.
    if c and c.get("artist_id") and (
            c.get("access_token") or (c.get("client_id") and c.get("client_secret"))):
        return c
    return None


def is_connected(db) -> bool:
    return _creds(db) is not None


def _access_token(db, c: dict) -> str | None:
    """Spotify access tokens expire hourly. Mint a fresh one and persist it:
    via refresh-token grant if we have one, else via client-credentials (enough
    for public artist analytics); fall back to any stored token."""
    cid, csec = c.get("client_id"), c.get("client_secret")
    if c.get("refresh_token") and cid and csec:
        data = {"grant_type": "refresh_token", "refresh_token": c["refresh_token"],
                "client_id": cid, "client_secret": csec}
    elif cid and csec:
        data = {"grant_type": "client_credentials", "client_id": cid, "client_secret": csec}
    else:
        return c.get("access_token")
    try:
        r = httpx.post("https://accounts.spotify.com/api/token", timeout=_TIMEOUT, data=data)
        tok = (r.json() or {}).get("access_token") if r.status_code == 200 else None
        if tok:
            connectors.update_credentials(db, "spotify", {**c, "access_token": tok})
            return tok
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("Spotify token mint failed: %s", exc)
    return c.get("access_token")


def _get(path: str, token: str, **params) -> dict | None:
    try:
        r = httpx.get(f"{_BASE}/{path}", params=params or None,
                      headers={"Authorization": f"Bearer {token}"}, timeout=_TIMEOUT)
        return r.json() if r.status_code == 200 else None
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("Spotify API %s failed: %s", path, exc)
        return None


def _search_token(db) -> str | None:
    """A token for public search — only needs client_id/secret (or a stored
    access_token); the artist_id requirement doesn't apply to discovery."""
    c = connectors.get_credentials(db, "spotify")
    if not c:
        return None
    if c.get("client_id") and c.get("client_secret"):
        return _access_token(db, c)
    return c.get("access_token")


def discover_playlists(db, genres, limit: int = 50) -> list[dict]:
    """Find REAL public playlists to pitch, by genre, via the Spotify Search API.
    Returns dicts shaped like the synthetic provider (name/curator/genre/
    submission_link/email/instagram/followers). Spotify exposes no curator email,
    so email is None — these are pitched via their submission link (manual), but
    they're real, on-brand targets instead of fabricated ones. [] if not connected."""
    token = _search_token(db)
    if not token:
        return []
    terms = [g.strip() for g in (genres or []) if g and g.strip()][:6]
    out: list[dict] = []
    seen: set[str] = set()
    for g in terms:
        data = _get("search", token, q=g, type="playlist", limit=20, market="US")
        items = ((data or {}).get("playlists") or {}).get("items") or []
        for p in items:
            pid = p.get("id")
            if not pid or pid in seen or not p.get("name"):
                continue
            seen.add(pid)
            out.append({
                "name": p.get("name"),
                "curator_name": (p.get("owner") or {}).get("display_name") or "Curator",
                "genre": g,
                "submission_link": (p.get("external_urls") or {}).get("spotify"),
                "email": None, "instagram": None,
                "followers": int((p.get("followers") or {}).get("total") or 0),
            })
            if len(out) >= limit:
                return out
    return out


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
