"""Client-acquisition goal API — daily new-client target + autoscale status."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import client_goal
from ..config import settings
from ..database import get_db
from ..models import Setting
from ..security import require_role

router = APIRouter(prefix="/clients", tags=["clients"])
_read = require_role("admin", "operator", "viewer")
_write = require_role("admin", "operator")


@router.get("/goal")
def goal(db: Session = Depends(get_db), _=Depends(_read)):
    """Progress toward the daily new-client target (clients today vs target, the
    measured conversion rate, and the cold-touch volume needed to hit it)."""
    return client_goal.status(db)


@router.post("/autoscale")
def autoscale(db: Session = Depends(get_db), _=Depends(_write)):
    """Recalculate and apply the outreach volume needed to hit the client target.
    Runs nightly automatically; this triggers it on demand."""
    return client_goal.autoscale(db)


class TargetIn(BaseModel):
    target: int = Field(ge=1, le=500)


@router.post("/target")
def set_target(body: TargetIn, db: Session = Depends(get_db), _=Depends(_write)):
    """Set the daily new-client target and immediately re-size outreach for it."""
    settings.daily_client_target = body.target
    row = db.get(Setting, "scale:daily_client_target")
    if row is None:
        row = Setting(key="scale:daily_client_target")
        db.add(row)
    row.value = str(body.target)
    db.commit()
    return client_goal.autoscale(db)
