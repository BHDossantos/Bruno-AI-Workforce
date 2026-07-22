"""Twilio Voice — place + record calls.

Two ways to call a lead, both bridged through Twilio so the lead sees your
business caller-ID and the call is recorded (with a spoken consent notice for
two-party-consent states like MA/FL):

  • Bridge: Twilio rings YOUR phone first; when you answer it dials the lead and
    connects you. Works from any device — no browser needed.
  • Browser softphone: the Twilio Voice JS SDK calls out from the browser using
    a short-lived access token (for when your phone's dead).

Raw REST + a hand-rolled access-token JWT (PyJWT) — no Twilio SDK dependency.
No-ops cleanly when unconfigured.
"""
from __future__ import annotations

import logging
import re
import time
from urllib.parse import urlencode

import httpx
import jwt

from ..config import settings

log = logging.getLogger("bruno.voice")


def _e164(phone: str | None) -> str:
    """Normalize a US phone to E.164 (+1XXXXXXXXXX) so Twilio accepts it and it's
    safe in a URL. '(978) 254-1435' -> '+19782541435'."""
    d = re.sub(r"\D", "", phone or "")
    if len(d) == 11 and d.startswith("1"):
        return "+" + d
    if len(d) == 10:
        return "+1" + d
    return ("+" + d) if d else ""

_CONSENT = ("This call is with a licensed insurance producer and may be "
            "recorded for quality and training purposes.")


def _voice_number() -> str:
    from . import telco
    if telco.provider("voice") == "signalwire":
        return (settings.signalwire_voice_number or settings.signalwire_insurance_number
                or settings.signalwire_from_number or "")
    return (settings.twilio_voice_number or settings.twilio_insurance_number
            or settings.twilio_from_number or "")


def _transfer_number() -> str:
    """Where a live-answered auto-dial is transferred — the producer's CELL first,
    then the callback number as a fallback. So 'someone answers → my cell rings.'"""
    return _e164(settings.producer_cell or settings.producer_callback)


def _callback_number() -> str:
    """The phone the bridge / test call rings FIRST (you), then connects the lead.
    Uses the callback field, falling back to the cell — so calling works when EITHER
    is set (the callback field is often left blank while the cell is filled in)."""
    return _e164(settings.producer_callback or settings.producer_cell)


def pretty_phone(e164: str) -> str:
    """Human-readable US number for the UI: '+16039308272' -> '+1 (603) 930-8272'.
    Non-US / short numbers are returned as-is so we never mangle them."""
    d = re.sub(r"\D", "", e164 or "")
    if len(d) == 11 and d.startswith("1"):
        return f"+1 ({d[1:4]}) {d[4:7]}-{d[7:]}"
    return e164 or ""


def dial_targets() -> dict:
    """The exact numbers the calling engine will use RIGHT NOW — so the UI can show
    'we will ring THIS number' instead of leaving it a black box. This is the single
    most common reason 'the call says done but my phone never rang': the number being
    rung isn't the phone in your hand, and nothing surfaced which number it was."""
    rings = _callback_number()
    transfers = _transfer_number()
    caller = _e164(_voice_number()) or _voice_number()
    # Did the rung number come from the explicit callback field, or fall back to the
    # (possibly stale) cell default? Surfacing this tells you where to fix it.
    source = "callback" if _e164(settings.producer_callback) else (
        "cell" if _e164(settings.producer_cell) else "none")
    return {
        "rings_first": rings,
        "rings_first_pretty": pretty_phone(rings),
        "transfers_to": transfers,
        "transfers_to_pretty": pretty_phone(transfers),
        "caller_id": caller,
        "caller_id_pretty": pretty_phone(caller),
        "rings_source": source,
    }


def is_configured() -> bool:
    """Bridge calling: a Twilio-compatible carrier (Twilio or SignalWire) + a
    caller-ID number + a phone to ring you back on (callback or cell)."""
    from . import telco
    return bool(telco.configured("voice") and _voice_number() and _callback_number())


def browser_configured() -> bool:
    """Browser softphone: also needs an API Key + a TwiML App SID."""
    return bool(settings.twilio_account_sid and _voice_number()
                and settings.twilio_api_key_sid and settings.twilio_api_key_secret
                and settings.twilio_twiml_app_sid)


