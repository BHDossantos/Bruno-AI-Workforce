"""Foundation grants API — list opportunities, update status, and a summary."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Grant
from ..security import require_role

router = APIRouter(prefix="/grants", tags=["foundation"])
_read = require_role("admin", "operator", "viewer")
_write = require_role("admin", "operator")


def _out(g: Grant) -> dict:
    return {"id": str(g.id), "title": g.title, "funder": g.funder, "source": g.source,
            "url": g.url, "amount": float(g.amount) if g.amount is not None else None,
            "deadline": g.deadline.isoformat() if g.deadline else None,
            "category": g.category, "summary": g.summary, "eligibility": g.eligibility,
            "match_score": g.match_score, "status": g.status,
            "created_at": g.created_at.isoformat() if g.created_at else None}


@router.get("")
def list_grants(status: str | None = None, limit: int = 200,
                db: Session = Depends(get_db), _=Depends(_read)):
    q = db.query(Grant)
    if status:
        q = q.filter(Grant.status == status)
    rows = (q.order_by(Grant.match_score.desc(), Grant.created_at.desc()).limit(limit).all())
    return [_out(g) for g in rows]


@router.get("/summary")
def summary(db: Session = Depends(get_db), _=Depends(_read)):
    total = db.query(func.count()).select_from(Grant).scalar() or 0
    pipeline = (db.query(func.coalesce(func.sum(Grant.amount), 0))
                .filter(Grant.status.notin_(["Lost", "Skipped"])).scalar() or 0)
    by_status = dict(db.query(Grant.status, func.count()).group_by(Grant.status).all())
    return {"total": int(total), "pipeline_amount": float(pipeline),
            "by_status": {k: int(v) for k, v in by_status.items()}}


@router.post("/source")
def source_now(db: Session = Depends(get_db), _=Depends(_write)):
    """Run the Grant Research agent now."""
    from ..agents import AGENTS
    return {"ok": True, "result": AGENTS["grant_research"](db).run()}


class StatusIn(BaseModel):
    status: str


@router.post("/{grant_id}/status")
def set_status(grant_id: str, body: StatusIn, db: Session = Depends(get_db), _=Depends(_write)):
    g = db.query(Grant).filter(Grant.id == grant_id).first()
    if not g:
        raise HTTPException(404, "grant not found")
    g.status = body.status
    db.commit()
    return {"ok": True, "status": g.status}
