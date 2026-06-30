"""Natural-language campaign builder API."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import campaign_builder
from ..database import get_db
from ..security import require_role

router = APIRouter(prefix="/campaigns", tags=["campaigns"])
_read = require_role("admin", "operator", "viewer")
_write = require_role("admin", "operator")


class BriefIn(BaseModel):
    brief: str


@router.post("/plan")
def plan(body: BriefIn, db: Session = Depends(get_db), _=Depends(_write)):
    """Turn a plain-English brief into a structured campaign plan."""
    return campaign_builder.build(db, body.brief)


@router.get("")
def list_campaigns(db: Session = Depends(get_db), _=Depends(_read)):
    return campaign_builder.list_plans(db)


@router.post("/{plan_id}/launch")
def launch(plan_id: str, db: Session = Depends(get_db), _=Depends(_write)):
    """Launch a planned campaign — runs the mapped agent to source + draft."""
    return campaign_builder.launch(db, plan_id)
