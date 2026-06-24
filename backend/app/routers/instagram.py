"""Instagram growth routes: targets + content calendar + live account."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..integrations import instagram_api
from ..models import Campaign, InstagramTarget
from ..schemas import CampaignOut, InstagramTargetOut
from ..security import require_role

router = APIRouter(prefix="/instagram", tags=["instagram"])
_read = require_role("admin", "operator", "viewer")
_write = require_role("admin", "operator")


class PublishIn(BaseModel):
    image_url: str
    caption: str = ""


@router.get("/account")
def account(db: Session = Depends(get_db), _=Depends(_read)):
    """Live overview from the connected Instagram Business account (or not-connected)."""
    return instagram_api.overview(db)


@router.post("/publish")
def publish(body: PublishIn, db: Session = Depends(get_db), _=Depends(_write)):
    """Publish a post to the connected Instagram account (needs Meta approval)."""
    return instagram_api.publish_post(db, body.image_url, body.caption)


@router.get("/targets", response_model=list[InstagramTargetOut])
def targets(category: str | None = None, limit: int = 200,
            db: Session = Depends(get_db), _=Depends(_read)):
    q = db.query(InstagramTarget)
    if category:
        q = q.filter(InstagramTarget.category == category)
    return q.order_by(InstagramTarget.created_at.desc()).limit(limit).all()


@router.get("/calendar", response_model=list[CampaignOut])
def calendar(limit: int = 14, db: Session = Depends(get_db), _=Depends(_read)):
    return (db.query(Campaign).filter(Campaign.channel == "instagram")
            .order_by(Campaign.created_at.desc()).limit(limit).all())
