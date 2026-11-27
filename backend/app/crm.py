"""Universal CRM — one searchable surface over every contact.

Insurance leads, restaurants, employers (from jobs), playlist curators, IG
targets, and hand-added contacts are aggregated live into a common shape, joined
to the AI memory graph. No sync table: each source stays the system of record and
the CRM reads across them, so the list is always fresh.
"""
from __future__ import annotations

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from . import memory
from .import_phone_key import import_phone_key
from .models import InstagramTarget, Job, Lead, ManualContact, MusicPlaylist, Restaurant

# Each source: (cid prefix, model, row->contact mapper, searchable columns, source label)
SOURCES = ["insurance", "savorymind", "career", "music", "influence", "manual"]


def _c(cid, name, **kw) -> dict:
    base = {"id": cid, "name": name, "company": None, "title": None, "email": None,
            "phone": None, "status": None, "source": None, "link": "#"}
    base.update(kw)
    return base


def _from_lead(l: Lead) -> dict:
    return _c(f"lead:{l.id}", l.company_name or l.owner_name or "Unknown",
              company=l.company_name, title=l.owner_name, email=l.email, phone=l.phone,
              status=l.status, source="insurance", link="/insurance",
              kind="Insurance Lead", subject=l.company_name or l.owner_name)


def _from_restaurant(r: Restaurant) -> dict:
    return _c(f"restaurant:{r.id}", r.name, company=r.name, title=r.owner_manager,
              email=r.email, phone=r.phone, status=r.status, source="savorymind",
              link="/savorymind", kind="Restaurant", subject=r.name)


def _from_job(j: Job) -> dict:
    return _c(f"job:{j.id}", j.company, company=j.company, title=j.title,
              status=None, source="career", link=j.url or "/apply",
              kind="Employer", subject=j.company)


def _from_playlist(p: MusicPlaylist) -> dict:
    return _c(f"playlist:{p.id}", p.curator_name or p.name, company=p.name,
              title="Curator", email=p.email, status=p.status, source="music",
              link="/music", kind="Playlist Curator", subject=p.curator_name or p.name)


def _from_ig(t: InstagramTarget) -> dict:
    return _c(f"ig:{t.id}", t.handle, title=t.niche, status=t.status,
              source="influence", link="/instagram", kind="IG Target", subject=t.handle)


def _from_contact(c: ManualContact) -> dict:
    return _c(f"contact:{c.id}", c.name, company=c.company, title=c.title,
              email=c.email, phone=c.phone, status=c.status, source="manual",
              link="/crm", kind=c.kind, subject=c.name)


# Keep this a read-only search normalization: neither stored data nor delivery
# destinations change. Use functions supported by PostgreSQL and SQLite.
_PHONE_SEPARATORS = " +().-\t\u00a0\u202f"


def _phone_search_keys(term: str | None) -> tuple[str, ...]:
    term = (term or "").strip()
    digits = term.translate(str.maketrans("", "", _PHONE_SEPARATORS))
    if not digits.isascii() or not digits.isdecimal() or not 7 <= len(digits) <= 17:
        return ()
    if digits.startswith("00"):
        country_number = digits[2:]
        if not 7 <= len(country_number) <= 15:
            return ()
        if len(country_number) == 11 and country_number.startswith("1"):
            return (digits, country_number, country_number[1:])
        return (digits, country_number)
    keys = [digits]
    if term.startswith("+"):
        # Explicit country codes stay intact, except that North American +1
        # can match a stored domestic number without the 1.
        keys.append("00" + digits)
        if len(digits) == 11 and digits.startswith("1"):
            keys.append(digits[1:])
    elif len(digits) == 10 and digits[0] in "23456789":
        keys.extend(("1" + digits, "001" + digits))
    elif len(digits) == 11 and digits.startswith("1"):
        keys.extend((digits[1:], "00" + digits))
    return tuple(keys)


