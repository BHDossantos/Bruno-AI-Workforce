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

from sqlalchemy import func
from sqlalchemy.orm import Session

from . import outreach
from .agents.base import FOLLOW_UP_OFFSETS
from .ai import client, skills
from .ai.prompts import CANDIDATE_PROFILE, CONSULTING_OUTREACH, INSURANCE_OUTREACH, SAVORYMIND_PITCH
from .models import FollowUp, Lead, ManualContact, Message, Restaurant

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


def _existing_lead(db: Session, email: str, *, consulting: bool):
    """Find a lead already in the book with this email, within the same business
    family (consulting = B&B Global; everything else = insurance) so re-importing a
    list updates rows instead of creating duplicates. Case-insensitive."""
    q = db.query(Lead).filter(func.lower(Lead.email) == email.strip().lower())
    q = q.filter(Lead.segment == "consulting") if consulting else q.filter(Lead.segment != "consulting")
    return q.order_by(Lead.created_at.asc()).first()


def process_leads_csv(db: Session, rows: list[dict]) -> dict:
    """Import insurance leads FAST. Expected columns: email (required), company_name,
    owner_name, phone, website, linkedin, industry, segment, category.

    This only parses + inserts the leads (a quick DB write) and returns immediately —
    it does NOT write the AI email or send during the upload. Writing the cold email
    is expensive (one AI call per lead) and sending is paced by the daily ramp cap,
    so both are deferred to the paced sender (bulk_outreach.dispatch_leads, run by the
    9:30am/3:30pm cron and the manual 'Send pending' action). A 2,000-row list now
    imports in a second instead of timing out the request.

    Re-importing the same list is safe: a row whose email already exists UPDATES that
    lead (refreshing any newly-provided fields) instead of creating a duplicate."""
    imported = updated = skipped = 0
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
        owner = _g(row, "owner_name", "owner", "name", *_FULLNAME_KEYS, *_FIRST_KEYS)
        phone = _g(row, "phone", *_PHONE_KEYS)
        existing = _existing_lead(db, email, consulting=False)
        if existing:
            # Refresh newly-provided fields; never clobber existing data with blanks.
            existing.company_name = company or existing.company_name
            existing.owner_name = owner or existing.owner_name
            existing.phone = phone or existing.phone
            existing.website = _g(row, "website") or existing.website
            existing.linkedin = _g(row, "linkedin") or existing.linkedin
            existing.industry = _g(row, "industry") or existing.industry
            updated += 1
            continue
        reason = (f"{category} businesses typically need liability, property and professional coverage."
                  if segment == "commercial" else f"{category} prospects often need home/auto/life coverage.")
        lead = Lead(segment=segment, category=category, company_name=company,
                    owner_name=owner, email=email,
                    phone=phone, website=_g(row, "website"),
                    linkedin=_g(row, "linkedin"), industry=_g(row, "industry"),
                    reason=reason, score=80, status="New")
        db.add(lead)
        db.flush()
        _schedule_followups(db, "lead", lead.id)
        imported += 1
    db.commit()
    log.info("Imported %d leads, updated %d (queued for paced outreach, %d skipped)",
             imported, updated, skipped)
    # sent is always 0 here — outreach goes out on the paced sender, not the upload.
    return {"imported": imported, "updated": updated, "sent": 0, "queued": imported,
            "skipped_no_email": skipped}


