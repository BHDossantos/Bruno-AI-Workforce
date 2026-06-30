"""Instantly.ai integration — hand cold outreach off to Instantly campaigns.

Instantly solves the hard part of cold email at scale that a personal Gmail can't:
many warmed sending inboxes across dedicated domains, deliverability/warmup, and
multi-step sequences. When an Instantly API key + campaign are configured, the app
pushes each lead into the Instantly campaign (which then sends + follows up + warms
on its own) instead of sending through a fragile Gmail App Password that Google
revokes at volume.

Key-gated: every function is a safe no-op when not configured, so the existing
Gmail path is completely unchanged until the user connects Instantly.

API: https://developer.instantly.ai  (v2, Bearer auth).
"""
from __future__ import annotations

import logging

import httpx

from ..config import settings

log = logging.getLogger("bruno.instantly")
_BASE = "https://api.instantly.ai/api/v2"


def is_configured() -> bool:
    """True only when we can actually hand a lead to a specific campaign."""
    return bool(settings.instantly_api_key and settings.instantly_campaign_id)


def has_key() -> bool:
    return bool(settings.instantly_api_key)


def _headers() -> dict:
    return {"Authorization": f"Bearer {settings.instantly_api_key}",
            "Content-Type": "application/json"}


def add_lead(email: str, *, first_name: str | None = None, last_name: str | None = None,
             company_name: str | None = None, website: str | None = None,
             phone: str | None = None, personalization: str | None = None,
             campaign_id: str | None = None) -> bool:
    """Add ONE lead to the configured Instantly campaign. Returns True on success.

    ``personalization`` carries our AI-written body — reference it in the Instantly
    campaign's email step as {{personalization}} to send our copy."""
    if not is_configured() or not email:
        return False
    lead: dict = {"email": email}
    if first_name:
        lead["first_name"] = first_name
    if last_name:
        lead["last_name"] = last_name
    if company_name:
        lead["company_name"] = company_name
    if website:
        lead["website"] = website
    if phone:
        lead["phone"] = phone
    if personalization:
        lead["personalization"] = personalization
    body = {"campaign_id": campaign_id or settings.instantly_campaign_id, "leads": [lead]}
    try:
        r = httpx.post(f"{_BASE}/leads/add", json=body, headers=_headers(), timeout=30)
        r.raise_for_status()
        return True
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("Instantly add_lead failed (%s): %s", email, exc)
        return False


def list_campaigns() -> list[dict]:
    """Return the workspace's campaigns ([{id, name}, ...]) so the user can pick one."""
    if not has_key():
        return []
    try:
        r = httpx.get(f"{_BASE}/campaigns", headers=_headers(), timeout=30)
        r.raise_for_status()
        data = r.json()
        items = data.get("items", data) if isinstance(data, dict) else data
        out = []
        for c in items or []:
            cid = c.get("id") or c.get("campaign_id")
            if cid:
                out.append({"id": cid, "name": c.get("name") or cid})
        return out
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("Instantly list_campaigns failed: %s", exc)
        return []


def verify() -> dict:
    """Lightweight check that the API key works (lists campaigns). For the Connect page."""
    if not has_key():
        return {"ok": False, "reason": "no API key"}
    try:
        r = httpx.get(f"{_BASE}/campaigns", headers=_headers(), timeout=20)
        r.raise_for_status()
        return {"ok": True, "reason": None}
    except Exception as exc:  # pragma: no cover - network guard
        return {"ok": False, "reason": f"{str(exc)[:100]}"}
