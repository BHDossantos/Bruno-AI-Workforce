"""Universal CRM — one searchable surface over every contact.

Insurance leads, restaurants, employers (from jobs), playlist curators, IG
targets, and hand-added contacts are aggregated live into a common shape, joined
to the AI memory graph. No sync table: each source stays the system of record and
the CRM reads across them, so the list is always fresh.
"""
from __future__ import annotations

from sqlalchemy import or_
from sqlalchemy.orm import Session

from . import memory
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


def list_contacts(db: Session, *, q: str | None = None, source: str | None = None,
                  limit: int = 200) -> list[dict]:
    out: list[dict] = []
    like = f"%{q}%" if q else None

    def add(model, mapper, cols, src):
        if source and source != src:
            return
        query = db.query(model)
        if like is not None:
            query = query.filter(or_(*[c.ilike(like) for c in cols]))
        for row in query.limit(limit).all():
            out.append(mapper(row))

    add(Lead, _from_lead, [Lead.company_name, Lead.owner_name, Lead.email, Lead.phone], "insurance")
    add(Restaurant, _from_restaurant, [Restaurant.name, Restaurant.owner_manager, Restaurant.email], "savorymind")
    add(Job, _from_job, [Job.company, Job.title], "career")
    add(MusicPlaylist, _from_playlist, [MusicPlaylist.curator_name, MusicPlaylist.name, MusicPlaylist.email], "music")
    add(InstagramTarget, _from_ig, [InstagramTarget.handle, InstagramTarget.niche], "influence")
    add(ManualContact, _from_contact, [ManualContact.name, ManualContact.company, ManualContact.email, ManualContact.phone], "manual")

    out.sort(key=lambda c: (c["name"] or "").lower())
    return out[:limit]


def get_contact(db: Session, cid: str) -> dict | None:
    """Resolve one aggregated contact and attach its memory-graph entries (merged
    across the contact's name AND email, so auto-captured replies show too)."""
    src = next((c for c in list_contacts(db) if c["id"] == cid), None)
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
    src = next((c for c in list_contacts(db) if c["id"] == cid), None)
    if not src:
        return None
    subject = src.get("subject") or src.get("name")
    memory.add(db, (content or "").strip(), kind="note", subject=subject, source="manual")
    return get_contact(db, cid)


def link_contact(db: Session, cid: str, to_subject: str, relation: str) -> dict | None:
    """Connect a contact to another entity in the relationship graph, then return
    the refreshed contact (with its connections)."""
    src = next((c for c in list_contacts(db) if c["id"] == cid), None)
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
    # Seed the knowledge graph so the contact is immediately searchable everywhere.
    bits = [b for b in [row.title, row.company, row.kind] if b]
    memory.add(db, f"{row.name}" + (f" — {', '.join(bits)}" if bits else ""),
               kind="contact", subject=row.name, source="crm")
    return _from_contact(row)