def draft_lead_email(db: Session, lead: Lead) -> str:
    """Write the AI cold email + call script for one lead, in place, and return the
    subject line. Shared by the paced sender so the expensive AI call happens on the
    background/send path (capped per day) — never during the CSV upload request.

    Segment-aware: 'consulting' leads (B&B Global) get the founder-led consulting
    pitch; everything else gets the insurance producer's outreach."""
    segment = (lead.segment or "commercial").lower()
    company = lead.company_name
    if segment == "consulting":
        sysp = skills.system_prompt("cold-email", "copywriting")
        art = client.complete_json(CONSULTING_OUTREACH.format(
            profile=CANDIDATE_PROFILE, company_name=company or lead.email,
            category=lead.category or "", industry=lead.industry or "", city=""), system=sysp)
        fallback = f"A quick idea for {company or 'your team'}"
    else:
        sysp = skills.system_prompt("cold-email", "marketing-psychology")
        category = lead.category or lead.industry or "Commercial"
        reason = lead.reason or (
            f"{category} businesses typically need liability, property and professional coverage."
            if segment == "commercial" else f"{category} prospects often need home/auto/life coverage.")
        art = client.complete_json(INSURANCE_OUTREACH.format(
            company_name=company or lead.email, category=category, segment=segment,
            industry=lead.industry or "", city="", reason=reason), system=sysp)
        fallback = f"Insurance options for {company or 'your business'}"
    subject = None
    if isinstance(art, dict):
        lead.cold_email = art.get("cold_email_body") or lead.cold_email
        lead.call_script = _text(art.get("call_script")) or lead.call_script
        lead.linkedin_msg = art.get("linkedin_msg") or lead.linkedin_msg
        subject = art.get("cold_email_subject")
    return subject or fallback


def process_bnb_csv(db: Session, rows: list[dict]) -> dict:
    """Import B&B Global (tech consulting) leads FAST — insert only. The paced sender
    writes the founder-led consulting email and sends it via the BnB mailbox. Expected
    columns: email (required), company_name, owner_name, phone, website, linkedin,
    industry, category. Re-importing updates existing consulting leads by email."""
    imported = updated = skipped = 0
    for row in rows:
        email = _g(row, "email", "email_address", *_EMAIL_KEYS)
        if not email:
            skipped += 1
            continue
        company = _g(row, "company_name", "company", "business", "business_name", *_COMPANY_KEYS)
        owner = _g(row, "owner_name", "owner", "name", *_FULLNAME_KEYS, *_FIRST_KEYS)
        phone = _g(row, "phone", *_PHONE_KEYS)
        existing = _existing_lead(db, email, consulting=True)
        if existing:
            existing.company_name = company or existing.company_name
            existing.owner_name = owner or existing.owner_name
            existing.phone = phone or existing.phone
            existing.website = _g(row, "website") or existing.website
            existing.linkedin = _g(row, "linkedin") or existing.linkedin
            existing.industry = _g(row, "industry") or existing.industry
            updated += 1
            continue
        lead = Lead(segment="consulting", category=_g(row, "category", "industry") or "Technology",
                    company_name=company, owner_name=owner,
                    email=email, phone=phone, website=_g(row, "website"),
                    linkedin=_g(row, "linkedin"), industry=_g(row, "industry"),
                    score=80, status="New")
        db.add(lead)
        db.flush()
        _schedule_followups(db, "lead", lead.id)
        imported += 1
    db.commit()
    log.info("Imported %d BnB leads, updated %d (queued, %d skipped)", imported, updated, skipped)
    return {"imported": imported, "updated": updated, "sent": 0, "queued": imported,
            "skipped_no_email": skipped}


