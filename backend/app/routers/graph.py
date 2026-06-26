"""Relationship graph API — link entities and read one-hop connections."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import graph
from ..database import get_db
from ..security import require_role

router = APIRouter(prefix="/graph", tags=["graph"])
_read = require_role("admin", "operator", "viewer")
_write = require_role("admin", "operator")


class LinkIn(BaseModel):
    from_subject: str
    to_subject: str
    relation: str
    from_type: str | None = None
    to_type: str | None = None
    note: str | None = None


@router.get("/neighbors")
def neighbors(subject: str, limit: int = 40, db: Session = Depends(get_db), _=Depends(_read)):
    return graph.neighbors(db, subject, k=limit)


@router.post("/link")
def link(body: LinkIn, db: Session = Depends(get_db), _=Depends(_write)):
    row = graph.link(db, body.from_subject, body.to_subject, body.relation,
                     from_type=body.from_type, to_type=body.to_type, note=body.note)
    if not row:
        raise HTTPException(400, "invalid edge (need distinct subjects + a relation)")
    return {"ok": True, "id": str(row.id)}


@router.delete("/{edge_id}")
def unlink(edge_id: str, db: Session = Depends(get_db), _=Depends(_write)):
    return {"ok": graph.unlink(db, edge_id)}
