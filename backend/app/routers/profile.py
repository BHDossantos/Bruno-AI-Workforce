"""Brand profile — the account/business identity that tailors all AI content."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import brand
from ..database import get_db
from ..schemas import BrandProfileOut, BrandProfileUpdate
from ..security import require_role

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("", response_model=BrandProfileOut)
def get_profile(db: Session = Depends(get_db),
                _=Depends(require_role("admin", "operator", "viewer"))):
    return brand.get_profile(db)


@router.put("", response_model=BrandProfileOut)
def update_profile(body: BrandProfileUpdate, db: Session = Depends(get_db),
                   _=Depends(require_role("admin", "operator"))):
    row = brand.get_profile(db)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return row