def _base_url() -> str:
    return (settings.public_base_url or "").rstrip("/")


def _xml(body: str) -> str:
    return f'<?xml version="1.0" encoding="UTF-8"?><Response>{body}</Response>'


def _dial_lead(lead_phone: str, lead_id: str | None) -> str:
    """TwiML that dials the lead with our caller-ID, plays the consent notice TO
    the lead when they answer, and records the bridged call."""
    base, rec = _base_url(), settings.call_recording_enabled
    num = _e164(lead_phone) or lead_phone
    announce = (f'<Number url="{base}/calls/twiml/announce">{num}</Number>'
                if (rec and base) else f'<Number>{num}</Number>')
    # answerOnBridge keeps YOUR leg on ringback until the lead actually answers
    # (without it the call can drop in a few seconds); timeout gives the lead time
    # to pick up. callerId must be a Twilio number you own, in E.164 — a value stored
    # with formatting ("(978)…") is an invalid callerId and Twilio drops the <Dial>.
    caller_id = _e164(_voice_number()) or _voice_number()
    attrs = f' callerId="{caller_id}" answerOnBridge="true" timeout="30"'
    if base:
        # After the Dial ends, Twilio POSTs the real outcome (completed / no-answer /
        # busy / failed) here — so a dropped call records WHY instead of us guessing.
        attrs += (f' action="{base}/calls/dial-status'
                  f'{("?lead_id=" + lead_id) if lead_id else ""}"')
    if rec and base:
        attrs += (' record="record-from-answer-dual"'
                  f' recordingStatusCallback="{base}/calls/recording'
                  f'{("?lead_id=" + lead_id) if lead_id else ""}"')
    return _xml(f'<Dial{attrs}>{announce}</Dial>')


def announce_twiml() -> str:
    """Played to the lead on answer, before bridging — the recording consent."""
    return _xml(f'<Say>{_CONSENT}</Say>')


def bridge_twiml(lead_phone: str, lead_id: str | None) -> str:
    return _dial_lead(lead_phone, lead_id)


def outbound_twiml(to: str, lead_id: str | None) -> str:
    """TwiML for a browser-softphone outbound call (Twilio hits the TwiML App)."""
    return _dial_lead(to, lead_id)


def inbound_twiml() -> str:
    """Played when someone CALLS OUR NUMBER back. Greets them as Thrust Insurance
    and forwards the call to the producer's cell (E.164 caller-ID = our own number
    so the carrier accepts the <Dial>); if it isn't answered, takes a short
    voicemail. Point your SignalWire number's 'When a call comes in' webhook here."""
    greeting = ("<Say>Thank you for calling Thrust Insurance. Please hold while we "
                "connect you to a licensed producer.</Say>")
    to = _transfer_number()
    if not to:  # no forwarding number set — take a message instead of dead air
        return _xml(greeting + "<Say>Sorry, no one is available right now. Please leave "
                    'a message after the tone.</Say><Record maxLength="120" playBeep="true"/>')
    caller_id = _e164(_voice_number()) or _voice_number()
    cid = f' callerId="{caller_id}"' if caller_id else ""
    # timeout=20: ring the cell ~20s. If unanswered the document continues to the
    # voicemail prompt below (a completed/answered call never reaches it).
    dial = f'<Dial{cid} timeout="20">{to}</Dial>'
    voicemail = ("<Say>Sorry we missed you. Please leave a message after the tone and "
                 'we will call you right back.</Say><Record maxLength="120" playBeep="true"/>')
    return _xml(greeting + dial + voicemail)


