"""Predictive planning API — simulate paths to an income target."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import planning
from ..database import get_db
from ..security import require_role

router = APIRouter(prefix="/planning", tags=["planning"])
_read = require_role("admin", "operator", "viewer")


@router.get("/simulate")
def simulate(target: int = 1_000_000, db: Session = Depends(get_db), _=Depends(_read)):
    """Model paths to a yearly income target, ranked by feasibility."""
    return planning.simulate(db, target)