def _phone_filter(column, keys: tuple[str, ...]):
    normalized = column
    for separator in _PHONE_SEPARATORS:
        normalized = func.replace(normalized, separator, "")
    return normalized.in_(keys)


def list_contacts(db: Session, *, q: str | None = None, source: str | None = None,
                  limit: int = 200) -> list[dict]:
    out: list[dict] = []
    like = f"%{q}%" if q else None
    phone_keys = _phone_search_keys(q)

    def add(model, mapper, cols, src, phone=None):
        if source and source != src:
            return
        query = db.query(model)
        if like is not None:
            predicates = [c.ilike(like) for c in cols]
            if phone is not None:
                if phone_keys:
                    predicates.append(_phone_filter(phone, phone_keys))
                    if not q.strip().startswith(("+", "00")) and len(phone_keys[0]) < 10:
                        predicates.append(phone.ilike(like))  # preserve partial local lookup
                else:
                    predicates.append(phone.ilike(like))
            query = query.filter(or_(*predicates))
        for row in query.limit(limit).all():
            out.append(mapper(row))

    add(Lead, _from_lead, [Lead.company_name, Lead.owner_name, Lead.email], "insurance", phone=Lead.phone)
    add(Restaurant, _from_restaurant, [Restaurant.name, Restaurant.owner_manager, Restaurant.email], "savorymind")
    add(Job, _from_job, [Job.company, Job.title], "career")
    add(MusicPlaylist, _from_playlist, [MusicPlaylist.curator_name, MusicPlaylist.name, MusicPlaylist.email], "music")
    add(InstagramTarget, _from_ig, [InstagramTarget.handle, InstagramTarget.niche], "influence")
    add(ManualContact, _from_contact, [ManualContact.name, ManualContact.company, ManualContact.email], "manual", phone=ManualContact.phone)

    out.sort(key=lambda c: (c["name"] or "").lower())
    return out[:limit]


# cid prefix -> (model, row->contact mapper), for an O(1) exact lookup that
# never depends on the aggregated list's sort order or page size.
_PREFIX_MAP = {
    "lead": (Lead, _from_lead), "restaurant": (Restaurant, _from_restaurant),
    "job": (Job, _from_job), "playlist": (MusicPlaylist, _from_playlist),
    "ig": (InstagramTarget, _from_ig), "contact": (ManualContact, _from_contact),
}


def _find_by_cid(db: Session, cid: str) -> dict | None:
    """Resolve a single contact by its exact id. `list_contacts` sorts and caps
    at `limit` across every source combined — scanning it for one id meant a
    contact could silently vanish ("not found") once enough OTHER contacts
    existed anywhere in the system, regardless of how recently it was added."""
    prefix, sep, raw_id = (cid or "").partition(":")
    entry = _PREFIX_MAP.get(prefix) if sep else None
    if not entry:
        return None
    model, mapper = entry
    try:
        row = db.query(model).filter(model.id == raw_id).first()
    except Exception:  # malformed/non-UUID id -> not found, not a 500
        return None
    return mapper(row) if row else None


def get_contact(db: Session, cid: str) -> dict | None:
    """Resolve one aggregated contact and attach its memory-graph entries (merged
    across the contact's name AND email, so auto-captured replies show too)."""
    src = _find_by_cid(db, cid)
    if not src:
        return None
    subject = src.get("subject") or src.get("name")
    src["memories"] = memory.recall_entity(db, name=subject, email=src.get("email"), k=25)
    from . import graph
    src["connections"] = graph.neighbors(db, subject)
    return src


def add_note(db: Session, cid: str, content: str) -> dict | None:
    """Teach the workforce something about a contact — saved to the memory graph
    under the contact's name so every agent recalls it from now on."""
    src = _find_by_cid(db, cid)
    if not src:
        return None
    subject = src.get("subject") or src.get("name")
    memory.add(db, (content or "").strip(), kind="note", subject=subject, source="manual")
    return get_contact(db, cid)


