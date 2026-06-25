"""Medium publishing via the official Medium API.

Publishes long-form articles (the Content Factory's "blog" pieces) to the
connected Medium account using a personal Integration Token (provider 'medium':
integration_token). Markdown in → a Medium post. Guarded throughout — degrades to
a clear reason, never raises.

Note: Medium issues Integration Tokens under Settings → Security and apps. If
your account can't generate one, blog pieces stay as drafts in the Content
Factory (assist).
"""
from __future__ import annotations

import logging

import httpx

from . import connectors

log = logging.getLogger("bruno.medium_api")
_TIMEOUT = httpx.Timeout(25.0, connect=5.0)
_BASE = "https://api.medium.com/v1"


def _creds(db) -> dict | None:
    c = connectors.get_credentials(db, "medium")
    if c and c.get("integration_token"):
        return c
    return None


def is_connected(db) -> bool:
    return _creds(db) is not None


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}",
            "Content-Type": "application/json", "Accept": "application/json"}


def _me(db) -> dict | None:
    """The authenticated Medium user (id, username) — cached creds, live call."""
    c = _creds(db)
    if not c:
        return None
    try:
        r = httpx.get(f"{_BASE}/me", headers=_headers(c["integration_token"]), timeout=_TIMEOUT)
        if r.status_code == 200:
            return (r.json() or {}).get("data") or {}
        log.warning("Medium /me -> %s: %s", r.status_code, r.text[:200])
        return None
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("Medium /me failed: %s", exc)
        return None


def verify(db) -> dict | None:
    """Confirm the token works — returns {username, name} or None."""
    me = _me(db)
    if not me:
        return None
    return {"username": me.get("username"), "name": me.get("name")}


def get_account(db) -> dict | None:
    return verify(db)


def post_article(db, title: str, markdown: str, tags: list[str] | None = None) -> dict:
    """Publish a markdown article to the connected Medium account."""
    c = _creds(db)
    if not c:
        return {"ok": False, "reason": "Medium not connected"}
    if not (title and markdown):
        return {"ok": False, "reason": "article needs a title and body"}
    me = _me(db)
    author_id = (me or {}).get("id")
    if not author_id:
        return {"ok": False, "reason": "integration token rejected"}
    payload = {
        "title": title[:100],
        "contentFormat": "markdown",
        "content": f"# {title}\n\n{markdown}",
        "tags": (tags or [])[:5],
        "publishStatus": (c.get("publish_status") or "draft").strip() or "draft",
    }
    try:
        r = httpx.post(f"{_BASE}/users/{author_id}/posts", json=payload,
                       headers=_headers(c["integration_token"]), timeout=_TIMEOUT)
        data = r.json() if r.content else {}
        if r.status_code in (200, 201):
            d = data.get("data") or {}
            return {"ok": True, "id": d.get("id"), "url": d.get("url")}
        return {"ok": False, "reason": (data.get("errors") or [{}])[0].get("message")
                or r.text[:200]}
    except Exception as exc:  # pragma: no cover - network guard
        return {"ok": False, "reason": str(exc)}
