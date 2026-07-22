"""Business/Brand registry API.

Read-only for now — it exposes the config-driven business list so the UI (Setup
mailbox cards, the Content Factory dropdown, the Mailbox Pool) can render from data
instead of hard-coded arrays. Write/edit endpoints (the "Add a business" form) and
routing the send/booking code through the registry come in later steps.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import business_registry as registry
from ..database import get_db
from ..security import require_role

router = APIRouter(tags=["businesses"])
_read = require_role("admin", "operator", "viewer")


@router.get("/businesses")
def list_businesses(active_only: bool = False, db: Session = Depends(get_db), _=Depends(_read)):
    """Every configured business/brand, seeded from current settings. This is the
    data the UI should render instead of hard-coding the business list."""
    registry.seed_defaults(db)  # make sure the defaults exist on first read
    rows = registry.all_businesses(db, active_only=active_only)
    return {"businesses": [registry.serialize(b) for b in rows], "count": len(rows)}
