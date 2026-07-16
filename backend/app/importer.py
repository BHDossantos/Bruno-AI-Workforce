"""CSV lead/restaurant importer.

Lets the user bring real, owned contact lists. Each imported row becomes a Lead
or Restaurant, gets a personalized email written with the marketing skills, is
dispatched via the right Gmail account (respecting send/draft mode + the
real-email guard + daily cap), and gets the full follow-up sequence scheduled.
"""
from __future__ import annotations

import logging
import re
from datetime import date, timedelta

from sqlalchemy.orm import Session

from . import outreach
from .agents.base import FOLLOW_UP_OFFSETS
from .ai import client, skills
from .ai.prompts import INSURANCE_OUTREACH, SAVORYMIND_PITCH
from .models import FollowUp, Lead, ManualContact, Restaurant

log = logging.getLogger("bruno.importer")


def _norm_key(k: str) -> str:
    """Normalize a header to letters+digits only, so 'E-mail 1 - Value',
    'E-mail Address', 'Email Address' and 'email_address' all collapse together."""
    return re.sub(r"[^a-z0-9]", "", (k or "").lower())


def _g(row: dict, *keys: str) -> str | None:
    """Get a value across header variants from ANY export (Google, iPhone/vCard,
    Outlook, LinkedIn). Matching ignores case, spaces, hyphens and underscores.
    Multi-value Google fields ('a ::: b') return the first value."""
    norm = {_norm_key(k): v for k, v in row.items()}
    for k in keys:
        v = norm.get(_norm_key(k))
        if v and str(v).strip():
            return str(v).split(":::")[0].strip()
    return None


# Candidate header names per field, spanning every common contact export.
_EMAIL_KEYS = ("email", "email address", "e-mail address", "email_address",
               "e-mail 1 - value", "email 1 - value", "e-mail 2 - value", "primary email")
_PHONE_KEYS = ("phone", "phone 1 - value", "phone 2 - value", "mobile phone", "mobile",
               "home phone", "business phone", "work phone", "primary phone", "tel")
_FIRST_KEYS = ("first name", "given name")
_LAST_KEYS = ("last name", "family name", "surname")
_FULLNAME_KEYS = ("name", "display name", "file as", "full name")
_COMPANY_KEYS = ("company", "organization name", "organization", "organisation", "employer")
_TITLE_KEYS = ("title", "job title", "organization title", "position", "role")


def normalize_contact(row: dict) -> dict:
    """Map one row from any platform's export to a common contact shape."""
    name = " ".join(p for p in [_g(row, *_FIRST_KEYS), _g(row, "middle name"),
                                _g(row, *_LAST_KEYS)] if p)
    name = name or _g(row, *_FULLNAME_KEYS) or _g(row, *_COMPANY_KEYS)
    return {
        "name": name,
        "email": _g(row, *_EMAIL_KEYS),
        "phone": _g(row, *_PHONE_KEYS),
        "company": _g(row, *_COMPANY_KEYS),
        "title": _g(row, *_TITLE_KEYS),
        "notes": _g(row, "notes", "note"),
    }


def _unfold_vcard(text: str) -> list[str]:
    """RFC 6350 line unfolding: a line starting with space/tab continues the prior
    one. iCloud wraps long EMAIL/FN values, so without this they get truncated."""
    out: list[str] = []
    for raw in (text or "").splitlines():
        if raw[:1] in (" ", "\t") and out:
            out[-1] += raw[1:]          # continuation → append (keep inner content)
        else:
            out.append(raw)
    return [ln.strip() for ln in out]


