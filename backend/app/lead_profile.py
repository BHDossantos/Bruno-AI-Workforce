"""Per-lead quote-intake profile.

Tracks the ACTUAL answers a prospect has given against the requirements
checklist for their quote type (Personal Auto, Commercial Auto, Workers' Comp,
General Liability — see quote_intake.py), so a lead's page shows exactly what's
been collected and what's still missing instead of just an emailed checklist.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from . import quote_intake
from .models import Lead


def profile_for(lead: Lead) -> dict:
    """The lead's intake profile: chosen quote type, its fields, saved answers,
    and completion — empty/incomplete until a quote type has been picked."""
    intake = lead.intake or {}
    quote_type = intake.get("quote_type")
    template = quote_intake.get(quote_type) if quote_type else None
    fields = template["fields"] if template else []
    answers = intake.get("answers") or {}
    collected = sum(1 for f in fields if (answers.get(f["key"]) or "").strip())
    return {
        "lead_id": str(lead.id),
        "quote_type": quote_type,
        "quote_type_label": template["label"] if template else None,
        "fields": fields,
        "answers": answers,
        "collected": collected,
        "total": len(fields),
        "complete": bool(fields) and collected == len(fields),
        "updated_at": intake.get("updated_at"),
    }


def save_intake(db: Session, lead_id: str, quote_type: str, answers: dict[str, str]) -> dict | None:
    """Set/replace a lead's quote type + answers. Returns None if the lead or
    quote type doesn't exist; unknown answer keys are dropped so stale fields
    from a previously-selected quote type can never linger."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        return None
    template = quote_intake.get(quote_type)
    if not template:
        return None
    valid_keys = {f["key"] for f in template["fields"]}
    clean_answers = {k: v for k, v in (answers or {}).items() if k in valid_keys and (v or "").strip()}
    lead.intake = {
        "quote_type": quote_type, "answers": clean_answers,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    db.commit()
    return profile_for(lead)
