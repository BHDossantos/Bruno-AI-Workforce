"""Universal CRM API — one contact surface across every source + the memory graph."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import crm
from ..database import get_db
from ..security import require_role

router = APIRouter(prefix="/crm", tags=["crm"])
_read = require_role("admin", "operator", "viewer")
_write = require_role("admin", "operator")


class ContactIn(BaseModel):
    name: str
    company: str | None = None
    title: str | None = None
    email: str | None = None
    phone: str | None = None
    kind: str = "contact"
    status: str | None = None
    notes: str | None = None


@router.get("")
def list_contacts(q: str | None = None, source: str | None = None,
                  limit: int = 200, db: Session = Depends(get_db), _=Depends(_read)):
    return crm.list_contacts(db, q=q, source=source, limit=limit)


@router.post("")
def add_contact(body: ContactIn, db: Session = Depends(get_db), _=Depends(_write)):
    return crm.add_contact(db, **body.model_dump())


@router.get("/{cid}")
def get_contact(cid: str, db: Session = Depends(get_db), _=Depends(_read)):
    c = crm.get_contact(db, cid)
    if not c:
        raise HTTPException(404, "contact not found")
    return c


class NoteIn(BaseModel):
    content: str


@router.post("/{cid}/note")
def add_note(cid: str, body: NoteIn, db: Session = Depends(get_db), _=Depends(_write)):
    """Teach the workforce something about this contact (saved to the memory graph)."""
    if not body.content.strip():
        raise HTTPException(400, "empty note")
    c = crm.add_note(db, cid, body.content)
    if not c:
        raise HTTPException(404, "contact not found")
    return c


class LinkIn(BaseModel):
    to_subject: str
    relation: str = "connected_to"


@router.post("/{cid}/link")
def link_contact(cid: str, body: LinkIn, db: Session = Depends(get_db), _=Depends(_write)):
    """Connect this contact to another entity in the relationship graph."""
    if not body.to_subject.strip():
        raise HTTPException(400, "need an entity to connect to")
    c = crm.link_contact(db, cid, body.to_subject.strip(), body.relation.strip() or "connected_to")
    if not c:
        raise HTTPException(404, "contact not found")
    return c
