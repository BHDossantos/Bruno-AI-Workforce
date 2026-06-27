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


class ScheduleIn(BaseModel):
    when: str  # ISO datetime


@router.post("/{content_id}/approve")
def approve(content_id: str, db: Session = Depends(get_db), _=Depends(_write)):
    """Approve a piece → queue it to publish on the next content tick."""
    return _set_status(db, content_id, "scheduled", scheduled=True)


@router.post("/{content_id}/schedule")
def schedule(content_id: str, body: ScheduleIn, db: Session = Depends(get_db), _=Depends(_write)):
    """Reschedule a piece to a specific time (and mark it scheduled)."""
    item = db.query(ContentItem).filter(ContentItem.id == content_id).first()
    if not item:
        raise HTTPException(404, "content not found")
    try:
        item.scheduled_for = datetime.fromisoformat(body.when)
    except ValueError:
        raise HTTPException(400, "invalid datetime (use ISO format)")
    item.status = "scheduled"
    db.commit()
    return content_factory.out(item)


@router.post("/{content_id}/dismiss")
def dismiss(content_id: str, db: Session = Depends(get_db), _=Depends(_write)):
    return _set_status(db, content_id, "dismissed")


@router.post("/{content_id}/regenerate")
def regenerate(content_id: str, db: Session = Depends(get_db), _=Depends(_write)):
    """Rewrite one stale draft at the current quality bar (dismisses the old one)."""
    res = content_factory.regenerate_item(db, content_id)
    if res.get("ok") is False:
        raise HTTPException(404, res.get("reason", "content not found"))
    return res


class HookIn(BaseModel):
    hook: str


@router.post("/{content_id}/apply-hook")
def apply_hook(content_id: str, body: HookIn, db: Session = Depends(get_db), _=Depends(_write)):
    """Swap the post's opening line for one of the AI's alternative hooks."""
    res = content_factory.apply_hook(db, content_id, body.hook)
    if res.get("ok") is False:
        raise HTTPException(404, res.get("reason", "content not found"))
    return res


class RegenIn(BaseModel):
    business: str | None = None
    channel: str | None = None


@router.post("/regenerate")
def regenerate_stale(body: RegenIn | None = None, db: Session = Depends(get_db), _=Depends(_write)):
    """Clear the un-published draft backlog and regenerate fresh content at the new
    quality bar (optionally filtered by business/channel)."""
    body = body or RegenIn()
    return content_factory.regenerate_stale(db, business=body.business, channel=body.channel)


@router.post("/publish-due")
def publish_due(db: Session = Depends(get_db), _=Depends(_write)):
    return content_factory.publish_due(db)


@router.get("/analytics")
def analytics(db: Session = Depends(get_db), _=Depends(_read)):
    from .. import content_analytics
    return {"top": content_analytics.top_performers(db, 12),
            "by_category": content_analytics.category_performance(db)}


@router.get("/video/status")
def video_status(_=Depends(_read)):
    from .. import video_pipeline
    return video_pipeline.available()


@router.post("/{content_id}/video")
def make_video(content_id: str, db: Session = Depends(get_db), _=Depends(_write)):
    """Produce media assets (voiceover, cover, AI video clip) for a content piece."""
    from .. import video_pipeline
    return video_pipeline.start_for_content(db, content_id)
