"""Business/Brand registry — the config-driven source of truth for "which
businesses exist and how each one sends / books / is branded."

Today the fixed set (personal / insurance / bnb / savorymind) and its addresses,
brand names, calendars and segments are hard-coded in ~15 modules. This registry
is the seam that replaces them: one table (``businesses``) + a read API, so adding
a business becomes a Setup form entry instead of a code change.

STEP 1 (this module) only *stores + exposes* the registry, seeded from the current
settings so it mirrors live config exactly. Nothing reads it for behavior yet —
routing the send/booking/segment code through it is a later, separate step. That
ordering keeps this change safe: a new table can't break sending.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from .config import settings
from .models import Business

log = logging.getLogger("bruno.business_registry")

# Map each business to the settings it derives from + its evergreen content key.
# Values are RESOLVED from settings at seed time so the registry mirrors whatever
# is actually configured — we don't re-hard-code addresses here.
_SEED_SPEC = [
    {"key": "personal", "label": "Personal",
     "gmail_attr": "gmail_address", "from_attr": "resend_from_email",
     "name_attr": "personal_business_name", "segments": ["personal"],
     "content_key": "personal"},
    {"key": "insurance", "label": "Thrust Insurance",
     "gmail_attr": "insurance_gmail_address", "from_attr": "resend_from_insurance",
     "name_attr": "insurance_business_name", "reply_attr": "resend_reply_to",
     "calendar_attr": "calendar_link_insurance", "banner_attr": "newsletter_banner_insurance",
     "segments": ["commercial", "personal", "referral_partner"], "lead_source": "everquote",
     "content_key": "insurance"},
    {"key": "bnb", "label": "BnB Global",
     "gmail_attr": "bnb_gmail_address", "name_attr": None,
     "calendar_attr": "calendar_link_bnb", "banner_attr": "newsletter_banner_bnb",
     "segments": ["consulting"], "content_key": "bnbglobal"},
    {"key": "savorymind", "label": "SavoryMind",
     "gmail_attr": "savorymind_gmail_address", "name_attr": None,
     "calendar_attr": "calendar_link_savorymind", "banner_attr": "newsletter_banner_savorymind",
     "segments": ["restaurant"], "content_key": "savorymind"},
]


def _get(attr: str | None) -> str | None:
    if not attr:
        return None
    v = (getattr(settings, attr, "") or "").strip()
    return v or None


def _content_categories(content_key: str | None) -> list:
    """The content-factory topics for this business, if the evergreen map has them —
    read defensively so a change there can never break seeding."""
    if not content_key:
        return []
    try:
        from . import evergreen
        cats = getattr(evergreen, "BUSINESS_CATEGORIES", {}) or {}
        return list(cats.get(content_key, []) or [])
    except Exception:  # pragma: no cover - evergreen is optional here
        return []


def _seed_row(spec: dict) -> dict:
    """Resolve a seed spec into concrete column values from live settings."""
    return {
        "key": spec["key"],
        "label": spec["label"],
        "active": True,
        "gmail_address": _get(spec.get("gmail_attr")),
        "sender_from": _get(spec.get("from_attr")),
        "reply_to": _get(spec.get("reply_attr")),
        "business_name": _get(spec.get("name_attr")) or spec["label"],
        "calendar_link": _get(spec.get("calendar_attr")),
        "newsletter_banner": _get(spec.get("banner_attr")),
        "content_categories": _content_categories(spec.get("content_key")),
        "segments": list(spec.get("segments") or []),
        "lead_source": spec.get("lead_source"),
        "extra": {},
    }


def seed_defaults(db: Session) -> int:
    """Insert any default business that isn't in the table yet. Idempotent and
    non-destructive — existing rows (including future Setup-form edits) are left
    untouched. Returns how many were newly inserted."""
    existing = {b.key for b in db.query(Business.key).all()}
    added = 0
    for spec in _SEED_SPEC:
        if spec["key"] in existing:
            continue
        db.add(Business(**_seed_row(spec)))
        added += 1
    if added:
        db.commit()
        log.info("business_registry: seeded %d default business(es)", added)
    return added


def all_businesses(db: Session, *, active_only: bool = False) -> list[Business]:
    q = db.query(Business).order_by(Business.label)
    if active_only:
        q = q.filter(Business.active.is_(True))
    return q.all()


def get(db: Session, key: str) -> Business | None:
    return db.query(Business).filter(Business.key == key).first()


def serialize(b: Business) -> dict:
    return {
        "key": b.key, "label": b.label, "active": b.active,
        "gmail_address": b.gmail_address, "sender_from": b.sender_from,
        "reply_to": b.reply_to, "business_name": b.business_name,
        "calendar_link": b.calendar_link, "newsletter_banner": b.newsletter_banner,
        "content_categories": b.content_categories or [],
        "segments": b.segments or [], "lead_source": b.lead_source,
    }
