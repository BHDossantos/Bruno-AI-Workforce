"""Newsletter API — per-funnel lists, sends, and a public unsubscribe."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from .. import newsletters as nl
from ..database import get_db
from ..models import NewsletterSubscriber
from ..security import require_role

router = APIRouter(prefix="/newsletters", tags=["newsletters"])
_read = require_role("admin", "operator", "viewer")
_write = require_role("admin", "operator")


@router.get("")
def overview(db: Session = Depends(get_db), _=Depends(_read)):
    return nl.overview(db)


@router.get("/subscribers")
def subscribers(funnel: str | None = None, limit: int = 500,
                db: Session = Depends(get_db), _=Depends(_read)):
    q = db.query(NewsletterSubscriber)
    if funnel:
        q = q.filter(NewsletterSubscriber.funnel == funnel)
    rows = q.order_by(NewsletterSubscriber.created_at.desc()).limit(limit).all()
    return [{"funnel": s.funnel, "email": s.email, "name": s.name,
             "unsubscribed": s.unsubscribed,
             "created_at": s.created_at.isoformat() if s.created_at else None} for s in rows]


@router.get("/{funnel}/preview")
def preview(funnel: str, db: Session = Depends(get_db), _=Depends(_read)):
    """Generate this funnel's next issue without sending — so you can see a
    newsletter on demand (works even with zero warm subscribers)."""
    res = nl.preview(db, funnel)
    if res.get("ok") is False:
        raise HTTPException(400, res.get("reason", "preview failed"))
    return res


@router.post("/{funnel}/send")
def send(funnel: str, db: Session = Depends(get_db), _=Depends(_write)):
    """Send this funnel's newsletter now to its warm subscribers."""
    res = nl.send_funnel(db, funnel)
    if res.get("ok") is False:
        raise HTTPException(400, res.get("reason", "send failed"))
    return res


# Public — no auth (people click this from their inbox).
@router.get("/unsubscribe", response_class=PlainTextResponse)
def unsubscribe(token: str, db: Session = Depends(get_db)):
    ok = nl.unsubscribe(db, token)
    return "You've been unsubscribed. Sorry to see you go!" if ok \
        else "This unsubscribe link is invalid or already used."
