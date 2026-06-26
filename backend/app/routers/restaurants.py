"""SavoryMind restaurants + consumer growth routes."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import outreach
from ..database import get_db
from ..models import Restaurant
from ..schemas import RestaurantOut, StatusUpdate
from ..security import require_role

router = APIRouter(prefix="/restaurants", tags=["savorymind"])


@router.get("", response_model=list[RestaurantOut])
def list_restaurants(kind: str = "prospect", temperature: str | None = None, limit: int = 200,
                     db: Session = Depends(get_db), _=Depends(require_role("admin", "operator", "viewer"))):
    from ..lead_temperature import classify
    rows = (db.query(Restaurant).filter(Restaurant.kind == kind)
            .order_by(Restaurant.created_at.desc()).limit(limit).all())
    if temperature:
        rows = [r for r in rows if classify(r.status) == temperature.lower()]
    return rows


@router.get("/summary")
def restaurants_summary(db: Session = Depends(get_db),
                        _=Depends(require_role("admin", "operator", "viewer"))):
    """Cold / warm / hot counts for SavoryMind restaurant prospects."""
    from ..lead_temperature import classify
    buckets = {"cold": 0, "warm": 0, "hot": 0, "dead": 0}
    for (status,) in db.query(Restaurant.status).filter(Restaurant.kind == "prospect").all():
        buckets[classify(status)] = buckets.get(classify(status), 0) + 1
    return buckets


@router.post("/{restaurant_id}/send")
def send_pitch(restaurant_id: str, db: Session = Depends(get_db),
               _=Depends(require_role("admin", "operator"))):
    """Reach out to a restaurant now — sends the SavoryMind pitch via email."""
    r = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    if not r.email:
        return {"ok": False, "reason": "no email on file for this restaurant"}
    subject = f"Growing revenue at {r.name} with SavoryMind"
    msg = outreach.dispatch_email(db, entity_type="restaurant", entity_id=r.id,
                                  to_email=r.email, subject=subject,
                                  body=r.pitch_email, account="personal", actor="manual",
                                  autonomous=False)
    if r.status in (None, "New", "Drafted"):
        r.status = "Sent" if msg.status == "Sent" else r.status
    db.commit()
    return {"ok": True, "status": msg.status, "to": r.email}


@router.post("/dispatch")
def dispatch_pending(db: Session = Depends(get_db),
                     _=Depends(require_role("admin", "operator"))):
    """Send the SavoryMind pitch to every pending restaurant prospect at once."""
    from .. import bulk_outreach
    return {"ok": True, **bulk_outreach.dispatch_restaurants(db, autonomous=False)}


@router.post("/{restaurant_id}/status")
def set_status(restaurant_id: str, body: StatusUpdate, db: Session = Depends(get_db),
               _=Depends(require_role("admin", "operator"))):
    r = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    r.status = body.status
    db.commit()
    return {"restaurant_id": restaurant_id, "status": body.status}