def place_bridge_call(lead_phone: str, lead_id: str | None) -> tuple[str | None, str | None]:
    """Ring the producer's phone; on answer, Twilio bridges to the lead. Returns
    (call_sid, error)."""
    if not is_configured():
        return None, "Calling not connected — add Twilio + your callback number on Setup."
    base = _base_url()
    if not base:
        return None, "PUBLIC_BASE_URL is not set, so Twilio can't reach the call webhooks."
    to_lead = _e164(lead_phone)
    if not to_lead:
        return None, "lead has no valid phone number"
    # URL-encode the query params — a raw '(978) 254-1435' makes Twilio reject the
    # callback URL (code 21205 'Url is not a valid URL').
    bridge_q = urlencode({k: v for k, v in {"lead_phone": to_lead, "lead_id": lead_id}.items() if v})
    status_q = urlencode({"lead_id": lead_id}) if lead_id else ""
    from . import telco
    url = telco.api_url("Calls.json", "voice")
    data = {
        "To": _callback_number(),                  # ring YOU first (callback or cell)
        "From": _e164(_voice_number()),            # E.164 required — SignalWire 21212 otherwise
        "Url": f"{base}/calls/twiml/bridge?{bridge_q}",
        "StatusCallback": f"{base}/calls/status" + (f"?{status_q}" if status_q else ""),
        "StatusCallbackEvent": "completed",
    }
    try:
        r = httpx.post(url, data=data, auth=telco.auth("voice"), timeout=20)
        if r.status_code >= 400:
            return None, f"{telco.label('voice')} {r.status_code}: {(r.text or '')[:160]}"
        return r.json().get("sid"), None
    except Exception as exc:  # pragma: no cover - network guard
        return None, f"Call failed: {str(exc)[:160]}"


def test_twiml() -> str:
    """What the test call plays when you answer — a plain confirmation."""
    return _xml("<Say>Your Bruno A I calling is set up and working. "
                "The auto dialer will call your leads and connect them to this phone. "
                "Goodbye.</Say>")


def place_test_call() -> tuple[str | None, str | None]:
    """Ring the producer's own phone with a confirmation message — a one-tap way to
    prove the carrier credentials + caller-ID + callback number all work end to end,
    without touching a real lead. Returns (call_sid, error)."""
    from . import telco
    if not telco.configured("voice"):
        return None, ("Calling carrier not connected — paste your SignalWire API Token "
                      "(or Twilio creds) in Setup.")
    if not _voice_number():
        return None, "No caller-ID number set — add your SignalWire/Twilio number in Setup."
    to = _callback_number()
    if not to:
        return None, "No callback number — enter your cell in Setup → Calling ('Your cell to ring')."
    base = _base_url()
    if not base:
        return None, f"PUBLIC_BASE_URL is not set, so {telco.label('voice')} can't reach the webhook."
    data = {"To": to, "From": _e164(_voice_number()),
            "Url": f"{base}/calls/twiml/test"}
    try:
        r = httpx.post(telco.api_url("Calls.json", "voice"), data=data,
                       auth=telco.auth("voice"), timeout=20)
        if r.status_code >= 400:
            return None, f"{telco.label('voice')} {r.status_code}: {(r.text or '')[:200]}"
        return r.json().get("sid"), None
    except Exception as exc:  # pragma: no cover - network guard
        return None, f"Call failed: {str(exc)[:160]}"


# ── Auto-dial with answering-machine detection: leave a voicemail or transfer ──
def voicemail_configured() -> bool:
    """True once the producer has recorded their voicemail drop."""
    return bool(settings.producer_voicemail_url)


def _amd_is_human(answered_by: str | None) -> bool:
    """Treat human AND unknown as 'human' — better to connect you to a real person
    than to accidentally leave a voicemail for someone who's actually on the line."""
    return (answered_by or "").strip().lower() in ("human", "", "unknown")


def _vm_fallback_text() -> str:
    return (f"Hi, this is {settings.producer_name} with Thrust Insurance. I'm following up on the "
            "insurance quote you requested. Please give me a call back whenever you have a moment. "
            "Thank you and talk soon.")


def amd_twiml(answered_by: str | None, lead_id: str | None) -> str:
    """After Twilio detects who answered our call to the lead:
      • human  → transfer to the producer's phone (bridged + recorded), or
      • machine → play the producer's recorded voicemail (real voice), then hang up."""
    base = _base_url()
    if _amd_is_human(answered_by):
        num = _transfer_number()   # transfer a live answer to the producer's cell
        rec = ""
        if settings.call_recording_enabled and base:
            rec = (' record="record-from-answer-dual"'
                   f' recordingStatusCallback="{base}/calls/recording'
                   f'{("?lead_id=" + lead_id) if lead_id else ""}"')
        return _xml('<Say>Please hold — connecting you with a licensed insurance producer. '
                    'This call may be recorded for quality.</Say>'
                    f'<Dial callerId="{_e164(_voice_number())}" timeout="25"{rec}>{num}</Dial>')
    # Machine → leave the recorded voicemail (your real voice), else a spoken fallback.
    vm = settings.producer_voicemail_url
    return _xml(f'<Play>{vm}</Play>' if vm else f'<Say>{_vm_fallback_text()}</Say>')


