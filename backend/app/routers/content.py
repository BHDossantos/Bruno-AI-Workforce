"""Content Factory API — one idea → channel-ready content for every platform."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import content_factory
from ..database import get_db
from ..models import ContentItem
from ..security import require_role

router = APIRouter(prefix="/content", tags=["content"])
_read = require_role("admin", "operator", "viewer")
_write = require_role("admin", "operator")


class FactoryIn(BaseModel):
    topic: str
    business: str = "executive"
    channels: list[str] | None = None


@router.post("/factory")
def run_factory(body: FactoryIn, db: Session = Depends(get_db), _=Depends(_write)):
    return content_factory.generate_pack(db, body.topic, body.business, body.channels)


@router.get("")
def list_content(business: str | None = None, channel: str | None = None,
                 status: str | None = None, limit: int = 100,
                 db: Session = Depends(get_db), _=Depends(_read)):
    q = db.query(ContentItem)
    for col, val in (("business", business), ("channel", channel), ("status", status)):
        if val:
            q = q.filter(getattr(ContentItem, col) == val)
    rows = q.order_by(ContentItem.created_at.desc()).limit(limit).all()
    return [content_factory.out(i) for i in rows]


def _set_status(db, content_id, status, scheduled=False):
    item = db.query(ContentItem).filter(ContentItem.id == content_id).first()
    if not item:
        raise HTTPException(404, "content not found")
    item.status = status
    if scheduled:
        item.scheduled_for = datetime.now(timezone.utc)
    db.commit()
    return content_factory.out(item)


@router.post("/{content_id}/approve")
def approve(content_id: str, db: Session = Depends(get_db), _=Depends(_write)):
    """Approve a piece → queue it to publish on the next content tick."""
    return _set_status(db, content_id, "scheduled", scheduled=True)


@router.post("/{content_id}/dismiss")
def dismiss(content_id: str, db: Session = Depends(get_db), _=Depends(_write)):
    return _set_status(db, content_id, "dismissed")


@router.post("/publish-due")
def publish_due(db: Session = Depends(get_db), _=Depends(_write)):
    return content_factory.publish_due(db)


@router.get("/analytics")
def analytics(db: Session = Depends(get_db), _=Depends(_read)):
    from .. import content_analytics
    return {"top": content_analytics.top_performers(db, 12),
            "by_category": content_analytics.category_performance(db)}