def process_restaurants_csv(db: Session, rows: list[dict]) -> dict:
    """Import SavoryMind restaurant prospects FAST — insert only. The paced sender
    writes the SavoryMind pitch and sends it. Expected columns: email (required),
    name, owner_manager, phone, website, instagram, cuisine, city. Re-importing
    updates an existing prospect by email instead of duplicating it."""
    imported = updated = skipped = 0
    for row in rows:
        email = _g(row, "email", "email_address", *_EMAIL_KEYS)
        if not email:
            skipped += 1
            continue
        name = _g(row, "name", "restaurant", "restaurant_name", "company_name", *_FULLNAME_KEYS, *_COMPANY_KEYS) or email
        existing = (db.query(Restaurant).filter(Restaurant.kind == "prospect",
                    func.lower(Restaurant.email) == email.strip().lower()).first())
        if existing:
            existing.owner_manager = _g(row, "owner_manager", "owner", "manager") or existing.owner_manager
            existing.phone = _g(row, "phone") or existing.phone
            existing.website = _g(row, "website") or existing.website
            existing.instagram = _g(row, "instagram") or existing.instagram
            existing.cuisine = _g(row, "cuisine") or existing.cuisine
            existing.city = _g(row, "city") or existing.city
            updated += 1
            continue
        r = Restaurant(kind="prospect", name=name, owner_manager=_g(row, "owner_manager", "owner", "manager"),
                       website=_g(row, "website"), instagram=_g(row, "instagram"), email=email,
                       phone=_g(row, "phone"), cuisine=_g(row, "cuisine"), city=_g(row, "city"),
                       status="New")
        db.add(r)
        db.flush()
        _schedule_followups(db, "restaurant", r.id)
        imported += 1
    db.commit()
    log.info("Imported %d SavoryMind prospects, updated %d (queued, %d skipped)",
             imported, updated, skipped)
    return {"imported": imported, "updated": updated, "sent": 0, "queued": imported,
            "skipped_no_email": skipped}


def draft_restaurant_email(db: Session, r: Restaurant) -> str:
    """Write the AI SavoryMind pitch for one restaurant, in place, and return the
    subject. Runs on the paced sender, not during the CSV upload."""
    sysp = skills.system_prompt("copywriting", "cold-email")
    art = client.complete_json(SAVORYMIND_PITCH.format(
        name=r.name, cuisine=r.cuisine or "restaurant", city=r.city or "",
        owner=r.owner_manager or "", insight="grow revenue with menu intelligence"), system=sysp)
    subject = None
    if isinstance(art, dict):
        r.pitch_email = art.get("pitch_body") or r.pitch_email
        r.linkedin_msg = art.get("linkedin_msg") or r.linkedin_msg
        r.follow_up = art.get("demo_invite") or r.follow_up
        subject = art.get("pitch_subject")
    return subject or f"Growing revenue at {r.name} with SavoryMind"


def dedupe_leads(db: Session) -> dict:
    """One-time cleanup for duplicate leads (e.g. a list re-imported several times).
    Groups leads by email within a business family (consulting vs insurance) and keeps
    ONE per group — preferring the most-worked row (engaged status › has a written
    email › has sent/queued messages › most contacts › oldest) so no history is lost.
    Merges the contact count onto the keeper, then deletes the extras and their
    scheduled follow-ups. Returns how many groups were deduped and rows removed."""
    from collections import defaultdict

    groups: dict[tuple[str, str], list[Lead]] = defaultdict(list)
    for lead in db.query(Lead).filter(Lead.email.isnot(None), Lead.email != "").all():
        family = "consulting" if (lead.segment or "").lower() == "consulting" else "insurance"
        groups[((lead.email or "").strip().lower(), family)].append(lead)

    def _rank(l: Lead) -> tuple:
        engaged = (l.status or "").strip().lower() not in ("", "new", "drafted", "skipped")
        has_msg = db.query(Message.id).filter(
            Message.entity_type == "lead", Message.entity_id == l.id).first() is not None
        return (engaged, bool((l.cold_email or "").strip()), has_msg,
                l.times_contacted or 0, -(l.score or 0))

    deduped = removed = 0
    for (_email, _family), rows in groups.items():
        if len(rows) < 2:
            continue
        keeper = max(rows, key=_rank)
        for l in rows:
            if l.id == keeper.id:
                continue
            keeper.times_contacted = max(keeper.times_contacted or 0, l.times_contacted or 0)
            db.query(FollowUp).filter(FollowUp.entity_type == "lead",
                                      FollowUp.entity_id == l.id).delete(synchronize_session=False)
            db.delete(l)
            removed += 1
        deduped += 1
    db.commit()
    log.info("Deduped %d lead groups, removed %d duplicate leads", deduped, removed)
    return {"ok": True, "groups_deduped": deduped, "removed": removed}