def parse_vcards(text: str) -> list[dict]:
    """Parse an Apple/iCloud/iPhone vCard (.vcf) export into row dicts compatible
    with normalize_contact (keys: name, email, phone, company, title, notes).
    Handles folded continuation lines and Apple item-group prefixes (item1.EMAIL)."""
    cards: list[dict] = []
    cur: dict = {}
    for line in _unfold_vcard(text):
        if line.upper() == "BEGIN:VCARD":
            cur = {}
        elif line.upper() == "END:VCARD":
            if cur:
                cards.append(cur)
            cur = {}
        elif ":" in line:
            head, _, val = line.partition(":")
            # strip TYPE params (TEL;CELL) AND Apple item-group prefixes (item1.EMAIL).
            prop = head.split(";")[0].split(".")[-1].upper()
            val = val.strip()
            if not val:
                continue
            if prop == "FN":
                cur.setdefault("name", val)
            elif prop == "N" and "name" not in cur:
                parts = [p.strip() for p in val.split(";")]
                cur["name"] = " ".join(p for p in [parts[1] if len(parts) > 1 else "",
                                                   parts[0] if parts else ""] if p)
            elif prop == "EMAIL":
                cur.setdefault("email", val)
            elif prop == "TEL":
                cur.setdefault("phone", val)
            elif prop == "ORG":
                cur.setdefault("company", val.split(";")[0].strip())
            elif prop == "TITLE":
                cur.setdefault("title", val)
            elif prop == "NOTE":
                cur.setdefault("notes", val)
    return cards


def process_contacts_csv(db: Session, rows: list[dict]) -> dict:
    """Import a personal contact list (e.g. a Google Contacts export).

    Each contact becomes (a) a ManualContact, worked by the warm insurance
    contacts-outreach engine, AND (b) a visible personal Lead so it shows up on
    the Leads/Insurance page (the user's mental model is "these are my leads").
    The Lead is created with status 'contact' (a non-pending status) so the bulk
    cold-email path never double-sends — the warm contacts_outreach engine stays
    the single sender. Family / opt-out emails are skipped entirely from both.
    Handles Google's 'First Name', 'E-mail 1 - Value', 'Phone 1 - Value',
    'Organization Name/Title' columns."""
    from . import contacts_outreach
    exclude = contacts_outreach._exclude_set()
    imported = leads_added = skipped = 0
    seen: set[str] = set()
    existing = {e.lower() for (e,) in db.query(ManualContact.email)
                .filter(ManualContact.email.isnot(None)).all()}
    existing_leads = {e.lower() for (e,) in db.query(Lead.email)
                      .filter(Lead.email.isnot(None)).all()}
    for row in rows:
        c = normalize_contact(row)
        email, phone = c["email"], c["phone"]
        if not email and not phone:
            skipped += 1  # nothing actionable
            continue
        name = c["name"] or email or phone
        dedupe = (email or "").lower() or f"{name}|{phone}".lower()
        if dedupe in seen or (email and email.lower() in existing):
            skipped += 1
            continue
        seen.add(dedupe)
        db.add(ManualContact(
            name=name, email=email, phone=phone,
            company=c["company"], title=c["title"],
            kind="contact", notes=c["notes"]))
        imported += 1
        # Surface as a personal Lead too (visibility), unless it's an excluded
        # (family/opt-out) address or already a lead.
        elow = (email or "").lower()
        if elow and elow not in exclude and elow not in existing_leads:
            existing_leads.add(elow)
            db.add(Lead(segment="personal", category="Personal contact",
                        owner_name=name, email=email, phone=phone,
                        company_name=c["company"], industry=c["title"],
                        reason="Imported personal contact — warm insurance network.",
                        score=70, status="contact"))
            leads_added += 1
        if imported % 500 == 0:
            db.commit()
    db.commit()
    log.info("Imported %d contacts (%d as leads, %d skipped)", imported, leads_added, skipped)
    ok = imported > 0
    reason = None
    if not ok:
        reason = ("No contacts could be read. Make sure you uploaded a contacts export "
                  "(Google/Outlook/LinkedIn CSV or an iCloud .vcf) with email or phone "
                  f"columns — {skipped} row(s) had nothing usable." if rows
                  else "The file was empty or unreadable.")
    return {"ok": ok, "imported": imported, "leads_added": leads_added,
            "skipped": skipped, "reason": reason}


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
    """Import insurance leads FAST. Expected columns: email (required), company_name,
    owner_name, phone, website, linkedin, industry, segment, category.

    This only parses + inserts the leads (a quick DB write) and returns immediately —
    it does NOT write the AI email or send during the upload. Writing the cold email
    is expensive (one AI call per lead) and sending is paced by the daily ramp cap,
    so both are deferred to the paced sender (bulk_outreach.dispatch_leads, run by the
    9:30am/3:30pm cron and the manual 'Send pending' action). A 2,000-row list now
    imports in a second instead of timing out the request."""
    imported = skipped = 0
    for row in rows:
        # Match ANY email-column naming (not just a literal "email" header), so a
        # file exported from Google/Outlook/etc. and imported as "leads" doesn't
        # silently import 0 rows just because the header isn't exactly "email".
        email = _g(row, "email", "email_address", *_EMAIL_KEYS)
        if not email:
            skipped += 1
            continue
        segment = (_g(row, "segment") or "commercial").lower()
        category = _g(row, "category", "industry") or "Commercial"
        company = _g(row, "company_name", "company", "business", "business_name", *_COMPANY_KEYS)
        reason = (f"{category} businesses typically need liability, property and professional coverage."
                  if segment == "commercial" else f"{category} prospects often need home/auto/life coverage.")
        lead = Lead(segment=segment, category=category, company_name=company,
                    owner_name=_g(row, "owner_name", "owner", "name", *_FULLNAME_KEYS, *_FIRST_KEYS), email=email,
                    phone=_g(row, "phone", *_PHONE_KEYS), website=_g(row, "website"),
                    linkedin=_g(row, "linkedin"), industry=_g(row, "industry"),
                    reason=reason, score=80, status="New")
        db.add(lead)
        db.flush()
        _schedule_followups(db, "lead", lead.id)
        imported += 1
    db.commit()
    log.info("Imported %d leads (queued for paced outreach, %d skipped)", imported, skipped)
    # sent is always 0 here — outreach goes out on the paced sender, not the upload.
    return {"imported": imported, "sent": 0, "queued": imported, "skipped_no_email": skipped}


