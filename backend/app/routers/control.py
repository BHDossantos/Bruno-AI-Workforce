"""Execution control — the Emergency Stop kill-switch API."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import control
from ..database import get_db
from ..security import require_role

router = APIRouter(prefix="/control", tags=["control"])
_read = require_role("admin", "operator", "viewer")
_write = require_role("admin", "operator")


@router.get("/status")
def status(db: Session = Depends(get_db), _=Depends(_read)):
    return {"paused": control.is_paused_safe(db)}


@router.post("/pause")
def pause(db: Session = Depends(get_db), _=Depends(_write)):
    """Emergency stop: immediately halt all autonomous posting, sending and agent runs."""
    return {"paused": control.set_paused(db, True)}


@router.post("/resume")
def resume(db: Session = Depends(get_db), _=Depends(_write)):
    """Release the emergency stop — agents resume on their normal schedule."""
    return {"paused": control.set_paused(db, False)}
