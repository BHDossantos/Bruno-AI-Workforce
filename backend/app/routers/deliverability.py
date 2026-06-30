"""Deliverability dashboard routes.

One screen to see whether email is actually going out (channel, sends today vs
cap, backlog, per-mailbox breakdown, recent failures) and one button to drain the
whole outbox now.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import deliverability
from ..database import get_db
from ..security import require_role

router = APIRouter(prefix="/deliverability", tags=["deliverability"])
_read = require_role("admin", "operator", "viewer")
_write = require_role("admin", "operator")


@router.get("")
def get_deliverability(db: Session = Depends(get_db), _=Depends(_read)):
    """Sending health: active channel, sends today vs cap, backlog, per-mailbox, failures."""
    return deliverability.snapshot(db)


@router.post("/send-now")
def send_now(db: Session = Depends(get_db), _=Depends(_write)):
    """Send every queued lead + restaurant prospect right now (respects caps/pause)."""
    return deliverability.send_pending_now(db)
