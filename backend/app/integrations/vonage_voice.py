"""Voice via Vonage (Nexmo) — outbound auto-dial + bridge calling.

A third voice provider alongside twilio_voice and plivo_voice, selectable through
``voice_provider``. Same interface (``is_configured`` / ``place_auto_call`` /
``place_bridge_call`` / ``record_voicemail_call``) so the dispatcher routes to it.

Vonage differs from the others:
  • Auth: a short-lived **JWT (RS256)** signed with your Application private key +
    Application ID — not Basic auth.
  • Create call: POST https://api.nexmo.com/v1/calls with the JWT; phone numbers
    are E.164 **without** the leading '+'.
  • Call control is **NCCO** (a JSON array of actions), served from the
    /calls/vonage/* webhooks — not XML.

Uses the same producer voicemail/transfer settings, so behavior matches the other
providers. Transfer-to-cell honors ``auto_dial_transfer_enabled`` (default off →
leave the recorded voicemail). No-ops cleanly when unconfigured.
"""
from __future__ import annotations

import logging
import re
import time
import uuid
from urllib.parse import urlencode

import httpx
import jwt

from ..config import settings

log = logging.getLogger("bruno.vonage_voice")

_API = "https://api.nexmo.com/v1/calls"
_CONSENT = ("This call is with a licensed insurance producer and may be "
            "recorded for quality and training purposes.")


def _num(phone: str | None) -> str:
    """Vonage wants E.164 digits WITHOUT the '+': '+16039308272' → '16039308272'."""
    d = re.sub(r"\D", "", phone or "")
    if len(d) == 10:
        return "1" + d
    return d  # 11-digit already carries the country code


def _app_id() -> str:
    return (settings.vonage_application_id or "").strip()


def _private_key() -> str:
    return settings.vonage_private_key or ""


def _from_number() -> str:
    return _num(settings.vonage_voice_number or settings.vonage_from_number or "")


def _transfer_number() -> str:
    return _num(settings.producer_cell or settings.producer_callback)


def is_configured() -> bool:
    """Auto-dial/bridge calling: an Application ID + private key + a number + your callback."""
    return bool(_app_id() and _private_key().strip() and _from_number()
                and settings.producer_callback)


def voicemail_configured() -> bool:
    return bool(settings.producer_voicemail_url)


def _jwt() -> str:
    now = int(time.time())
    payload = {"application_id": _app_id(), "iat": now, "nbf": now,
               "exp": now + 60, "jti": uuid.uuid4().hex}
    return jwt.encode(payload, _private_key(), algorithm="RS256")


def _base_url() -> str:
    return (settings.public_base_url or "").rstrip("/")


def _amd_is_human(answered_by: str | None) -> bool:
    return (answered_by or "").strip().lower() in ("human", "", "unknown", "person")


def _vm_fallback_text() -> str:
    return (f"Hi, this is {settings.producer_name} with Thrust Insurance. I'm following up on the "
            "insurance quote you requested. Please give me a call back whenever you have a moment. "
            "Thank you and talk soon.")


# ── NCCO the webhooks return (JSON arrays) ────────────────────────────────────
def _voicemail_ncco() -> list:
    vm = settings.producer_voicemail_url
    if vm:
        return [{"action": "stream", "streamUrl": [vm]}]
    return [{"action": "talk", "text": _vm_fallback_text()}]


def amd_ncco(answered_by: str | None, lead_id: str | None) -> list:
    """Auto-dial answer: connect a live answer to the producer's cell when transfer
    is enabled, else leave the recorded voicemail for everyone."""
    if settings.auto_dial_transfer_enabled and _amd_is_human(answered_by):
        return [
            {"action": "talk",
             "text": "Please hold — connecting you with a licensed insurance producer. "
                     "This call may be recorded for quality."},
            {"action": "connect", "from": _from_number(),
             "endpoint": [{"type": "phone", "number": _transfer_number()}]},
        ]
    return _voicemail_ncco()


def bridge_ncco(lead_phone: str, lead_id: str | None) -> list:
    """After the producer answers a bridge call — consent notice, then dial the lead."""
    return [
        {"action": "talk", "text": _CONSENT},
        {"action": "connect", "from": _from_number(),
         "endpoint": [{"type": "phone", "number": _num(lead_phone)}]},
    ]


def record_vm_ncco() -> list:
    base = _base_url()
    return [
        {"action": "talk", "text": "Record the voicemail you want left for leads after the tone. "
                                   "Press the pound key when you are done."},
        {"action": "record", "endOnKey": "#", "timeOut": 60, "beepStart": True,
         "eventUrl": [f"{base}/calls/vonage/vm-saved"]},
    ]


# ── Placing calls (Vonage Voice API) ──────────────────────────────────────────
def _place(to: str, answer_path: str) -> tuple[str | None, str | None]:
    base = _base_url()
    if not base:
        return None, "PUBLIC_BASE_URL is not set, so Vonage can't reach the call webhooks."
    try:
        token = _jwt()
    except Exception as exc:  # bad/missing PEM
        return None, f"Vonage auth failed — check the private key is a full PEM: {str(exc)[:120]}"
    body = {
        "to": [{"type": "phone", "number": to}],
        "from": {"type": "phone", "number": _from_number()},
        "answer_url": [f"{base}{answer_path}"],
        "answer_method": "POST",
        "event_url": [f"{base}/calls/vonage/event"],
        "event_method": "POST",
    }
    try:
        r = httpx.post(_API, json=body, headers={"Authorization": f"Bearer {token}"}, timeout=20)
        if r.status_code >= 400:
            try:
                j = r.json()
                msg = j.get("title") or j.get("error_title") or j.get("error") or str(j)[:160]
            except Exception:
                msg = (r.text or "")[:160]
            hint = " (check the Application ID / private key)" if r.status_code in (401, 403) else ""
            return None, f"Vonage {r.status_code}: {msg}{hint}"
        try:
            cid = r.json().get("uuid")
        except Exception:
            cid = None
        return (cid or "vonage-call"), None
    except Exception as exc:  # pragma: no cover - network guard
        return None, f"Call failed: {str(exc)[:160]}"


def place_auto_call(lead_phone: str, lead_id: str | None) -> tuple[str | None, str | None]:
    if not is_configured():
        return None, "Vonage calling not connected — add Application ID, private key, a number + your callback."
    to = _num(lead_phone)
    if not to:
        return None, "lead has no valid phone number"
    q = urlencode({"lead_id": lead_id}) if lead_id else ""
    return _place(to, f"/calls/vonage/amd{('?' + q) if q else ''}")


def place_bridge_call(lead_phone: str, lead_id: str | None) -> tuple[str | None, str | None]:
    if not is_configured():
        return None, "Vonage calling not connected — add Application ID, private key, a number + your callback."
    if not _num(lead_phone):
        return None, "lead has no valid phone number"
    q = urlencode({k: v for k, v in {"lead_phone": _num(lead_phone), "lead_id": lead_id}.items() if v})
    return _place(_num(settings.producer_callback), f"/calls/vonage/bridge?{q}")


def record_voicemail_call() -> tuple[str | None, str | None]:
    if not is_configured():
        return None, "Add Vonage + your callback number on Setup first."
    return _place(_num(settings.producer_callback), "/calls/vonage/record-vm")
