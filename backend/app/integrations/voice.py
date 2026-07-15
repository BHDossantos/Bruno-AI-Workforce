"""Voice provider dispatcher.

Routes calling (auto-dial, bridge, voicemail-record) to Plivo, Vonage, or the
Twilio-compatible stack (Twilio/SignalWire) based on ``voice_provider``, exposing
ONE interface so the auto-dialer and the Call button don't care which carrier
places the call. This lets voice move between carriers when one number's
reputation is filtering calls to voicemail — without touching the callers.

Only the call-PLACING + status surface is dispatched here. The provider-specific
call-control webhooks stay in their own modules (TwiML → twilio_voice, Plivo XML →
plivo_voice, NCCO → vonage_voice), since each speaks different markup.
"""
from __future__ import annotations

from ..config import settings


def active() -> str | None:
    """Which provider a call would use right now — 'plivo' | 'vonage' | 'twilio',
    or None if nothing is connected. An explicit ``voice_provider`` wins when that
    provider is configured; otherwise auto prefers a dedicated alternative carrier
    (Vonage, then Plivo) over the Twilio-compatible stack."""
    from . import plivo_voice, twilio_voice, vonage_voice
    pref = (settings.voice_provider or "auto").strip().lower()
    if pref == "plivo" and plivo_voice.is_configured():
        return "plivo"
    if pref == "vonage" and vonage_voice.is_configured():
        return "vonage"
    if pref in ("twilio", "signalwire") and twilio_voice.is_configured():
        return "twilio"
    # auto (or the preferred one isn't configured): pick what's connected.
    if vonage_voice.is_configured():
        return "vonage"
    if plivo_voice.is_configured():
        return "plivo"
    if twilio_voice.is_configured():
        return "twilio"
    return None


def _mod():
    from . import plivo_voice, twilio_voice, vonage_voice
    return {"plivo": plivo_voice, "vonage": vonage_voice, "twilio": twilio_voice}.get(
        active(), twilio_voice)


def is_configured() -> bool:
    from . import plivo_voice, twilio_voice, vonage_voice
    return (plivo_voice.is_configured() or vonage_voice.is_configured()
            or twilio_voice.is_configured())


def voicemail_configured() -> bool:
    from . import twilio_voice  # same producer_voicemail_url for every provider
    return twilio_voice.voicemail_configured()


def browser_configured() -> bool:
    from . import twilio_voice  # browser softphone is Twilio-only
    return twilio_voice.browser_configured()


def access_token(identity: str):
    from . import twilio_voice
    return twilio_voice.access_token(identity)


def place_auto_call(lead_phone: str, lead_id: str | None) -> tuple[str | None, str | None]:
    return _mod().place_auto_call(lead_phone, lead_id)


def place_bridge_call(lead_phone: str, lead_id: str | None) -> tuple[str | None, str | None]:
    return _mod().place_bridge_call(lead_phone, lead_id)


def record_voicemail_call() -> tuple[str | None, str | None]:
    return _mod().record_voicemail_call()
