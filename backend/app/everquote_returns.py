"""EverQuote-valid lead returns.

EverQuote lets you return certain leads for credit — but only for specific,
legitimate reasons: invalid / disconnected phone, invalid (bad/undeliverable)
email, duplicate lead, or a lead outside your configured footprint. It does NOT
allow a return just because a consumer says "I didn't request this."

This scans imported EverQuote leads, detects those valid reasons, and prepares
the return-reason text so a return is one click. (Reviving no-reply dead-ends is
a different thing — see lead_return.py — and is NOT a return.)
"""
from __future__ import annotations

import logging
import re

from sqlalchemy.orm import Session

from . import everquote
from .config import settings
from .models import Lead
from .outreach import is_real_email

log = logging.getLogger("bruno.eqreturns")

# Map the footprint scope (state names) to the abbreviations EverQuote sends.
_STATE_ABBR = {
    "massachusetts": "MA", "new hampshire": "NH", "florida": "FL", "maine": "ME",
    "vermont": "VT", "connecticut": "CT", "rhode island": "RI", "new york": "NY",
}
# Scope tokens that mean "no per-state footprint limit" — skip out-of-footprint.
_BROAD_SCOPE = {"us", "usa", "eu", "us_eu", "all", ""}


def _allowed_states() -> set[str] | None:
    raw = (settings.insurance_lead_scope or "").strip().lower()
    if raw in _BROAD_SCOPE:
        return None  # no footprint restriction configured
    out: set[str] = set()
    for tok in raw.split(","):
        t = tok.strip()
        if len(t) == 2:
            out.add(t.upper())
        elif t in _STATE_ABBR:
            out.add(_STATE_ABBR[t])
    return out or None


def _digits(phone: str | None) -> str:
    return re.sub(r"\D", "", phone or "")


def _phone_invalid(phone: str | None) -> bool:
    d = _digits(phone)
    if not d:
        return True
    if len(d) not in (10, 11):
        return True
    core = d[-10:]
    if len(set(core)) == 1:        # 0000000000, 1111111111 …
        return True
    if core[0] in "01":            # US area codes never start 0 or 1
        return True
    return False


def return_candidates(db: Session, limit: int = 500) -> list[dict]:
    """EverQuote leads eligible for a valid return, with a prepared reason each."""
    leads = (db.query(Lead).filter(Lead.intake["source"].astext == "everquote")
             .limit(limit).all())
    allowed = _allowed_states()

    # Duplicate detection across the EverQuote set (same email or phone twice+).
    seen_email: dict[str, int] = {}
    seen_phone: dict[str, int] = {}
    for l in leads:
        if l.email:
            seen_email[l.email.lower()] = seen_email.get(l.email.lower(), 0) + 1
        d = _digits(l.phone)
        if d:
            seen_phone[d] = seen_phone.get(d, 0) + 1

    out = []
    for l in leads:
        f = (l.intake or {}).get("everquote") or {}
        name = l.owner_name or l.email or "Lead"
        state = (f.get("state") or "").upper()
        reason_code = reason_text = None

        if _phone_invalid(l.phone):
            reason_code = "invalid_phone"
            reason_text = ("Invalid / disconnected phone number — the number on file is not a "
                           "reachable 10-digit US line.")
        elif l.email and not is_real_email(l.email):
            reason_code = "invalid_email"
            reason_text = "Invalid email address — undeliverable / not a real address."
        elif l.email and seen_email.get(l.email.lower(), 0) > 1:
            reason_code = "duplicate"
            reason_text = f"Duplicate lead — the same email ({l.email}) appears on multiple leads."
        elif _digits(l.phone) and seen_phone.get(_digits(l.phone), 0) > 1:
            reason_code = "duplicate"
            reason_text = "Duplicate lead — the same phone number appears on multiple leads."
        elif allowed is not None and state and state not in allowed:
            reason_code = "out_of_footprint"
            reason_text = (f"Outside your configured footprint — this lead is in {state}, "
                           f"which isn't in your writing area ({', '.join(sorted(allowed))}).")

        if reason_code:
            out.append({
                "lead_id": str(l.id), "name": name, "email": l.email, "phone": l.phone,
                "state": state, "vehicle": " ".join(p for p in [
                    str(f.get("vehicle_year") or ""), f.get("vehicle_make") or "",
                    everquote.model_case(f.get("vehicle_model"))] if p).strip(),
                "reason_code": reason_code, "reason_text": reason_text,
                "eq_uuid": f.get("eq_uuid"),
            })
    return out


def summary(db: Session) -> dict:
    return {"eq_return_candidates": len(return_candidates(db, limit=10_000))}
