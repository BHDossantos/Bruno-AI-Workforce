"""Automation rules API — view and toggle the event-driven branching rules."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import automation
from ..database import get_db
from ..security import require_role

router = APIRouter(prefix="/automations", tags=["automations"])


@router.get("")
def list_rules(db: Session = Depends(get_db),
              _=Depends(require_role("admin", "operator", "viewer"))):
    """Every automation rule with its trigger, action, and on/off state."""
    return automation.list_rules(db)


class ToggleIn(BaseModel):
    key: str
    on: bool


@router.post("/toggle")
def toggle(body: ToggleIn, db: Session = Depends(get_db),
           _=Depends(require_role("admin", "operator"))):
    ok = automation.set_enabled(db, body.key, body.on)
    return {"ok": ok, "key": body.key, "enabled": body.on if ok else None}
