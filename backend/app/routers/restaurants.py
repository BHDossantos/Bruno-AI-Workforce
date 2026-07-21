"""SavoryMind restaurants + consumer growth routes."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from .. import outreach
from ..database import get_db
from ..models import Restaurant
from ..schemas import RestaurantOut, StatusUpdate
from ..security import require_role

router = APIRouter(prefix="/restaurants", tags=["savorymind"])


class CrmUpdateIn(BaseModel):
    profile: dict = {}
    custom: dict[str, str] | None = None


@router.get("/crm/schema")
def restaurant_crm_schema(_=Depends(require_role("admin", "operator", "viewer"))):
    """Blank SavoryMind restaurant CRM form schema (for the 'Add restaurant' page)."""
    from .. import crm_profile
    return {"schema": crm_profile.schema_for_module("restaurant"), "profile": {}, "custom": {}}


@router.get("/{restaurant_id}/crm")
def get_restaurant_crm(restaurant_id: str, db: Session = Depends(get_db),
                       _=Depends(require_role("admin", "operator", "viewer"))):
    """The restaurant's editable CRM record: profile, owner, intelligence, finance,
    and repeatable locations / employees / customers / menu / inventory / reviews."""
    from .. import crm_profile
    r = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
    if not r:
        raise HTTPException(404, "Restaurant not found")
    return {"schema": crm_profile.schema_for(r), **crm_profile.get_crm(r)}


@router.patch("/{restaurant_id}/crm")
def update_restaurant_crm(restaurant_id: str, body: CrmUpdateIn, db: Session = Depends(get_db),
                          _=Depends(require_role("admin", "operator"))):
    """Save edits to any section(s) of the restaurant's CRM record."""
    from .. import crm_profile
    r = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
    if not r:
        raise HTTPException(404, "Restaurant not found")
    return crm_profile.update_crm_entity(db, r, body.profile, body.custom)


@router.post("/crm")
def create_restaurant_crm(body: CrmUpdateIn, db: Session = Depends(get_db),
                          _=Depends(require_role("admin", "operator"))):
    """Add a new SavoryMind restaurant prospect from the CRM form."""
    from .. import crm_profile
    r = crm_profile.create_restaurant(db, body.profile, body.custom)
    return {"restaurant_id": str(r.id), **crm_profile.get_crm(r)}


@router.get("", response_model=list[RestaurantOut])
def list_restaurants(kind: str = "prospect", temperature: str | None = None, limit: int = 200,
                     db: Session = Depends(get_db), _=Depends(require_role("admin", "operator", "viewer"))):
    from .. import lead_temperature
    q = db.query(Restaurant).filter(Restaurant.kind == kind)
    # Temperature maps to a fixed, known set of statuses — push it into SQL so
    # it can't be starved by an unrelated row LIMIT once cold prospects (the
    # majority, sourced daily) fill the page before a warm/hot filter runs
    # (the same bug already fixed on /leads).
    if temperature:
        wanted = lead_temperature.statuses_for(temperature)
        if wanted is not None:
            q = q.filter(func.lower(Restaurant.status).in_(wanted))
        else:  # cold = everything NOT hot/warm/dead, including blank/unknown
            q = q.filter(or_(Restaurant.status.is_(None),
                             ~func.lower(Restaurant.status).in_(lead_temperature.all_classified_statuses())))
    return q.order_by(Restaurant.created_at.desc()).limit(limit).all()


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
