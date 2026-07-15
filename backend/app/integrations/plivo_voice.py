"""Voice via Plivo — outbound auto-dial + bridge calling.

A second voice provider alongside twilio_voice, for when the Twilio-compatible
number's carrier reputation is filtering calls to voicemail. Same shape as
twilio_voice (``is_configured`` / ``place_auto_call`` / ``place_bridge_call`` /
``voicemail_configured``) so the auto-dialer + Call button can route to either.

Plivo differs from Twilio in two ways this module bridges:
  • Outbound call: POST https://api.plivo.com/v1/Account/{auth_id}/Call/ with
    Basic auth and JSON {from, to, answer_url, machine_detection, …}. It returns
    a request_uuid (not a call SID up front).
  • Call control is **Plivo XML** (<Response><Speak>/<Play>/<Dial>/<Record>),
    served from the /calls/plivo/* webhooks — not TwiML.

Uses the same producer voicemail/transfer settings, so the recorded drop and the
transfer-to-cell behave identically. No-ops cleanly when unconfigured.
"""
from __future__ import annotations

import logging
import re
from urllib.parse import urlencode

import httpx

from ..config import settings

log = logging.getLogger("bruno.plivo_voice")

_CONSENT = ("This call is with a licensed insurance producer and may be "
            "recorded for quality and training purposes.")


def _e164(phone: str | None) -> str:
    """Normalize a US phone to E.164 (+1XXXXXXXXXX)."""
    d = re.sub(r"\D", "", phone or "")
    if len(d) == 11 and d.startswith("1"):
        return "+" + d
    if len(d) == 10:
        return "+1" + d
    return ("+" + d) if d else ""


def _auth_id() -> str:
    return (settings.plivo_auth_id or "").strip()


def _auth_token() -> str:
    return (settings.plivo_auth_token or "").strip()


def _voice_number() -> str:
    """Caller-ID for outbound calls — a dedicated Plivo voice number if set, else
    the shared Plivo number."""
    return (settings.plivo_voice_number or settings.plivo_from_number or "")


def _transfer_number() -> str:
    """Where a live-answered auto-dial is transferred — the producer's cell first."""
    return _e164(settings.producer_cell or settings.producer_callback)


def is_configured() -> bool:
    """Bridge/auto-dial calling: Plivo creds + a caller-ID number + your callback."""
    return bool(_auth_id() and _auth_token() and _voice_number()
                and settings.producer_callback)


def voicemail_configured() -> bool:
    return bool(settings.producer_voicemail_url)


def _base_url() -> str:
    return (settings.public_base_url or "").rstrip("/")


def _xml(body: str) -> str:
    return f'<?xml version="1.0" encoding="UTF-8"?><Response>{body}</Response>'


def _amd_is_human(answered_by: str | None) -> bool:
    """Human AND unknown → treat as human (better to connect a real person than to
    voicemail someone live). Plivo reports 'human'/'machine' (or blank on timeout)."""
    return (answered_by or "").strip().lower() in ("human", "", "unknown", "person")


def _vm_fallback_text() -> str:
    return (f"Hi, this is {settings.producer_name} with Thrust Insurance. I'm following up on the "
            "insurance quote you requested. Please give me a call back whenever you have a moment. "
            "Thank you and talk soon.")


# ── Plivo XML the webhooks return ─────────────────────────────────────────────
def _voicemail_xml() -> str:
    """Leave the recorded drop (real voice), else a spoken fallback."""
    vm = settings.producer_voicemail_url
    return _xml(f'<Play>{vm}</Play>' if vm else f'<Speak>{_vm_fallback_text()}</Speak>')


def amd_xml(answered_by: str | None, lead_id: str | None) -> str:
    """After Plivo's machine detection on the call to the lead:
      • human  → (if transfer enabled) connect to the producer's cell, else drop VM
      • machine → play the producer's recorded voicemail, then hang up."""
    if settings.auto_dial_transfer_enabled and _amd_is_human(answered_by):
        num = _transfer_number()
        rec = ' record="true"' if settings.call_recording_enabled else ""
        return _xml('<Speak>Please hold — connecting you with a licensed insurance producer. '
                    'This call may be recorded for quality.</Speak>'
                    f'<Dial callerId="{_e164(_voice_number())}"{rec}><Number>{num}</Number></Dial>')
    return _voicemail_xml()


