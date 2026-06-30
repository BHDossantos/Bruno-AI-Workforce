"""Runtime-configurable credentials so the user can connect Gmail + lead-data
sources from inside the app (no redeploy, no env-var editing).

Values are stored in the Setting table and applied onto the in-memory ``settings``
object — at startup and whenever saved — so the existing gmail/apollo/places code
keeps reading ``settings`` unchanged. An explicit environment variable always wins
over a stored value (so prod secrets set in the deployment aren't overridden).

Secrets are WRITE-ONLY through the API: they're never returned, only a
"configured: true/false" status and non-secret addresses.
"""
from __future__ import annotations

import logging

from .config import settings
from .models import Setting

log = logging.getLogger("bruno.runtime_config")

_PREFIX = "cfg:"

# settings attribute -> is_secret. The keys map 1:1 to Settings fields.
FIELDS: dict[str, bool] = {
    "gmail_address": False,
    "gmail_app_password": True,
    "insurance_gmail_address": False,
    "insurance_gmail_app_password": True,
    "bnb_gmail_address": False,
    "bnb_gmail_app_password": True,
    "savorymind_gmail_address": False,
    "savorymind_gmail_app_password": True,
    "apollo_api_key": True,
    "google_places_api_key": True,
    # Twilio (two-way SMS) — connect texting in-app instead of env vars.
    "twilio_account_sid": True,
    "twilio_auth_token": True,
    "twilio_from_number": False,
    "twilio_insurance_number": False,  # optional separate number for insurance texts
    # JSearch / RapidAPI key → live LinkedIn/Indeed/Glassdoor/ZipRecruiter jobs.
    "jobs_api_key": True,
    # Instantly.ai / Smartlead.ai — dedicated cold-email sending engines.
    "instantly_api_key": True,
    "instantly_campaign_id": False,
    "smartlead_api_key": True,
    "smartlead_campaign_id": False,
    # SendGrid — reliable email delivery (verified sender required).
    "sendgrid_api_key": True,
    "sendgrid_from_email": False,
    "sendgrid_from_insurance": False,
    "sendgrid_from_bnb": False,
    "sendgrid_from_savorymind": False,
}


def _stored(db, field: str) -> str:
    try:
        row = db.get(Setting, _PREFIX + field)
        return (row.value or "") if row else ""
    except Exception:  # pragma: no cover - defensive
        return ""


def apply_to_settings(db) -> None:
    """Load stored credentials into the live settings object (env vars win)."""
    import os
    for field in FIELDS:
        if os.environ.get(field.upper()):
            continue  # an explicit env var takes precedence
        val = _stored(db, field)
        if val:
            try:
                setattr(settings, field, val)
            except Exception:  # pragma: no cover
                log.warning("could not apply stored config %s", field)


def save(db, field: str, value: str) -> bool:
    """Persist one credential and apply it immediately. Returns True if accepted."""
    if field not in FIELDS:
        return False
    value = (value or "").strip()
    # Gmail App Passwords are shown as "abcd efgh ijkl mnop" — users paste them
    # WITH the spaces, which makes SMTP login fail. Strip ALL internal whitespace
    # so the 16-char password authenticates regardless of how it was copied.
    if field.endswith("app_password"):
        value = "".join(value.split())
    row = db.get(Setting, _PREFIX + field)
    if row is None:
        row = Setting(key=_PREFIX + field)
        db.add(row)
    row.value = value
    db.commit()
    try:
        setattr(settings, field, value)
    except Exception:  # pragma: no cover
        pass
    return True


def status(db) -> dict:
    """Connection status — booleans + non-secret addresses only, never secrets."""
    from .integrations import apollo, gmail, instantly, jobs_api, places, sendgrid, smartlead, sms
    apply_to_settings(db)  # make sure the live view reflects stored values
    bridge_on = bool(settings.bridge_token)
    return {
        "instantly": {"configured": instantly.is_configured(),
                      "has_key": instantly.has_key()},
        "smartlead": {"configured": smartlead.is_configured(),
                      "has_key": smartlead.has_key()},
        "sendgrid": {"configured": sendgrid.is_configured(),
                     "has_key": sendgrid.has_key()},
        "gmail_personal": {
            "configured": gmail.is_configured(gmail.PERSONAL),
            "address": settings.gmail_address or "",
        },
        "gmail_insurance": {
            "configured": gmail.is_configured(gmail.INSURANCE),
            "address": settings.insurance_gmail_address or "",
        },
        "gmail_bnb": {
            "configured": gmail.is_configured(gmail.BNB),
            "address": settings.bnb_gmail_address or "",
        },
        "gmail_savorymind": {
            "configured": gmail.is_configured(gmail.SAVORYMIND),
            "address": settings.savorymind_gmail_address or "",
        },
        "apollo": {"configured": apollo.is_configured()},
        "google_places": {"configured": places.is_configured()},
        "sms": {"configured": sms.is_configured() or bridge_on,
                "via": "twilio" if sms.is_configured() else ("bridge" if bridge_on else None)},
        "jobs_api": {"configured": jobs_api.is_configured()},
    }
