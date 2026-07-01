"""WhatsApp via Meta's own Cloud API — no Twilio, no reseller markup.

Uses the same Facebook Developer app already connected for Facebook/Instagram.
Meta's own free tier covers a meaningful volume of conversations before any
per-conversation charge applies, and Meta's rate is cheaper than Twilio's resale
rate on top of it. Needs a WhatsApp-enabled phone number (added as a product in
the Meta app) + a permanent access token from Business Settings — configured
in-app on Setup, no redeploy.
"""
from __future__ import annotations

import logging

import httpx

from ..config import settings

log = logging.getLogger("bruno.whatsapp_cloud")
_TIMEOUT = httpx.Timeout(20.0, connect=5.0)
_GRAPH = "https://graph.facebook.com/v19.0"


def is_configured() -> bool:
    return bool(settings.whatsapp_cloud_phone_number_id and settings.whatsapp_cloud_token)


def send(to: str, body: str) -> str | None:
    """Send a WhatsApp text message. Returns the message id, or None if
    unconfigured/failed. `to` should be a phone number in E.164 (with or
    without the leading '+' — Meta accepts digits-only)."""
    if not is_configured() or not to or not body:
        return None
    to_digits = to.lstrip("+")
    url = f"{_GRAPH}/{settings.whatsapp_cloud_phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp", "to": to_digits,
        "type": "text", "text": {"body": body},
    }
    try:
        r = httpx.post(url, json=payload, timeout=_TIMEOUT,
                       headers={"Authorization": f"Bearer {settings.whatsapp_cloud_token}",
                                "Content-Type": "application/json"})
        if r.status_code != 200:
            log.warning("WhatsApp Cloud send -> %s: %s", r.status_code, r.text[:200])
            return None
        data = r.json() or {}
        msgs = data.get("messages") or []
        return msgs[0].get("id") if msgs else None
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("WhatsApp Cloud send failed (%s): %s", to, exc)
        return None


def verify() -> dict:
    """Check the phone number id + token work, via a lightweight GET."""
    if not is_configured():
        return {"ok": False, "reason": "not configured"}
    try:
        r = httpx.get(f"{_GRAPH}/{settings.whatsapp_cloud_phone_number_id}", timeout=_TIMEOUT,
                      params={"access_token": settings.whatsapp_cloud_token, "fields": "display_phone_number"})
        if r.status_code == 200:
            return {"ok": True, "reason": None,
                    "phone": (r.json() or {}).get("display_phone_number")}
        return {"ok": False, "reason": f"rejected ({r.status_code})"}
    except Exception as exc:  # pragma: no cover - network guard
        return {"ok": False, "reason": str(exc)[:120]}
