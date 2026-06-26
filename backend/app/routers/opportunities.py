"""Universal Opportunity Engine API — capture any opportunity as a scored object
so it ranks into the same daily brief as jobs and leads."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Opportunity
from ..security import require_role

router = APIRouter(prefix="/opportunities", tags=["opportunities"])
_read = require_role("admin", "operator", "viewer")
_write = require_role("admin", "operator")

KINDS = ["investor", "podcast", "collab", "speaking", "partnership",
         "brand_deal", "press", "conference", "other"]


class OpportunityIn(BaseModel):
    title: str
    kind: str = "other"
    value: float = 0
    probability: float = 0.3
    urgency: float = 1.0
    effort: int = 2
    objective: str | None = None
    command_center: str = "business"
    link: str | None = None
    notes: str | None = None


def _out(o: Opportunity) -> dict:
    return {"id": str(o.id), "kind": o.kind, "title": o.title, "value": float(o.value or 0),
            "probability": float(o.probability or 0), "urgency": float(o.urgency or 1),
            "effort": o.effort, "objective": o.objective, "command_center": o.command_center,
            "status": o.status, "link": o.link, "notes": o.notes,
            "expected_value": round(float(o.value or 0) * float(o.probability or 0)),
            "created_at": o.created_at.isoformat() if o.created_at else None}


@router.get("")
def list_opportunities(status: str | None = None, db: Session = Depends(get_db), _=Depends(_read)):
    q = db.query(Opportunity)
    if status:
        q = q.filter(Opportunity.status == status)
    rows = q.order_by(Opportunity.created_at.desc()).limit(300).all()
    rows.sort(key=lambda o: float(o.value or 0) * float(o.probability or 0), reverse=True)
    return [_out(o) for o in rows]


@router.post("")
def create_opportunity(body: OpportunityIn, db: Session = Depends(get_db), _=Depends(_write)):
    o = Opportunity(**body.model_dump())
    db.add(o)
    db.commit()
    db.refresh(o)
    return _out(o)


class StatusIn(BaseModel):
    status: str  # Open | Won | Lost | Dismissed


@router.post("/{oid}/status")
def set_status(oid: str, body: StatusIn, db: Session = Depends(get_db), _=Depends(_write)):
    o = db.query(Opportunity).filter(Opportunity.id == oid).first()
    if not o:
        raise HTTPException(404, "opportunity not found")
    o.status = body.status
    db.commit()
    return _out(o)


@router.delete("/{oid}")
def delete_opportunity(oid: str, db: Session = Depends(get_db), _=Depends(_write)):
    o = db.query(Opportunity).filter(Opportunity.id == oid).first()
    if o:
        db.delete(o)
        db.commit()
    return {"ok": True}
