"""AI Memory / Knowledge Graph API."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import memory as mem
from ..database import get_db
from ..security import require_role

router = APIRouter(prefix="/memory", tags=["memory"])
_read = require_role("admin", "operator", "viewer")
_write = require_role("admin", "operator")


class MemoryIn(BaseModel):
    content: str
    kind: str = "fact"
    subject: str | None = None
    meta: dict | None = None


@router.get("")
def list_or_search(q: str | None = None, kind: str | None = None, subject: str | None = None,
                   limit: int = 30, db: Session = Depends(get_db), _=Depends(_read)):
    return mem.search(db, q or "", k=limit, kind=kind, subject=subject)


@router.post("")
def add_memory(body: MemoryIn, db: Session = Depends(get_db), _=Depends(_write)):
    row = mem.add(db, body.content, kind=body.kind, subject=body.subject,
                  meta=body.meta, source="user")
    return mem._out(row) if row else {"ok": False, "reason": "empty"}


@router.get("/recall")
def recall(subject: str, limit: int = 10, db: Session = Depends(get_db), _=Depends(_read)):
    return mem.recall(db, subject, k=limit)
