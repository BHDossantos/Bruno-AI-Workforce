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
               temperature: str | None = None, line: str | None = None,
               sort: str | None = None, limit: int = 200,
               db: Session = Depends(get_db), _=Depends(require_role("admin", "operator", "viewer"))):
    from ..insurance_lines import line_for
    from ..lead_temperature import classify
    q = db.query(Lead)
    if segment:
        q = q.filter(Lead.segment == segment)
    if status:
        q = q.filter(Lead.status == status)
    rows = q.order_by(Lead.score.desc(), Lead.created_at.desc()).limit(limit).all()
    if temperature:
        rows = [l for l in rows if classify(l.status) == temperature.lower()]
    if line:  # Home / Auto / Life / Commercial line of business
        rows = [l for l in rows if line_for(l.category, l.segment, l.industry) == line.lower()]
    if sort == "fit":  # surface the strongest prospects first
        from ..lead_fit import score as _fit
        rows = sorted(rows, key=_fit, reverse=True)
    return rows


@router.get("/search")
def lead_finder(segment: str | None = None, temperature: str | None = None,
                industry: str | None = None, city: str | None = None,
                has_email: bool | None = None, min_score: int = 0, q: str | None = None,
                limit: int = 100, db: Session = Depends(get_db),
                _=Depends(require_role("admin", "operator", "viewer"))):
    """Lead Finder: filter leads and return each with an explainable 0-100 score.
    Filters: segment, temperature, industry, city, has_email, min_score, free-text q."""
    from ..lead_scoring import score_lead
    from ..lead_temperature import classify
    query = db.query(Lead)
    if segment:
        query = query.filter(Lead.segment == segment)
    if industry:
        query = query.filter(Lead.industry.ilike(f"%{industry}%"))
    if city:
        query = query.filter(Lead.city.ilike(f"%{city}%")) if hasattr(Lead, "city") else query
    if has_email is True:
        query = query.filter(Lead.email.isnot(None))
    if q:
        like = f"%{q}%"
        query = query.filter(
            (Lead.company_name.ilike(like)) | (Lead.owner_name.ilike(like))
            | (Lead.email.ilike(like)) | (Lead.industry.ilike(like)))
    rows = query.order_by(Lead.score.desc(), Lead.created_at.desc()).limit(max(limit, 400)).all()
    out = []
    for lead in rows:
        if temperature and classify(lead.status) != temperature.lower():
            continue
        sc = score_lead(lead)
        if sc["score"] < min_score:
            continue
        out.append({
            "id": str(lead.id), "company": lead.company_name, "name": lead.owner_name,
            "email": lead.email, "phone": lead.phone, "industry": lead.industry,
            "segment": lead.segment, "status": lead.status,
            "score": sc["score"], "band": sc["band"], "reasons": sc["reasons"],
        })
    out.sort(key=lambda r: r["score"], reverse=True)
    return out[:limit]


@router.get("/summary")
def leads_summary(segment: str | None = None, db: Session = Depends(get_db),
                  _=Depends(require_role("admin", "operator", "viewer"))):
    """Cold / warm / hot counts + Home / Auto / Life / Commercial line counts
    (per segment if given) — the funnel and the book of business at a glance."""
    from ..insurance_lines import LINES, line_for
    from ..lead_temperature import classify
    q = db.query(Lead.status, Lead.category, Lead.segment, Lead.industry)
    if segment:
        q = q.filter(Lead.segment == segment)
    buckets = {"cold": 0, "warm": 0, "hot": 0, "dead": 0}
    lines = {ln: 0 for ln in LINES}
    for status, category, seg, industry in q.all():
        buckets[classify(status)] = buckets.get(classify(status), 0) + 1
        lines[line_for(category, seg, industry)] += 1
    return {**buckets, "lines": lines}


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


@router.post("/sync-replies")
def sync_replies(db: Session = Depends(get_db),
                 _=Depends(require_role("admin", "operator"))):
    """Pull recent inbound email replies now — anyone who replied becomes a warm/hot
    lead. This is what the scheduler does automatically; this button runs it on
    demand so leads don't stay cold while the scheduler is off."""
    from .. import inbound
    return {"ok": True, **inbound.sync_replies(db)}


@router.post("/{lead_id}/status")
def set_status(lead_id: str, body: StatusUpdate, db: Session = Depends(get_db),
               _=Depends(require_role("admin", "operator"))):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    lead.status = body.status
    db.commit()
    return {"lead_id": lead_id, "status": body.status}
