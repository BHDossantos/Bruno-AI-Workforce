"""Twilio-compatible transport shared by the voice + SMS integrations.

Twilio and SignalWire expose the *identical* REST + TwiML ("Compatibility") API —
same request params, same TwiML verbs, same JSON response shape. They differ only
in the API host and the Basic-auth credential pair. Centralizing that choice here
lets the voice and SMS code build ONE request that runs on whichever is connected,
so SignalWire is a true drop-in when Twilio isn't available (deactivated/rejected).

    Twilio      https://api.twilio.com/2010-04-01/Accounts/{AccountSid}/…
                auth = (AccountSid, AuthToken)
    SignalWire  https://{space}.signalwire.com/api/laml/2010-04-01/Accounts/{ProjectID}/…
                auth = (ProjectID, APIToken)
"""
from __future__ import annotations

from ..config import settings


def _twilio_creds() -> bool:
    return bool((settings.twilio_account_sid or "").strip()
                and (settings.twilio_auth_token or "").strip())


def signalwire_configured() -> bool:
    """SignalWire needs a Space URL, a Project ID, and an API token."""
    return bool((settings.signalwire_space_url or "").strip()
                and (settings.signalwire_project_id or "").strip()
                and (settings.signalwire_api_token or "").strip())


def provider() -> str | None:
    """The active Twilio-compatible backend, or None if neither is connected.

    SignalWire is preferred whenever it's connected (it's the drop-in Twilio
    replacement). Setting ``sms_provider='twilio'`` forces Twilio when its creds
    exist — an explicit escape hatch if both are connected at once."""
    forced = (settings.sms_provider or "auto").strip().lower()
    if forced == "twilio" and _twilio_creds():
        return "twilio"
    if signalwire_configured():
        return "signalwire"
    if _twilio_creds():
        return "twilio"
    return None


def configured() -> bool:
    return provider() is not None


def _space() -> str:
    """The bare SignalWire Space host — tolerates a pasted 'https://…/' form."""
    s = (settings.signalwire_space_url or "").strip()
    return s.replace("https://", "").replace("http://", "").strip("/")


def account_sid() -> str:
    """The value that goes in the /Accounts/{…}/ path and the Basic-auth username."""
    if provider() == "signalwire":
        return (settings.signalwire_project_id or "").strip()
    return (settings.twilio_account_sid or "").strip()


def auth() -> tuple[str, str]:
    """Basic-auth pair for the active provider (whitespace-stripped — a stray space
    in a pasted credential is the classic cause of a 20003 'Authenticate' 401)."""
    if provider() == "signalwire":
        return account_sid(), (settings.signalwire_api_token or "").strip()
    return account_sid(), (settings.twilio_auth_token or "").strip()


def api_url(resource: str) -> str:
    """Full Compatibility-API URL for a resource, e.g. 'Messages.json'/'Calls.json'."""
    if provider() == "signalwire":
        return (f"https://{_space()}/api/laml/2010-04-01/Accounts/"
                f"{account_sid()}/{resource}")
    return f"https://api.twilio.com/2010-04-01/Accounts/{account_sid()}/{resource}"


def label() -> str:
    """Human name of the active provider — for error messages/status."""
    return "SignalWire" if provider() == "signalwire" else "Twilio"
