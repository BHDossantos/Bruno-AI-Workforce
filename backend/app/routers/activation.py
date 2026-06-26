"""Go-live activation API — the readiness checklist."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import activation
from ..database import get_db
from ..security import require_role

router = APIRouter(prefix="/activation", tags=["activation"])


@router.get("")
def get_activation(db: Session = Depends(get_db),
                   _=Depends(require_role("admin", "operator", "viewer"))):
    """What's done, what's next, and the readiness score to go live."""
    return activation.build(db)
