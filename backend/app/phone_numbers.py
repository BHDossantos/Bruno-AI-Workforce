"""The business phone number: ONE setting, used by every channel.

Swapping numbers used to mean finding every copy: code defaults, the per-channel
Setup fields (texting, insurance texting, caller-ID, transfer caller-ID) and the
number printed in email signatures. Any stale copy kept the old number ringing.

Now ``settings.business_phone`` is the source. A per-channel field is only an
optional override: blank means "use the business number". Saving a new business
number in Setup clears those overrides (see ``runtime_config.save``), so an old
copy can't win. How to swap: docs/phone-number.md.

Scope: the Twilio numbers. SignalWire, Plivo, Vonage and SIP each own their own
numbers on their own carrier, so they keep their own fields.
"""
from __future__ import annotations

import os
import re

from .config import settings

# Per-channel fields that override the business number when set. Cleared whenever a
# new business number is saved, so no stale copy outlives a number swap.
OVERRIDES: tuple[str, ...] = (
    "twilio_from_number",       # texting "from"
    "twilio_insurance_number",  # insurance texting "from"
    "twilio_voice_number",      # outbound caller-ID
    "transfer_caller_id",       # caller-ID on bridged legs that ring the owner's cell
    "producer_office_phone",    # number printed on emails / signatures
)


def e164(phone: str | None) -> str:
    """Normalize a US phone to E.164 (+1XXXXXXXXXX) so carriers accept it and it's
    safe in a URL. '(978) 254-1435' -> '+19782541435'."""
    d = re.sub(r"\D", "", phone or "")
    if len(d) == 11 and d.startswith("1"):
        return "+" + d
    if len(d) == 10:
        return "+1" + d
    return ("+" + d) if d else ""


def display(phone: str | None) -> str:
    """'+18575551011' -> '(857) 555-1011' — the format printed on outreach.
    Non-US numbers come back unchanged so we never mangle them."""
    n = e164(phone)
    d = n[2:] if n.startswith("+1") and len(n) == 12 else ""
    return f"({d[:3]}) {d[3:6]}-{d[6:]}" if d else (phone or "")


def business_number() -> str:
    """The one business number (E.164), or '' when none is set."""
    return e164(settings.business_phone)


def office_phone() -> str:
    """The number shown on emails and signatures: the override if set, else the
    business number."""
    return (settings.producer_office_phone or "").strip() or display(business_number())


def pinned_by_env() -> list[str]:
    """Number settings fixed by a deployment env var. Env vars beat Setup, so a
    leftover one silently keeps an old number alive — Setup lists them as a warning."""
    return [f.upper() for f in ("business_phone", *OVERRIDES) if os.environ.get(f.upper())]


def summary() -> dict:
    """Which number each channel uses right now, and why — for Setup."""
    from .integrations import sms, twilio_voice
    return {
        "business_phone": business_number(),
        "texting_from": e164(sms.number_for("personal", "twilio")),
        "insurance_texting_from": e164(sms.number_for("insurance", "twilio")),
        "caller_id": e164(twilio_voice._voice_number()),
        "transfer_caller_id": twilio_voice.bridge_caller_id(),
        "office_phone": office_phone(),
        "overrides_set": [f for f in OVERRIDES if (getattr(settings, f, "") or "").strip()],
        "pinned_by_env": pinned_by_env(),
    }
