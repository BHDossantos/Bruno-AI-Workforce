"""Voice provider dispatcher.

Routes calling (auto-dial, bridge, voicemail-record) to Plivo or the
Twilio-compatible stack (Twilio/SignalWire) based on ``voice_provider``, exposing
ONE interface so the auto-dialer and the Call button don't care which carrier
places the call. This lets voice move to Plivo when a Twilio-compatible number's
carrier reputation is filtering calls to voicemail — without touching the callers.

Only the call-PLACING + status surface is dispatched here. The provider-specific
call-control webhooks stay in their own modules (TwiML routes → twilio_voice,
Plivo-XML routes → plivo_voice), since the two speak different markup.
"""
from __future__ import annotations

from ..config import settings


def _use_plivo() -> bool:
    from . import plivo_voice
    pref = (settings.voice_provider or "auto").strip().lower()
    if pref == "plivo":
        return plivo_voice.is_configured()
    if pref in ("twilio", "signalwire"):
        return False
    return plivo_voice.is_configured()  # auto: Plivo is the deliberate fallback


def active() -> str | None:
    """Which provider a call would use right now — for status/UI."""
    from . import plivo_voice, twilio_voice
    if _use_plivo():
        return "plivo"
    if twilio_voice.is_configured():
        return "twilio"
    return "plivo" if plivo_voice.is_configured() else None


def is_configured() -> bool:
    from . import plivo_voice, twilio_voice
    return plivo_voice.is_configured() or twilio_voice.is_configured()


def voicemail_configured() -> bool:
    from . import twilio_voice  # same producer_voicemail_url for both providers
    return twilio_voice.voicemail_configured()


def browser_configured() -> bool:
    from . import twilio_voice  # browser softphone is Twilio-only
    return twilio_voice.browser_configured()


def access_token(identity: str):
    from . import twilio_voice
    return twilio_voice.access_token(identity)


def _mod():
    from . import plivo_voice, twilio_voice
    return plivo_voice if _use_plivo() else twilio_voice


def place_auto_call(lead_phone: str, lead_id: str | None) -> tuple[str | None, str | None]:
    return _mod().place_auto_call(lead_phone, lead_id)


def place_bridge_call(lead_phone: str, lead_id: str | None) -> tuple[str | None, str | None]:
    return _mod().place_bridge_call(lead_phone, lead_id)


def record_voicemail_call() -> tuple[str | None, str | None]:
    return _mod().record_voicemail_call()
