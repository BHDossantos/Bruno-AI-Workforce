"""Assisted social outreach queue.

Aggregates the AI-written LinkedIn/Instagram messages the agents produce into one
review-and-send queue. This is the compliant alternative to bot automation: the
copy + the target profile link are prepared so the user sends with one click,
then marks it done. No platform automation, no account risk.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Influencer, InstagramTarget, Lead, Restaurant
from ..security import require_role

router = APIRouter(prefix="/outreach", tags=["outreach"])
_read = require_role("admin", "operator", "viewer")
_write = require_role("admin", "operator")

DONE = {"Sent", "Replied", "Interested", "Closed Won", "Closed Lost"}


def _ig(handle: str | None) -> str | None:
    if not handle:
        return None
    return f"https://instagram.com/{handle.lstrip('@')}"


def _ig_dm(handle: str | None) -> str | None:
    """Deep link straight to the DM thread with this handle (opens the IG
    composer), so outreach is one tap instead of profile → message."""
    if not handle:
        return None
    return f"https://ig.me/m/{handle.lstrip('@')}"


@router.get("/social")
def social_queue(channel: str | None = None, limit: int = 400,
                 db: Session = Depends(get_db), _=Depends(_read)):
    items: list[dict] = []

    for l in db.query(Lead).filter(Lead.linkedin_msg.isnot(None), Lead.linkedin.isnot(None)).limit(150):
        if l.status in DONE:
            continue
        items.append({"entity_type": "lead", "entity_id": str(l.id), "name": l.company_name or l.owner_name,
                      "channel": "linkedin", "profile_url": l.linkedin, "handle": None,
                      "message": l.linkedin_msg, "status": l.status})

    for inf in db.query(Influencer).filter(Influencer.dm_pitch.isnot(None)).limit(100):
        if inf.status in DONE:
            continue
        items.append({"entity_type": "influencer", "entity_id": str(inf.id), "name": inf.name,
                      "channel": "instagram", "profile_url": _ig(inf.handle), "handle": inf.handle,
                      "dm_url": _ig_dm(inf.handle), "message": inf.dm_pitch, "status": inf.status})

    for t in db.query(InstagramTarget).filter(InstagramTarget.dm_opener.isnot(None)).limit(150):
        if t.status in DONE:
            continue
        items.append({"entity_type": "instagram_target", "entity_id": str(t.id), "name": f"@{t.handle}",
                      "channel": "instagram", "profile_url": _ig(t.handle), "handle": t.handle,
                      "dm_url": _ig_dm(t.handle), "message": t.dm_opener, "status": t.status})

    for r in db.query(Restaurant).filter(Restaurant.kind == "prospect",
                                         Restaurant.linkedin_msg.isnot(None)).limit(100):
        if r.status in DONE:
            continue
        items.append({"entity_type": "restaurant", "entity_id": str(r.id), "name": r.name,
                      "channel": "instagram", "profile_url": _ig(r.instagram), "handle": r.instagram,
                      "dm_url": _ig_dm(r.instagram), "message": r.linkedin_msg, "status": r.status})

    if channel:
        items = [i for i in items if i["channel"] == channel]
    return items[:limit]


class MarkBody(BaseModel):
    entity_type: str
    entity_id: str
    status: str = "Sent"


_MODELS = {"lead": Lead, "influencer": Influencer,
           "instagram_target": InstagramTarget, "restaurant": Restaurant}


@router.post("/social/mark")
def mark_done(body: MarkBody, db: Session = Depends(get_db), _=Depends(_write)):
    model = _MODELS.get(body.entity_type)
    if not model:
        return {"ok": False, "reason": "unknown entity_type"}
    row = db.query(model).filter(model.id == body.entity_id).first()
    if not row:
        return {"ok": False, "reason": "not found"}
    row.status = body.status
    db.commit()
    return {"ok": True, "entity_type": body.entity_type, "status": body.status}
