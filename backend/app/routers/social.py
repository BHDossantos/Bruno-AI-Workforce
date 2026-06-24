"""Unified social publishing API — status + post-now across connected platforms."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import social
from ..database import get_db
from ..security import require_role

router = APIRouter(prefix="/social", tags=["social"])
_read = require_role("admin", "operator", "viewer")
_write = require_role("admin", "operator")


class PostIn(BaseModel):
    caption: str
    image_url: str | None = None


@router.get("/status")
def status(db: Session = Depends(get_db), _=Depends(_read)):
    return social.status(db)


@router.get("/history")
def history(platform: str | None = None, limit: int = 90,
            db: Session = Depends(get_db), _=Depends(_read)):
    return social.history(db, platform, limit)


@router.post("/publish")
def publish(body: PostIn, db: Session = Depends(get_db), _=Depends(_write)):
    """Post now to every connected platform (generates an image if hosting is set)."""
    return social.publish_daily(db, body.caption, body.image_url)