def link_contact(db: Session, cid: str, to_subject: str, relation: str) -> dict | None:
    """Connect a contact to another entity in the relationship graph, then return
    the refreshed contact (with its connections)."""
    src = _find_by_cid(db, cid)
    if not src:
        return None
    from . import graph
    subject = src.get("subject") or src.get("name")
    graph.link(db, subject, to_subject, relation, from_type=src.get("kind"))
    return get_contact(db, cid)


def add_contact(db: Session, **fields) -> dict:
    row = ManualContact(**{k: v for k, v in fields.items() if v is not None})
    db.add(row)
    db.commit()
    db.refresh(row)
    saved = _from_contact(row)
    # The primary write is already durable. Search memory has its own transaction
    # and must not turn a confirmed save into an apparent failure.
    bits = [b for b in [row.title, row.company, row.kind] if b]
    try:
        memory.add(db, f"{row.name}" + (f" — {', '.join(bits)}" if bits else ""),
                   kind="contact", subject=row.name, source="crm")
    except Exception:
        import logging

        log = logging.getLogger(__name__)
        log.warning("CRM contact saved; optional search memory update failed")
        try:
            db.rollback()
        except Exception:
            # The request dependency closes the session; keep the saved response
            # even if a broken connection also prevents rollback.
            log.warning("CRM optional search memory transaction cleanup failed")
    return saved


class ContactIdentityConflict(Exception):
    """A manual contact does not safely identify exactly one existing lead."""


def _promotion_match(db: Session, email: str | None, phone: str | None) -> Lead | None:
    email = (email or "").strip().lower()
    key = import_phone_key(phone)
    if (phone or "").strip() and not key:
        raise ContactIdentityConflict("This contact's phone could not be matched safely. Check its full number.")

    emails = db.query(Lead).filter(func.lower(func.trim(Lead.email)) == email).limit(2).all() if email else []
    phone_ids = []
    if key:
        for lead_id, number in db.query(Lead.id, Lead.phone).filter(Lead.phone.isnot(None)).yield_per(500):
            if import_phone_key(number) == key:
                phone_ids.append(lead_id)
                if len(phone_ids) == 2:
                    break

    conflict = "This contact matches conflicting lead records. Review its email and phone before adding it to the Call List."
    if len(emails) > 1 or len(phone_ids) > 1 or (emails and phone_ids and emails[0].id != phone_ids[0]):
        raise ContactIdentityConflict(conflict)
    lead = emails[0] if emails else db.get(Lead, phone_ids[0]) if phone_ids else None
    if phone_ids and lead is None:
        raise ContactIdentityConflict(conflict)
    if lead and (lead.segment not in ("commercial", "personal")
            or (email and (lead.email or "").strip() and lead.email.strip().lower() != email)
            or (key and (lead.phone or "").strip() and import_phone_key(lead.phone) != key)):
        raise ContactIdentityConflict(conflict)
    return lead


def promote_to_lead(db: Session, cid: str) -> str | None:
    """Make a hand-added contact callable: create (or reuse) a Lead from a
    'contact:' entry so it gains the Call/Text toolbar and shows up in the Call
    List. Returns the lead id, or None if ``cid`` isn't a manual contact. Reuses an
    existing lead with the same email/phone so this never duplicates the book."""
    prefix, sep, raw = (cid or "").partition(":")
    if not sep or prefix != "contact":
        return None
    try:
        c = db.query(ManualContact).filter(ManualContact.id == raw).with_for_update().first()
    except Exception:  # malformed id → not found, not a 500
        return None
    if c is None:
        return None
    lead = _promotion_match(db, c.email, c.phone)
    if lead is None:
        lead = Lead(segment="commercial", category=(c.kind or "contact").title(),
                    company_name=c.company or c.name, owner_name=c.name,
                    email=c.email or None, phone=c.phone, status="New", score=80,
                    reason="Added from your contacts to reach out directly.")
        db.add(lead)
        db.commit()
        db.refresh(lead)
    return str(lead.id)
