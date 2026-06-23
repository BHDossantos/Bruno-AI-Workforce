"""SavoryMind restaurants + consumer growth routes."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Restaurant
from ..schemas import RestaurantOut, StatusUpdate
from ..security import require_role

router = APIRouter(prefix="/restaurants", tags=["savorymind"])


@router.get("", response_model=list[RestaurantOut])
def list_restaurants(kind: str = "prospect", limit: int = 200,
                     db: Session = Depends(get_db), _=Depends(require_role("admin", "operator", "viewer"))):
    return (db.query(Restaurant).filter(Restaurant.kind == kind)
            .order_by(Restaurant.created_at.desc()).limit(limit).all())


@router.post("/{restaurant_id}/status")
def set_status(restaurant_id: str, body: StatusUpdate, db: Session = Depends(get_db),
               _=Depends(require_role("admin", "operator"))):
    r = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    r.status = body.status
    db.commit()
    return {"restaurant_id": restaurant_id, "status": body.status}
