"""Leads routes (insurance + BnB Global consulting)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import outreach
from ..database import get_db
from ..models import Lead
from ..schemas import LeadOut, StatusUpdate
from ..security import require_role

router = APIRouter(prefix="/leads", tags=["insurance"])


@router.get("", response_model=list[LeadOut])
def list_leads(segment: str | None = None, status: str | None = None, limit: int = 200,
               db: Session = Depends(get_db), _=Depends(require_role("admin", "operator", "viewer"))):
    q = db.query(Lead)
    if segment:
        q = q.filter(Lead.segment == segment)
    if status:
        q = q.filter(Lead.status == status)
    return q.order_by(Lead.score.desc(), Lead.created_at.desc()).limit(limit).all()


@router.post("/{lead_id}/send")
def send_outreach(lead_id: str, db: Session = Depends(get_db),
                  _=Depends(require_role("admin", "operator"))):
    """Reach out to a lead now — sends its cold email (insurance via Thrust,
    consulting/other via personal mailbox)."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    if not lead.email:
        return {"ok": False, "reason": "no email on file"}
    account = "insurance" if lead.segment == "commercial" or lead.segment == "personal" else "personal"
    subject = f"A quick idea for {lead.company_name or lead.owner_name}"
    msg = outreach.dispatch_email(db, entity_type="lead", entity_id=lead.id, to_email=lead.email,
                                  subject=subject, body=lead.cold_email, account=account, actor="manual")
    if msg.status == "Sent" and lead.status in (None, "New", "Drafted"):
        lead.status = "Sent"
    db.commit()
    return {"ok": True, "status": msg.status, "to": lead.email}


@router.post("/{lead_id}/status")
def set_status(lead_id: str, body: StatusUpdate, db: Session = Depends(get_db),
               _=Depends(require_role("admin", "operator"))):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    lead.status = body.status
    db.commit()
    return {"lead_id": lead_id, "status": body.status}
