"""CSV lead/restaurant importer.

Lets the user bring real, owned contact lists. Each imported row becomes a Lead
or Restaurant, gets a personalized email written with the marketing skills, is
dispatched via the right Gmail account (respecting send/draft mode + the
real-email guard + daily cap), and gets the full follow-up sequence scheduled.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlalchemy.orm import Session

from . import outreach
from .agents.base import FOLLOW_UP_OFFSETS
from .ai import client, skills
from .ai.prompts import INSURANCE_OUTREACH, SAVORYMIND_PITCH
from .models import FollowUp, Lead, Restaurant

log = logging.getLogger("bruno.importer")


def _g(row: dict, *keys: str) -> str | None:
    """Case-insensitive get across possible column names."""
    lower = {(k or "").strip().lower(): v for k, v in row.items()}
    for k in keys:
        v = lower.get(k.lower())
        if v and str(v).strip():
            return str(v).strip()
    return None


def _schedule_followups(db: Session, entity_type: str, entity_id) -> None:
    today = date.today()
    for step, off in FOLLOW_UP_OFFSETS.items():
        db.add(FollowUp(entity_type=entity_type, entity_id=entity_id, step=step,
                        due_date=today + timedelta(days=off)))


def _text(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, (list, dict)):
        import json
        return json.dumps(v, indent=2)
    return str(v)


def process_leads_csv(db: Session, rows: list[dict]) -> dict:
    """Import insurance leads. Expected columns: email (required), company_name,
    owner_name, phone, website, linkedin, industry, segment, category."""
    sysp = skills.system_prompt("cold-email", "marketing-psychology")
    imported = sent = skipped = 0
    for row in rows:
        email = _g(row, "email", "email_address")
        if not email:
            skipped += 1
            continue
        segment = (_g(row, "segment") or "commercial").lower()
        category = _g(row, "category", "industry") or "Commercial"
        company = _g(row, "company_name", "company", "business", "business_name")
        reason = (f"{category} businesses typically need liability, property and professional coverage."
                  if segment == "commercial" else f"{category} prospects often need home/auto/life coverage.")
        art = client.complete_json(INSURANCE_OUTREACH.format(
            company_name=company or email, category=category, segment=segment,
            industry=_g(row, "industry"), city=_g(row, "city"), reason=reason), system=sysp)
        subject = (art.get("cold_email_subject") if isinstance(art, dict) else None) or \
            f"Insurance options for {company or 'your business'}"
        body = art.get("cold_email_body") if isinstance(art, dict) else None

        lead = Lead(segment=segment, category=category, company_name=company,
                    owner_name=_g(row, "owner_name", "owner", "name"), email=email,
                    phone=_g(row, "phone"), website=_g(row, "website"),
                    linkedin=_g(row, "linkedin"), industry=_g(row, "industry"),
                    reason=reason, score=80, status="Drafted", cold_email=body,
                    call_script=_text(art.get("call_script") if isinstance(art, dict) else None),
                    linkedin_msg=art.get("linkedin_msg") if isinstance(art, dict) else None)
        db.add(lead)
        db.flush()
        msg = outreach.dispatch_email(db, entity_type="lead", entity_id=lead.id, to_email=email,
                                      subject=subject, body=body, account="insurance", actor="import")
        if msg.status == "Sent":
            lead.status = "Sent"
            sent += 1
        _schedule_followups(db, "lead", lead.id)
        imported += 1
    db.commit()
    log.info("Imported %d leads (%d sent, %d skipped)", imported, sent, skipped)
    return {"imported": imported, "sent": sent, "skipped_no_email": skipped}


def process_restaurants_csv(db: Session, rows: list[dict]) -> dict:
    """Import restaurants. Expected columns: email (required), name, owner_manager,
    phone, website, instagram, cuisine, city."""
    sysp = skills.system_prompt("copywriting", "cold-email")
    imported = sent = skipped = 0
    for row in rows:
        email = _g(row, "email", "email_address")
        if not email:
            skipped += 1
            continue
        name = _g(row, "name", "restaurant", "restaurant_name", "company_name") or email
        art = client.complete_json(SAVORYMIND_PITCH.format(
            name=name, cuisine=_g(row, "cuisine") or "restaurant", city=_g(row, "city") or "",
            owner=_g(row, "owner_manager", "owner", "manager") or "", insight="grow revenue with menu intelligence"),
            system=sysp)
        subject = (art.get("pitch_subject") if isinstance(art, dict) else None) or \
            f"Growing revenue at {name} with SavoryMind"
        body = art.get("pitch_body") if isinstance(art, dict) else None

        r = Restaurant(kind="prospect", name=name, owner_manager=_g(row, "owner_manager", "owner", "manager"),
                       website=_g(row, "website"), instagram=_g(row, "instagram"), email=email,
                       phone=_g(row, "phone"), cuisine=_g(row, "cuisine"), city=_g(row, "city"),
                       status="Drafted", pitch_email=body,
                       linkedin_msg=art.get("linkedin_msg") if isinstance(art, dict) else None,
                       follow_up=art.get("demo_invite") if isinstance(art, dict) else None)
        db.add(r)
        db.flush()
        msg = outreach.dispatch_email(db, entity_type="restaurant", entity_id=r.id, to_email=email,
                                      subject=subject, body=body, account="personal", actor="import")
        if msg.status == "Sent":
            r.status = "Sent"
            sent += 1
        _schedule_followups(db, "restaurant", r.id)
        imported += 1
    db.commit()
    log.info("Imported %d restaurants (%d sent, %d skipped)", imported, sent, skipped)
    return {"imported": imported, "sent": sent, "skipped_no_email": skipped}