def bridge_xml(lead_phone: str, lead_id: str | None) -> str:
    """Returned after the producer answers a bridge call — dial + record the lead,
    with the spoken consent notice."""
    num = _e164(lead_phone) or lead_phone
    rec = ' record="true"' if settings.call_recording_enabled else ""
    return _xml(f'<Speak>{_CONSENT}</Speak>'
                f'<Dial callerId="{_e164(_voice_number())}"{rec}><Number>{num}</Number></Dial>')


def record_vm_xml() -> str:
    """Played when we call the producer to capture their voicemail drop."""
    base = _base_url()
    return _xml('<Speak>Record the voicemail you want left for leads after the beep. '
                'Press the pound key when you are done.</Speak>'
                f'<Record action="{base}/calls/plivo/vm-saved" maxLength="60" '
                'finishOnKey="#" playBeep="true" redirect="false"/>')


# ── Placing calls (Plivo Call API) ────────────────────────────────────────────
def _place(to: str, answer_path: str, *, machine_detection: bool) -> tuple[str | None, str | None]:
    base = _base_url()
    if not base:
        return None, "PUBLIC_BASE_URL is not set, so Plivo can't reach the call webhooks."
    url = f"https://api.plivo.com/v1/Account/{_auth_id()}/Call/"
    data: dict = {
        "from": _e164(_voice_number()),
        "to": to,
        "answer_url": f"{base}{answer_path}",
        "answer_method": "POST",
        "hangup_url": f"{base}/calls/plivo/status",
        "hangup_method": "POST",
    }
    if machine_detection:
        # Async AMD: Plivo detects, then requests answer_url with a 'Machine' param.
        data["machine_detection"] = "true"
        data["machine_detection_time"] = "5000"
    try:
        r = httpx.post(url, json=data, auth=(_auth_id(), _auth_token()), timeout=20)
        if r.status_code >= 400:
            try:
                j = r.json()
                msg = j.get("error") or j.get("message") or str(j)[:160]
            except Exception:
                msg = (r.text or "")[:160]
            hint = " (check the Plivo Auth ID / Auth Token)" if r.status_code == 401 else ""
            return None, f"Plivo {r.status_code}: {msg}{hint}"
        try:
            uuid = r.json().get("request_uuid") or r.json().get("call_uuid")
        except Exception:
            uuid = None
        return (uuid or "plivo-call"), None
    except Exception as exc:  # pragma: no cover - network guard
        return None, f"Call failed: {str(exc)[:160]}"


def place_auto_call(lead_phone: str, lead_id: str | None) -> tuple[str | None, str | None]:
    """Dial the LEAD directly with answering-machine detection. On answer Plivo hits
    /calls/plivo/amd, which transfers a human to your phone (if enabled) or drops your
    voicemail on a machine. Returns (call_uuid, error)."""
    if not is_configured():
        return None, "Plivo calling not connected — add Plivo Auth ID/Token + a number + your callback."
    to_lead = _e164(lead_phone)
    if not to_lead:
        return None, "lead has no valid phone number"
    q = urlencode({"lead_id": lead_id}) if lead_id else ""
    return _place(to_lead, f"/calls/plivo/amd{('?' + q) if q else ''}", machine_detection=True)


def place_bridge_call(lead_phone: str, lead_id: str | None) -> tuple[str | None, str | None]:
    """Ring the producer's phone; on answer, Plivo bridges to the lead."""
    if not is_configured():
        return None, "Plivo calling not connected — add Plivo Auth ID/Token + a number + your callback."
    to_lead = _e164(lead_phone)
    if not to_lead:
        return None, "lead has no valid phone number"
    q = urlencode({k: v for k, v in {"lead_phone": to_lead, "lead_id": lead_id}.items() if v})
    return _place(_e164(settings.producer_callback), f"/calls/plivo/bridge?{q}", machine_detection=False)


def record_voicemail_call() -> tuple[str | None, str | None]:
    """Ring the producer's phone so they can record the voicemail drop."""
    if not is_configured():
        return None, "Add Plivo + your callback number on Setup first."
    return _place(_e164(settings.producer_callback), "/calls/plivo/record-vm", machine_detection=False)
