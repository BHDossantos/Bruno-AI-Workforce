"""Smartlead.ai integration — hand cold outreach off to Smartlead campaigns.

Like Instantly, Smartlead runs cold email at scale across many warmed inboxes with
deliverability + sequences. When a Smartlead API key + campaign are configured, the
app pushes leads into the Smartlead campaign instead of sending through a personal
Gmail. Key-gated: a safe no-op when not configured.

API: https://api.smartlead.ai  (v1, api_key as a query param).
"""
from __future__ import annotations

import logging

import httpx

from ..config import settings

log = logging.getLogger("bruno.smartlead")
_BASE = "https://server.smartlead.ai/api/v1"


def is_configured() -> bool:
    return bool(settings.smartlead_api_key and settings.smartlead_campaign_id)


def has_key() -> bool:
    return bool(settings.smartlead_api_key)


def _params() -> dict:
    return {"api_key": settings.smartlead_api_key}


def add_lead(email: str, *, first_name: str | None = None, last_name: str | None = None,
             company_name: str | None = None, website: str | None = None,
             phone: str | None = None, personalization: str | None = None,
             campaign_id: str | None = None) -> bool:
    """Add ONE lead to the configured Smartlead campaign. Returns True on success.
    ``personalization`` is passed as a custom field; reference it in the Smartlead
    campaign template to send our AI-written copy."""
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
        lead["phone_number"] = phone
    if personalization:
        lead["custom_fields"] = {"personalization": personalization}
    cid = campaign_id or settings.smartlead_campaign_id
    try:
        r = httpx.post(f"{_BASE}/campaigns/{cid}/leads", params=_params(),
                       json={"lead_list": [lead]}, timeout=30)
        r.raise_for_status()
        return True
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("Smartlead add_lead failed (%s): %s", email, exc)
        return False


def list_campaigns() -> list[dict]:
    if not has_key():
        return []
    try:
        r = httpx.get(f"{_BASE}/campaigns", params=_params(), timeout=30)
        r.raise_for_status()
        data = r.json()
        items = data if isinstance(data, list) else data.get("data", [])
        return [{"id": c.get("id"), "name": c.get("name") or str(c.get("id"))}
                for c in items if c.get("id")]
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("Smartlead list_campaigns failed: %s", exc)
        return []


def verify() -> dict:
    if not has_key():
        return {"ok": False, "reason": "no API key"}
    try:
        r = httpx.get(f"{_BASE}/campaigns", params=_params(), timeout=20)
        r.raise_for_status()
        return {"ok": True, "reason": None}
    except Exception as exc:  # pragma: no cover - network guard
        return {"ok": False, "reason": f"{str(exc)[:100]}"}
