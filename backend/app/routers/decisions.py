"""Decision Journal API — log decisions, record outcomes, surface patterns so the
workforce learns how Bruno decides."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Decision
from ..security import require_role

router = APIRouter(prefix="/decisions", tags=["decisions"])
_read = require_role("admin", "operator", "viewer")
_write = require_role("admin", "operator")

CATEGORIES = ["career", "business", "insurance", "music", "financial", "personal", "other"]


class DecisionIn(BaseModel):
    title: str
    category: str = "other"
    decision: str | None = None
    reasoning: str | None = None
    expected_outcome: str | None = None
    confidence: int = 50


class OutcomeIn(BaseModel):
    outcome: str  # success | failure | mixed
    outcome_note: str | None = None


def _out(d: Decision) -> dict:
    return {"id": str(d.id), "title": d.title, "category": d.category, "decision": d.decision,
            "reasoning": d.reasoning, "expected_outcome": d.expected_outcome,
            "confidence": d.confidence, "status": d.status, "outcome": d.outcome,
            "outcome_note": d.outcome_note,
            "decided_at": d.decided_at.isoformat() if d.decided_at else None,
            "reviewed_at": d.reviewed_at.isoformat() if d.reviewed_at else None}


@router.get("")
def list_decisions(db: Session = Depends(get_db), _=Depends(_read)):
    rows = db.query(Decision).order_by(Decision.decided_at.desc()).limit(300).all()
    return [_out(d) for d in rows]


@router.post("")
def create_decision(body: DecisionIn, db: Session = Depends(get_db), _=Depends(_write)):
    d = Decision(**body.model_dump())
    db.add(d)
    db.commit()
    db.refresh(d)
    return _out(d)


@router.post("/{did}/outcome")
def record_outcome(did: str, body: OutcomeIn, db: Session = Depends(get_db), _=Depends(_write)):
    d = db.query(Decision).filter(Decision.id == did).first()
    if not d:
        raise HTTPException(404, "decision not found")
    d.outcome = body.outcome
    d.outcome_note = body.outcome_note
    d.status = "Reviewed"
    d.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    return _out(d)


@router.get("/patterns")
def patterns(db: Session = Depends(get_db), _=Depends(_read)):
    """What the journal has learned: win-rate overall, by category, and calibration
    (do high-confidence calls actually win more?)."""
    reviewed = db.query(Decision).filter(Decision.status == "Reviewed").all()
    return _analyze(reviewed)


def _analyze(reviewed: list[Decision]) -> dict:
    def winrate(rows):
        if not rows:
            return None
        wins = sum(1 for r in rows if r.outcome == "success")
        return round(100 * wins / len(rows))

    by_cat = {}
    for r in reviewed:
        by_cat.setdefault(r.category or "other", []).append(r)
    high = [r for r in reviewed if (r.confidence or 0) >= 70]
    low = [r for r in reviewed if (r.confidence or 0) < 70]

    return {
        "reviewed": len(reviewed),
        "overall_win_rate": winrate(reviewed),
        "by_category": [{"category": c, "count": len(rows), "win_rate": winrate(rows)}
                        for c, rows in sorted(by_cat.items(), key=lambda kv: -len(kv[1]))],
        "calibration": {
            "high_confidence_win_rate": winrate(high), "high_confidence_n": len(high),
            "low_confidence_win_rate": winrate(low), "low_confidence_n": len(low),
        },
    }
