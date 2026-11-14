"""Read-only staging proposal using the existing Twilio connection.

Run from backend: python -m app.scripts.stage_inbound_assistant
Reads existing local configuration/DB only. Never calls a provider or writes settings.
No account SID, auth token, database URL or raw exception is printed.
"""
import json
import re

from fastapi import HTTPException

from ..callback_auth import _credential
from ..config import settings
from ..database import SessionLocal

PHONE = re.compile(r"\+[1-9]\d{7,14}\Z")


def phone(value):
    """Accept E.164 or the existing US cell format; reject ambiguous input."""
    value = value.strip()
    if PHONE.fullmatch(value):
        return value
    if re.fullmatch(r"1\d{10}", value):
        return "+" + value
    return ""


def stage(db):
    report = {
        "mode": "read_only_proposal",
        "provider_requests_made": False,
        "account_verified": False,
        "balance_verified": False,
        "number_ownership_verified": False,
        "personal_destination_verified": False,
        "ready_for_activation": False,
        "proposed_environment": {
            "INBOUND_ASSISTANT_ENABLED": "false",
            "INBOUND_ASSISTANT_NUMBER": "",
            "INBOUND_ASSISTANT_TRANSFER_NUMBER": "",
            "INBOUND_ASSISTANT_VERIFIED_TRANSFER_NUMBER": "",
        },
        "blockers": [],
    }
    # Match webhook env-over-DB precedence, including explicitly cleared fields.
    # A failed config-store lookup must not silently stage stale/default numbers.
    try:
        sid = _credential(db, "twilio_account_sid")
        token = _credential(db, "twilio_auth_token")
        values = {key: _credential(db, key) for key in (
            "twilio_voice_number", "twilio_insurance_number", "twilio_from_number",
            "producer_cell", "producer_callback")}
    except HTTPException:
        report["configuration_readable"] = False
        report["blockers"].append("Existing runtime configuration could not be read; no numbers proposed.")
        return report
    report["configuration_readable"] = True
    report["existing_credentials_configured"] = bool(sid and token)
    if not sid or not token:
        report["blockers"].append("Existing Twilio account SID/auth token are missing; use the existing account connection.")
    public = settings.inbound_assistant_number or values["twilio_voice_number"] or values["twilio_insurance_number"] or values["twilio_from_number"]
    personal = settings.inbound_assistant_transfer_number or values["producer_cell"] or values["producer_callback"]
    public, personal = phone(public), phone(personal)
    if not public:
        report["blockers"].append("Confirm an existing voice-capable Twilio public number in E.164.")
    known_public = {phone(values[key]) for key in (
        "twilio_voice_number", "twilio_insurance_number", "twilio_from_number")}
    known_public.add(public)
    if personal and personal in known_public:
        report["blockers"].append("Transfer destination matches a configured public Twilio number; possible forwarding loop.")
        personal = ""
    if not personal:
        report["blockers"].append("Confirm Bruno's separate personal destination in E.164.")
    report["proposed_environment"].update(
        INBOUND_ASSISTANT_NUMBER=public, INBOUND_ASSISTANT_TRANSFER_NUMBER=personal)
    report["currently_enabled"] = settings.inbound_assistant_enabled
    report["blockers"].extend([
        "Verify the existing account, its balance and ownership/voice capability of the public number in Twilio Console.",
        "Independently verify personal destination ownership and that its carrier does not forward back to any assistant number.",
        "Separately authorize configuration, deployment/routing and staging calls; this proposal changes nothing.",
    ])
    return report


def main():
    with SessionLocal() as db:
        print(json.dumps(stage(db), indent=2))


if __name__ == "__main__":
    main()