def draft_lead_email(db: Session, lead: Lead) -> str:
    """Write the AI cold email + call script for one lead, in place, and return the
    subject line. Shared by the paced sender so the expensive AI call happens on the
    background/send path (capped per day) — never during the CSV upload request."""
    sysp = skills.system_prompt("cold-email", "marketing-psychology")
    segment = (lead.segment or "commercial").lower()
    category = lead.category or lead.industry or "Commercial"
    company = lead.company_name
    reason = lead.reason or (
        f"{category} businesses typically need liability, property and professional coverage."
        if segment == "commercial" else f"{category} prospects often need home/auto/life coverage.")
    art = client.complete_json(INSURANCE_OUTREACH.format(
        company_name=company or lead.email, category=category, segment=segment,
        industry=lead.industry or "", city="", reason=reason), system=sysp)
    subject = None
    if isinstance(art, dict):
        lead.cold_email = art.get("cold_email_body") or lead.cold_email
        lead.call_script = _text(art.get("call_script")) or lead.call_script
        lead.linkedin_msg = art.get("linkedin_msg") or lead.linkedin_msg
        subject = art.get("cold_email_subject")
    return subject or f"Insurance options for {company or 'your business'}"


def process_restaurants_csv(db: Session, rows: list[dict]) -> dict:
    """Import restaurants. Expected columns: email (required), name, owner_manager,
    phone, website, instagram, cuisine, city."""
    sysp = skills.system_prompt("copywriting", "cold-email")
    imported = sent = skipped = 0
    for row in rows:
        email = _g(row, "email", "email_address", *_EMAIL_KEYS)
        if not email:
            skipped += 1
            continue
        name = _g(row, "name", "restaurant", "restaurant_name", "company_name", *_FULLNAME_KEYS, *_COMPANY_KEYS) or email
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
        # Only dispatch with a real AI body — never send an empty pitch.
        if body:
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
