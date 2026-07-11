"""Backup SMS provider — Plivo.

A Twilio-compatible carrier used as a drop-in fallback so texting keeps working if
Twilio is down or the account is deactivated. Same shape as ``integrations.sms``
(``send_with_error`` returns ``(id, error)``), so the SMS engine can route to
either without caring which. No-ops cleanly when unconfigured.

Send: POST https://api.plivo.com/v1/Account/{auth_id}/Message/ with HTTP Basic
auth (auth_id:auth_token) and JSON {src, dst, text}. A 200/202 returns a
message_uuid; anything else carries Plivo's real error so failures self-diagnose.
"""
from __future__ import annotations

import logging

import httpx

from ..config import settings

log = logging.getLogger("bruno.plivo")


def _auth_id() -> str:
    return (settings.plivo_auth_id or "").strip()


def _auth_token() -> str:
    return (settings.plivo_auth_token or "").strip()


def is_configured() -> bool:
    """Ready once we have the Auth ID, Auth Token and a sending number."""
    return bool(_auth_id() and _auth_token() and settings.plivo_from_number)


def send_with_error(to: str, body: str, account: str = "insurance") -> tuple[str | None, str | None]:
    """Send an SMS via Plivo. Returns (message_uuid, error_reason) — exactly one is
    non-None — mirroring integrations.sms.send_with_error so callers are provider-
    agnostic. `account` is accepted for signature parity (Plivo uses one number)."""
    if not is_configured():
        return None, "Plivo isn't connected — add Auth ID, Auth Token and a number in Setup."
    if not to:
        return None, "no recipient phone"
    if not body:
        return None, "empty message"
    src = (settings.plivo_from_number or "").strip()
    url = f"https://api.plivo.com/v1/Account/{_auth_id()}/Message/"
    payload = {"src": src, "dst": to, "text": body}
    # Delivery-status callback so the app learns delivered/failed, not just "queued".
    base = (settings.public_base_url or "").rstrip("/")
    if base:
        payload["url"] = f"{base}/sms/plivo-status"
        payload["method"] = "POST"
    try:
        resp = httpx.post(url, json=payload, auth=(_auth_id(), _auth_token()), timeout=20)
        if resp.status_code >= 400:
            try:
                j = resp.json()
                msg = j.get("error") or j.get("message") or str(j)[:160]
            except Exception:
                msg = (resp.text or "")[:160]
            hint = ""
            if resp.status_code == 401:
                hint = " (authentication failed — check the Plivo Auth ID / Auth Token for a stray space or a rotated token.)"
            return None, f"Plivo {resp.status_code}: {msg}{hint}"
        try:
            uuids = resp.json().get("message_uuid") or []
            mid = uuids[0] if uuids else None
        except Exception:
            mid = None
        return (mid or "plivo-sent"), None
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("Plivo send failed (%s): %s", to, exc)
        return None, f"Plivo error: {str(exc)[:160]}"


def send_sms(to: str, body: str, account: str = "insurance") -> str | None:
    """Send an SMS via Plivo. Returns the message id, or None if unconfigured/failed."""
    return send_with_error(to, body, account)[0]