def record_vm_twiml() -> str:
    """Played when we call the producer to capture their voicemail drop."""
    base = _base_url()
    return _xml('<Say>Record the voicemail you want left for leads after the beep. '
                'Press the pound key when you are done.</Say>'
                f'<Record action="{base}/calls/vm-saved" maxLength="60" '
                'finishOnKey="#" playBeep="true"/>')


def place_auto_call(lead_phone: str, lead_id: str | None) -> tuple[str | None, str | None]:
    """Dial the LEAD directly with answering-machine detection. On answer Twilio hits
    /calls/twiml/amd, which transfers a human to your phone or drops your voicemail on
    a machine. Returns (call_sid, error)."""
    if not is_configured():
        return None, "Calling not connected — add Twilio + your callback number on Setup."
    base = _base_url()
    if not base:
        return None, "PUBLIC_BASE_URL is not set, so Twilio can't reach the call webhooks."
    to_lead = _e164(lead_phone)
    if not to_lead:
        return None, "lead has no valid phone number"
    q = urlencode({k: v for k, v in {"lead_phone": to_lead, "lead_id": lead_id}.items() if v})
    status_q = urlencode({"lead_id": lead_id}) if lead_id else ""
    from . import telco
    url = telco.api_url("Calls.json", "voice")
    data = {
        "To": to_lead,                       # dial the LEAD directly (not you first)
        "From": _e164(_voice_number()),
        "Url": f"{base}/calls/twiml/amd?{q}",
        "MachineDetection": "DetectMessageEnd",   # wait for the beep so the whole VM lands
        "MachineDetectionTimeout": "15",
        "StatusCallback": f"{base}/calls/status" + (f"?{status_q}" if status_q else ""),
        "StatusCallbackEvent": "completed",
    }
    try:
        r = httpx.post(url, data=data, auth=telco.auth("voice"), timeout=20)
        if r.status_code >= 400:
            return None, f"{telco.label('voice')} {r.status_code}: {(r.text or '')[:160]}"
        return r.json().get("sid"), None
    except Exception as exc:  # pragma: no cover - network guard
        return None, f"Auto-call failed: {str(exc)[:160]}"


def record_voicemail_call() -> tuple[str | None, str | None]:
    """Ring the producer's phone so they can record the voicemail drop in their own
    voice. The recording is saved via the /calls/vm-saved webhook."""
    from . import telco
    if not (telco.configured("voice") and _voice_number() and settings.producer_callback):
        return None, "Add SignalWire or Twilio + your callback number on Setup first."
    base = _base_url()
    if not base:
        return None, "PUBLIC_BASE_URL is not set, so the carrier can't reach the record webhook."
    url = telco.api_url("Calls.json", "voice")
    data = {"To": _e164(settings.producer_callback), "From": _e164(_voice_number()),
            "Url": f"{base}/calls/twiml/record-vm"}
    try:
        r = httpx.post(url, data=data, auth=telco.auth("voice"), timeout=20)
        if r.status_code >= 400:
            return None, f"{telco.label('voice')} {r.status_code}: {(r.text or '')[:160]}"
        return r.json().get("sid"), None
    except Exception as exc:  # pragma: no cover - network guard
        return None, f"Record call failed: {str(exc)[:160]}"


def access_token(identity: str) -> str | None:
    """Mint a Twilio Voice access token (JWT) for the browser softphone."""
    if not browser_configured():
        return None
    now = int(time.time())
    payload = {
        "jti": f"{settings.twilio_api_key_sid}-{now}",
        "iss": settings.twilio_api_key_sid,
        "sub": settings.twilio_account_sid,
        "iat": now, "exp": now + 3600,
        "grants": {
            "identity": identity,
            "voice": {
                "outgoing": {"application_sid": settings.twilio_twiml_app_sid},
                "incoming": {"allow": True},
            },
        },
    }
    return jwt.encode(payload, settings.twilio_api_key_secret, algorithm="HS256",
                      headers={"cty": "twilio-fpa;v=1", "typ": "JWT"})
