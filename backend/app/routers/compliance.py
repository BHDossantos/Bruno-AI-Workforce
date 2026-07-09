"""Compliance & Governance API — the dashboard for the compliance gate.

Read the current governance posture, the immutable audit log, the human-review
queue, and manage the Do-Not-Contact suppression list.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import compliance
from ..database import get_db
from ..models import ComplianceEvent, DoNotContact
from ..security import require_role

router = APIRouter(prefix="/compliance", tags=["compliance"])
_write = require_role("admin", "operator")
_read = require_role("admin", "operator", "viewer")


def _event(e: ComplianceEvent) -> dict:
    return {"id": str(e.id), "channel": e.channel, "outcome": e.outcome,
            "rule": e.rule, "reason": e.reason, "target": e.target, "state": e.state,
            "entity_type": e.entity_type,
            "entity_id": str(e.entity_id) if e.entity_id else None,
            "actor": e.actor,
            "created_at": e.created_at.isoformat() if e.created_at else None}


def _dnc(d: DoNotContact) -> dict:
    return {"id": str(d.id), "kind": d.kind, "value": d.value, "reason": d.reason,
            "source": d.source,
            "created_at": d.created_at.isoformat() if d.created_at else None}


@router.get("/status")
def status(db: Session = Depends(get_db), _=Depends(_read)):
    """Current governance posture: enforcement, licensed states, contact window,
    caps, DNC size, and lifetime allow/block/review decision counts."""
    return compliance.status(db)


@router.get("/audit")
def audit(outcome: str | None = None, limit: int = 100,
          db: Session = Depends(get_db), _=Depends(_read)):
    """The immutable decision log, newest first. Filter by outcome=block|review|allow."""
    return {"events": [_event(e) for e in compliance.audit(db, limit=limit, outcome=outcome)]}


@router.get("/review-queue")
def review_queue(limit: int = 100, db: Session = Depends(get_db), _=Depends(_read)):
    """Actions the gate flagged for a licensed human (regulated action / missing
    disclosure) — the human-in-the-loop queue."""
    return {"events": [_event(e) for e in compliance.review_queue(db, limit=limit)]}


@router.get("/dnc")
def dnc_list(db: Session = Depends(get_db), _=Depends(_read)):
    return {"entries": [_dnc(d) for d in compliance.list_dnc(db)]}


class DncIn(BaseModel):
    value: str
    kind: str = "phone"           # phone | email
    reason: str | None = None


@router.post("/dnc")
def dnc_add(body: DncIn, db: Session = Depends(get_db), _=Depends(_write)):
    """Add a phone/email to the Do-Not-Contact list — the gate blocks it immediately."""
    row = compliance.add_dnc(db, value=body.value, kind=body.kind,
                             reason=body.reason, source="manual")
    return {"ok": True, "entry": _dnc(row)}


@router.delete("/dnc/{dnc_id}")
def dnc_remove(dnc_id: str, db: Session = Depends(get_db), _=Depends(_write)):
    return {"ok": compliance.remove_dnc(db, dnc_id)}
