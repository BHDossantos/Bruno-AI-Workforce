"""AI video generation — pluggable provider (Luma Dream Machine / Runway).

Video gen is async (minutes), so this exposes create(prompt) -> job_id and
poll(job_id) -> url. A cron polls pending jobs and attaches the URL when ready.
No-ops without VIDEO_API_KEY. Add a provider by extending the dispatch tables.
"""
from __future__ import annotations

import logging

import httpx

from ..config import settings

log = logging.getLogger("bruno.video_gen")
_TIMEOUT = httpx.Timeout(30.0, connect=5.0)


def is_configured() -> bool:
    return bool(settings.video_api_key)


def _headers() -> dict:
    return {"authorization": f"Bearer {settings.video_api_key}", "content-type": "application/json"}


# ── Luma Dream Machine ───────────────────────────────────────────────────────
def _luma_create(prompt: str) -> str | None:
    r = httpx.post("https://api.lumalabs.ai/dream-machine/v1/generations",
                   headers=_headers(), json={"prompt": prompt[:1000]}, timeout=_TIMEOUT)
    return (r.json() or {}).get("id") if r.status_code in (200, 201) else None


def _luma_poll(job_id: str) -> tuple[str, str | None]:
    r = httpx.get(f"https://api.lumalabs.ai/dream-machine/v1/generations/{job_id}",
                  headers=_headers(), timeout=_TIMEOUT)
    if r.status_code != 200:
        return "pending", None
    d = r.json() or {}
    state = d.get("state")
    if state == "completed":
        return "completed", (d.get("assets") or {}).get("video")
    if state == "failed":
        return "failed", None
    return "pending", None


# ── Runway ───────────────────────────────────────────────────────────────────
def _runway_create(prompt: str) -> str | None:
    r = httpx.post("https://api.dev.runwayml.com/v1/text_to_video",
                   headers={**_headers(), "X-Runway-Version": "2024-11-06"},
                   json={"promptText": prompt[:1000], "model": "gen3a_turbo"}, timeout=_TIMEOUT)
    return (r.json() or {}).get("id") if r.status_code in (200, 201) else None


def _runway_poll(job_id: str) -> tuple[str, str | None]:
    r = httpx.get(f"https://api.dev.runwayml.com/v1/tasks/{job_id}",
                  headers={**_headers(), "X-Runway-Version": "2024-11-06"}, timeout=_TIMEOUT)
    if r.status_code != 200:
        return "pending", None
    d = r.json() or {}
    if d.get("status") == "SUCCEEDED":
        out = d.get("output") or []
        return "completed", (out[0] if out else None)
    if d.get("status") in ("FAILED", "CANCELLED"):
        return "failed", None
    return "pending", None


_CREATE = {"luma": _luma_create, "runway": _runway_create}
_POLL = {"luma": _luma_poll, "runway": _runway_poll}


def create(prompt: str) -> str | None:
    if not prompt or not is_configured():
        return None
    fn = _CREATE.get(settings.video_provider)
    if not fn:
        return None
    try:
        return fn(prompt)
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("video create failed (%s): %s", settings.video_provider, exc)
        return None


def poll(job_id: str) -> tuple[str, str | None]:
    if not job_id or not is_configured():
        return "pending", None
    fn = _POLL.get(settings.video_provider)
    if not fn:
        return "pending", None
    try:
        return fn(job_id)
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("video poll failed: %s", exc)
        return "pending", None
