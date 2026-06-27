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
def list_leads(segment: str | None = None, status: str | None = None,
               temperature: str | None = None, sort: str | None = None, limit: int = 200,
               db: Session = Depends(get_db), _=Depends(require_role("admin", "operator", "viewer"))):
    from ..lead_temperature import classify
    q = db.query(Lead)
    if segment:
        q = q.filter(Lead.segment == segment)
    if status:
        q = q.filter(Lead.status == status)
    rows = q.order_by(Lead.score.desc(), Lead.created_at.desc()).limit(limit).all()
    if temperature:
        rows = [l for l in rows if classify(l.status) == temperature.lower()]
    if sort == "fit":  # surface the strongest prospects first
        from ..lead_fit import score as _fit
        rows = sorted(rows, key=_fit, reverse=True)
    return rows


@router.get("/summary")
def leads_summary(segment: str | None = None, db: Session = Depends(get_db),
                  _=Depends(require_role("admin", "operator", "viewer"))):
    """Cold / warm / hot counts (per segment if given) — the funnel at a glance."""
    from ..lead_temperature import classify
    q = db.query(Lead.status)
    if segment:
        q = q.filter(Lead.segment == segment)
    buckets = {"cold": 0, "warm": 0, "hot": 0, "dead": 0}
    for (status,) in q.all():
        buckets[classify(status)] = buckets.get(classify(status), 0) + 1
    return buckets


@router.get("/pipeline-health")
def pipeline_health(db: Session = Depends(get_db),
                    _=Depends(require_role("admin", "operator", "viewer"))):
    """Why warm/hot leads aren't flowing yet, and the exact next action to fix it."""
    from .. import lead_pipeline
    return lead_pipeline.health(db)


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
                                  subject=subject, body=lead.cold_email, account=account,
                                  actor="manual", autonomous=False)
    if msg.status == "Sent" and lead.status in (None, "New", "Drafted"):
        lead.status = "Sent"
    db.commit()
    return {"ok": True, "status": msg.status, "to": lead.email}


@router.post("/dispatch")
def dispatch_pending(segment: str | None = None, db: Session = Depends(get_db),
                     _=Depends(require_role("admin", "operator"))):
    """Send the cold email to every pending lead at once (status New/Drafted with an
    email). Optional ?segment= for insurance (commercial/personal) or consulting."""
    from .. import bulk_outreach
    return {"ok": True, **bulk_outreach.dispatch_leads(db, segment=segment, autonomous=False)}


@router.post("/{lead_id}/status")
def set_status(lead_id: str, body: StatusUpdate, db: Session = Depends(get_db),
               _=Depends(require_role("admin", "operator"))):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    lead.status = body.status
    db.commit()
    return {"lead_id": lead_id, "status": body.status}
