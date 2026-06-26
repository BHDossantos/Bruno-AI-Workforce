"""Execution control — the Emergency Stop kill-switch API."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import control
from ..database import get_db
from ..security import require_role

router = APIRouter(prefix="/control", tags=["control"])
_read = require_role("admin", "operator", "viewer")
_write = require_role("admin", "operator")


@router.get("/status")
def status(db: Session = Depends(get_db), _=Depends(_read)):
    return {"paused": control.is_paused_safe(db), "mode": control.get_mode(db)}


class ModeIn(BaseModel):
    mode: str  # manual | semi | auto


@router.post("/mode")
def set_mode(body: ModeIn, db: Session = Depends(get_db), _=Depends(_write)):
    """Set automation mode: 'semi' (agents draft, you approve to send — default),
    'auto' (full autopilot), or 'manual' (draft only)."""
    return {"mode": control.set_mode(db, body.mode)}


@router.post("/pause")
def pause(db: Session = Depends(get_db), _=Depends(_write)):
    """Emergency stop: immediately halt all autonomous posting, sending and agent runs."""
    return {"paused": control.set_paused(db, True)}


@router.post("/resume")
def resume(db: Session = Depends(get_db), _=Depends(_write)):
    """Release the emergency stop — agents resume on their normal schedule."""
    return {"paused": control.set_paused(db, False)}
