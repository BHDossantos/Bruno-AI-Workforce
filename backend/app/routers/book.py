"""Client Book — post-sale insurance CRM (book of business).

A true CRM for WON clients: who they are + address, what they bought (carrier,
line, premium, policy #, dates), status, and a full communication timeline with
last-contact. Carrier dropdown is scoped to MA/NH/FL carriers but accepts free
text. Renewal radar surfaces policies expiring soon.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from .. import carriers as carriers_ref
from ..database import get_db
from ..models import Client, ClientNote, Lead
from ..security import require_role

router = APIRouter(prefix="/book", tags=["client-crm"])
_read = require_role("admin", "operator", "viewer")
_write = require_role("admin", "operator")

_EXPIRING_DAYS = 30


class ClientIn(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    line: str | None = None
    carrier: str | None = None
    policy_number: str | None = None
    premium_monthly: float | None = None
    quote_amount: float | None = None
    services: str | None = None
    status: str | None = None
    signed_at: date | None = None
    expires_at: date | None = None
    notes: str | None = None


class NoteIn(BaseModel):
    body: str
    kind: str = "note"
    author: str | None = None


def _f(v) -> float | None:
    return float(v) if v is not None else None


def _client_dict(c: Client, notes: list[ClientNote] | None = None) -> dict:
    today = date.today()
    days = (c.expires_at - today).days if c.expires_at else None
    d = {
        "id": str(c.id), "lead_id": str(c.lead_id) if c.lead_id else None,
        "name": c.name, "email": c.email, "phone": c.phone,
        "address": c.address, "city": c.city, "state": c.state, "zip": c.zip,
        "line": c.line, "carrier": c.carrier, "policy_number": c.policy_number,
        "premium_monthly": _f(c.premium_monthly), "quote_amount": _f(c.quote_amount),
        "services": c.services, "status": c.status,
        "signed_at": c.signed_at.isoformat() if c.signed_at else None,
        "expires_at": c.expires_at.isoformat() if c.expires_at else None,
        "notes": c.notes,
        "last_contacted_at": c.last_contacted_at.isoformat() if c.last_contacted_at else None,
        "days_to_expiry": days,
        "expiring_soon": days is not None and 0 <= days <= _EXPIRING_DAYS,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }
    if notes is not None:
        d["timeline"] = [{
            "id": str(n.id), "kind": n.kind, "body": n.body, "author": n.author,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        } for n in notes]
    return d


@router.get("/carriers")
def carrier_options(_=Depends(_read)):
    """Dropdown options for the CRM (MA/NH/FL carriers, lines, states, statuses)."""
    return {"carriers": carriers_ref.CARRIERS, "lines": carriers_ref.LINES,
            "states": carriers_ref.STATES, "statuses": carriers_ref.STATUSES,
            "note_kinds": carriers_ref.NOTE_KINDS}


@router.get("/clients")
def list_clients(line: str | None = None, carrier: str | None = None,
                 state: str | None = None, status: str | None = None,
                 q: str | None = None, expiring: bool = False, limit: int = 500,
                 db: Session = Depends(get_db), _=Depends(_read)):
    """The book of business, filterable by line/carrier/state/status/search, or
    only those expiring within 30 days (renewal radar)."""
    query = db.query(Client)
    if line:
        query = query.filter(Client.line == line)
    if carrier:
        query = query.filter(Client.carrier == carrier)
    if state:
        query = query.filter(Client.state == state)
    if status:
        query = query.filter(Client.status == status)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Client.name.ilike(like), Client.email.ilike(like),
                                 Client.policy_number.ilike(like), Client.city.ilike(like)))
    rows = query.order_by(Client.created_at.desc()).limit(limit).all()
    out = [_client_dict(c) for c in rows]
    if expiring:
        out = [c for c in out if c["expiring_soon"]]
    return out


@router.get("/summary")
def book_summary(db: Session = Depends(get_db), _=Depends(_read)):
    """Book-of-business KPIs: clients, active, expiring soon, monthly & annual
    premium, and breakdowns by line and carrier."""
    rows = db.query(Client).all()
    today = date.today()
    active = expiring = 0
    monthly = 0.0
    by_line: dict[str, int] = {}
    by_carrier: dict[str, int] = {}
    for c in rows:
        if (c.status or "").lower() == "active":
            active += 1
        if c.premium_monthly is not None:
            monthly += float(c.premium_monthly)
        if c.expires_at and 0 <= (c.expires_at - today).days <= _EXPIRING_DAYS:
            expiring += 1
        if c.line:
            by_line[c.line] = by_line.get(c.line, 0) + 1
        if c.carrier:
            by_carrier[c.carrier] = by_carrier.get(c.carrier, 0) + 1
    return {
        "clients": len(rows), "active": active, "expiring_soon": expiring,
        "monthly_premium": round(monthly, 2), "annual_premium": round(monthly * 12, 2),
        "by_line": by_line, "by_carrier": by_carrier,
    }


@router.post("/clients")
def create_client(body: ClientIn, db: Session = Depends(get_db), _=Depends(_write)):
    if not (body.name and body.name.strip()):
        raise HTTPException(status_code=400, detail="Client name is required")
    c = Client(**{k: v for k, v in body.model_dump().items() if v is not None})
    db.add(c)
    db.commit()
    db.refresh(c)
    return _client_dict(c, notes=[])


@router.get("/clients/{client_id}")
def get_client(client_id: str, db: Session = Depends(get_db), _=Depends(_read)):
    c = db.query(Client).filter(Client.id == client_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Client not found")
    notes = (db.query(ClientNote).filter(ClientNote.client_id == c.id)
             .order_by(ClientNote.created_at.desc()).all())
    return _client_dict(c, notes=notes)


@router.patch("/clients/{client_id}")
def update_client(client_id: str, body: ClientIn, db: Session = Depends(get_db), _=Depends(_write)):
    c = db.query(Client).filter(Client.id == client_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Client not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(c, k, v)
    db.commit()
    db.refresh(c)
    return _client_dict(c)


@router.delete("/clients/{client_id}")
def delete_client(client_id: str, db: Session = Depends(get_db), _=Depends(_write)):
    c = db.query(Client).filter(Client.id == client_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Client not found")
    db.query(ClientNote).filter(ClientNote.client_id == c.id).delete()
    db.delete(c)
    db.commit()
    return {"deleted": client_id}


@router.post("/clients/{client_id}/notes")
def add_note(client_id: str, body: NoteIn, db: Session = Depends(get_db), _=Depends(_write)):
    c = db.query(Client).filter(Client.id == client_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Client not found")
    if not (body.body and body.body.strip()):
        raise HTTPException(status_code=400, detail="Note body is required")
    kind = body.kind if body.kind in carriers_ref.NOTE_KINDS else "note"
    note = ClientNote(client_id=c.id, kind=kind, body=body.body.strip(), author=body.author)
    db.add(note)
    c.last_contacted_at = datetime.now(timezone.utc)  # a logged touch updates last-contact
    db.commit()
    db.refresh(note)
    return {"id": str(note.id), "kind": note.kind, "body": note.body,
            "author": note.author, "created_at": note.created_at.isoformat()}


@router.post("/from-lead/{lead_id}")
def from_lead(lead_id: str, db: Session = Depends(get_db), _=Depends(_write)):
    """Convert a won lead into a client record, pre-filling what we already know."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    existing = db.query(Client).filter(Client.lead_id == lead.id).first()
    if existing:
        return _client_dict(existing)
    from ..insurance_lines import line_for
    ln = line_for(lead.category, lead.segment, lead.industry)
    c = Client(
        lead_id=lead.id, name=lead.company_name or lead.owner_name or (lead.email or "New client"),
        email=lead.email, phone=lead.phone,
        line=ln if ln in carriers_ref.LINES else None,
        status="Active", signed_at=date.today())
    db.add(c)
    db.commit()
    db.refresh(c)
    return _client_dict(c, notes=[])
