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
    gmail_address: str | None = None
    gmail_app_password: str | None = None
    insurance_gmail_address: str | None = None
    insurance_gmail_app_password: str | None = None
    apollo_api_key: str | None = None
    google_places_api_key: str | None = None
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_from_number: str | None = None


@router.get("")
def get_status(db: Session = Depends(get_db),
              _=Depends(require_role("admin", "operator", "viewer"))):
    """What's connected — booleans + non-secret addresses only."""
    return runtime_config.status(db)


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
