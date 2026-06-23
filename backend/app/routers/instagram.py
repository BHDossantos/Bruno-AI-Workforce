"""Instagram growth routes: targets + content calendar."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Campaign, InstagramTarget
from ..schemas import CampaignOut, InstagramTargetOut
from ..security import require_role

router = APIRouter(prefix="/instagram", tags=["instagram"])
_read = require_role("admin", "operator", "viewer")


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
