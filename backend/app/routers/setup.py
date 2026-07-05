"""Connect Gmail + lead-data sources from inside the app.

The email engine and lead providers read from settings (env vars). This lets the
user connect them at runtime instead — credentials are stored server-side and
applied immediately. Secrets are write-only: the status endpoint returns only
whether each is configured, never the secret itself.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import runtime_config
from ..database import get_db
from ..security import require_role

router = APIRouter(prefix="/setup", tags=["setup"])


class CredIn(BaseModel):
    openai_api_key: str | None = None
    openai_model: str | None = None
    gmail_address: str | None = None
    gmail_app_password: str | None = None
    insurance_gmail_address: str | None = None
    insurance_gmail_app_password: str | None = None
    bnb_gmail_address: str | None = None
    bnb_gmail_app_password: str | None = None
    savorymind_gmail_address: str | None = None
    savorymind_gmail_app_password: str | None = None
    apollo_api_key: str | None = None
    google_places_api_key: str | None = None
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_from_number: str | None = None
    twilio_insurance_number: str | None = None
    twilio_whatsapp_number: str | None = None
    whatsapp_cloud_phone_number_id: str | None = None
    whatsapp_cloud_token: str | None = None
    jobs_api_key: str | None = None
    instantly_api_key: str | None = None
    instantly_campaign_id: str | None = None
    smartlead_api_key: str | None = None
    smartlead_campaign_id: str | None = None
    sendgrid_api_key: str | None = None
    sendgrid_from_email: str | None = None
    sendgrid_from_insurance: str | None = None
    sendgrid_from_bnb: str | None = None
    sendgrid_from_savorymind: str | None = None
    sendgrid_replyto_insurance: str | None = None
    sendgrid_replyto_bnb: str | None = None
    sendgrid_replyto_savorymind: str | None = None
    calendar_link: str | None = None
    calendar_link_insurance: str | None = None
    calendar_link_bnb: str | None = None
    calendar_link_savorymind: str | None = None
    contacts_outreach_exclude: str | None = None
    newsletter_banner_insurance: str | None = None
    newsletter_banner_bnb: str | None = None
    newsletter_banner_savorymind: str | None = None
    newsletter_banner_music: str | None = None
    facebook_app_id: str | None = None
    facebook_app_secret: str | None = None
    meta_redirect_uri: str | None = None
    tiktok_client_key: str | None = None
    tiktok_client_secret: str | None = None
    tiktok_redirect_uri: str | None = None
    elevenlabs_api_key: str | None = None
    video_api_key: str | None = None
    gcs_bucket: str | None = None
    hubspot_api_key: str | None = None
    plaid_client_id: str | None = None
    plaid_secret: str | None = None


@router.get("")
def get_status(db: Session = Depends(get_db),
              _=Depends(require_role("admin", "operator", "viewer"))):
    """What's connected — booleans + non-secret addresses only."""
    return runtime_config.status(db)


@router.get("/mailbox-health")
def mailbox_health(db: Session = Depends(get_db),
                   _=Depends(require_role("admin", "operator", "viewer"))):
    """Is each mailbox ACTUALLY able to send right now? Does a real auth check
    (no email sent) per account, plus today's sent-count vs the daily cap, so you
    can confirm outreach will go out — not just that a key is saved."""
    runtime_config.apply_to_settings(db)  # use the latest connected creds
    from .. import outreach
    from ..config import settings
    from ..integrations import gmail, sendgrid
    accounts = [("personal", "Personal Gmail"), ("insurance", "Insurance mailbox (primary)"),
                ("insurance_backup", "Insurance mailbox #2 (backup)"),
                ("bnb", "BnB Global mailbox"), ("savorymind", "SavoryMind mailbox")]
    out = []
    # SendGrid (if connected) is the actual sender — show its health first.
    if sendgrid.has_key():
        v = sendgrid.verify()
        out.append({
            "account": "sendgrid", "label": "SendGrid (delivery)",
            "configured": sendgrid.is_configured(),
            "can_send": bool(v.get("ok") and sendgrid.is_configured()),
            "method": "sendgrid", "address": settings.sendgrid_from_email or None,
            "reason": (v.get("reason") if not v.get("ok") else
                       (None if sendgrid.is_configured() else "Add a verified sender email")),
            "sent_today": int(outreach.sent_today_count(db, "personal")),
            "daily_cap": int(settings.sendgrid_daily_cap),
            "remaining_today": max(0, int(settings.sendgrid_daily_cap) - int(outreach.sent_today_count(db, "personal"))),
        })
    for key, label in accounts:
        v = gmail.verify(key)
        sent_today = outreach.sent_today_count(db, key)
        cap = outreach.effective_cap(db, key)
        out.append({
            "account": key, "label": label,
            "configured": gmail.is_configured(key),
            "can_send": bool(v.get("ok")), "method": v.get("method"),
            "address": v.get("address"), "reason": v.get("reason"),
            "sent_today": int(sent_today), "daily_cap": int(cap),
            "remaining_today": max(0, int(cap) - int(sent_today)),
        })
    # Show the EFFECTIVE mode (an invalid value like "15" is treated as "send").
    _m = (settings.gmail_outbound_mode or "send").strip().lower()
    effective_mode = _m if _m in ("send", "send_on_approve", "draft") else "send"
    return {"outbound_mode": effective_mode, "accounts": out}


@router.post("")
def save(body: CredIn, db: Session = Depends(get_db),
         _=Depends(require_role("admin", "operator"))):
    """Save any provided credentials (blank/None fields are ignored)."""
    saved = []
    for field, value in body.model_dump().items():
        if value is not None and value.strip() != "":
            if runtime_config.save(db, field, value):
                saved.append(field)
    return {"ok": True, "saved": saved, "status": runtime_config.status(db)}
