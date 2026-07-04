"""Leads routes (insurance + BnB Global consulting)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from .. import outreach
from ..database import get_db
from ..models import Lead
from ..schemas import LeadOut, StatusUpdate
from ..security import require_role

router = APIRouter(prefix="/leads", tags=["insurance"])


class IntakeIn(BaseModel):
    quote_type: str
    answers: dict[str, str] = {}


@router.get("/{lead_id}/intake")
def get_intake(lead_id: str, db: Session = Depends(get_db),
               _=Depends(require_role("admin", "operator", "viewer"))):
    """This lead's quote-intake profile — chosen quote type, its fields, saved
    answers, and how many of the requirements have actually been collected."""
    from .. import lead_profile
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(404, "Lead not found")
    return lead_profile.profile_for(lead)


@router.post("/{lead_id}/intake")
def set_intake(lead_id: str, body: IntakeIn, db: Session = Depends(get_db),
               _=Depends(require_role("admin", "operator"))):
    """Pick this lead's quote type and save what's been collected so far."""
    from .. import lead_profile
    result = lead_profile.save_intake(db, lead_id, body.quote_type, body.answers)
    if result is None:
        if not db.query(Lead).filter(Lead.id == lead_id).first():
            raise HTTPException(404, "Lead not found")
        raise HTTPException(400, "Unknown quote type")
    return result


@router.get("/{lead_id}/quote")
def build_quote(lead_id: str, db: Session = Depends(get_db),
                _=Depends(require_role("admin", "operator", "viewer"))):
    """Auto-build this lead's quote packet — line, recommended coverages, a
    fitting carrier shortlist, a ballpark premium estimate, and what's still
    missing before a real quote can be run. Rule-based, no AI key needed."""
    from .. import quote_builder
    result = quote_builder.build(db, lead_id)
    if not result.get("ok"):
        raise HTTPException(404, "Lead not found")
    return result


@router.post("/{lead_id}/quote/sent")
def mark_quote_sent(lead_id: str, db: Session = Depends(get_db),
                    _=Depends(require_role("admin", "operator"))):
    """Mark this lead's quote as sent — advances it to the Quote Sent stage and
    logs it to the lead's AI timeline."""
    from .. import quote_builder
    result = quote_builder.mark_sent(db, lead_id)
    if not result.get("ok"):
        raise HTTPException(404, "Lead not found")
    return result


class IntakeSendIn(BaseModel):
    quote_type: str
    channel: str  # "sms" | "whatsapp"
    lang: str = "en"


@router.post("/{lead_id}/quote-intake/send")
def send_quote_intake(lead_id: str, body: IntakeSendIn, db: Session = Depends(get_db),
                      _=Depends(require_role("admin", "operator"))):
    """Text or WhatsApp this lead the short version of the quote-intake ask
    (the same info the email template collects, phrased for a text thread)."""
    from datetime import datetime, timezone

    from .. import quote_intake, sms_engine
    from ..integrations import sms
    from ..models import Message
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(404, "Lead not found")
    if not lead.phone:
        raise HTTPException(400, "This lead has no phone number on file")
    template = quote_intake.get(body.quote_type)
    if not template:
        raise HTTPException(400, "Unknown quote type")
    text = template.get(f"text_body_{body.lang}") or template.get("text_body_en")
    if not text:
        raise HTTPException(400, "No text template for this quote type")

    if body.channel == "sms":
        result = sms_engine.send_text(db, entity_type="lead", entity_id=lead.id,
                                      phone=lead.phone, body=text, account="insurance")
        if not result:
            raise HTTPException(400, "No texting channel configured — connect Twilio or the "
                                "iMessage bridge on Setup first")
    elif body.channel == "whatsapp":
        if not sms.whatsapp_configured():
            raise HTTPException(400, "WhatsApp isn't connected — add Meta Cloud API or Twilio "
                                "WhatsApp credentials on Setup first")
        sid = sms.send_whatsapp(lead.phone, text)
        if not sid:
            raise HTTPException(400, "WhatsApp send failed")
        db.add(Message(channel="whatsapp", direction="outbound", entity_type="lead",
                       entity_id=lead.id, to_email=lead.phone, from_account="insurance",
                       body=text, status="Sent", provider_id=sid,
                       sent_at=datetime.now(timezone.utc)))
        lead.times_contacted = (lead.times_contacted or 0) + 1
        lead.last_contacted_at = datetime.now(timezone.utc)
        db.commit()
    else:
        raise HTTPException(400, "channel must be 'sms' or 'whatsapp'")
    return {"ok": True, "channel": body.channel, "text": text}


@router.get("", response_model=list[LeadOut])
def list_leads(segment: str | None = None, status: str | None = None,
               temperature: str | None = None, line: str | None = None,
               sort: str | None = None, limit: int = 200,
               db: Session = Depends(get_db), _=Depends(require_role("admin", "operator", "viewer"))):
    from .. import lead_temperature
    from ..insurance_lines import COMMERCIAL, HOME, LIFE, line_for
    q = db.query(Lead)
    if segment:
        q = q.filter(Lead.segment == segment)
    if status:
        q = q.filter(Lead.status == status)
    # Temperature maps to a fixed, known set of statuses — push it into SQL so
    # it never gets starved by an unrelated row LIMIT (whichever bucket
    # dominates the sort order would otherwise silently crowd out the rest).
    if temperature:
        wanted = lead_temperature.statuses_for(temperature)
        if wanted is not None:
            q = q.filter(func.lower(Lead.status).in_(wanted))
        else:  # cold = everything NOT hot/warm/dead, including blank/unknown
            q = q.filter(or_(Lead.status.is_(None),
                             ~func.lower(Lead.status).in_(lead_temperature.all_classified_statuses())))
    # Commercial-line leads only ever come from segment="commercial", and
    # home/life leads only ever come from everything else — narrow by segment
    # first so the (much larger) commercial volume can't bloat the scan below.
    # Auto is the one line that spans both (a personal driver OR a vehicle-
    # centric commercial prospect like an auto shop/trucker), so it can't take
    # that shortcut.
    ln = (line or "").lower()
    if ln == COMMERCIAL:
        q = q.filter(Lead.segment == "commercial")
    elif ln in (HOME, LIFE):
        q = q.filter(Lead.segment != "commercial")
    q = q.order_by(Lead.score.desc(), Lead.created_at.desc())
    if line:
        # `line` needs category/industry keyword matching, which isn't a real
        # column — so it can't be a SQL WHERE clause. Applying it AFTER a row
        # LIMIT would silently starve it once other rows fill the page first
        # (exactly what happened once the table passed a few thousand leads),
        # so fetch every candidate row (already narrowed by segment above) and
        # only limit AFTER the line filter has actually run.
        rows = [l for l in q.all() if line_for(l.category, l.segment, l.industry) == ln]
    else:
        rows = q.limit(limit).all()
    if sort == "fit":  # surface the strongest prospects first
        from ..lead_fit import score as _fit
        rows = sorted(rows, key=_fit, reverse=True)
    return rows[:limit]


@router.get("/search")
def lead_finder(segment: str | None = None, temperature: str | None = None,
                industry: str | None = None, city: str | None = None,
                has_email: bool | None = None, min_score: int = 0, q: str | None = None,
                limit: int = 100, db: Session = Depends(get_db),
                _=Depends(require_role("admin", "operator", "viewer"))):
    """Lead Finder: filter leads and return each with an explainable 0-100 score.
    Filters: segment, temperature, industry, city, has_email, min_score, free-text q."""
    from .. import lead_temperature
    from ..lead_scoring import score_lead
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
    # Temperature maps to a fixed, known status set — push it into SQL (same
    # fix as /leads) so it can't be starved by the row LIMIT below once one
    # temperature bucket dominates the sort order.
    if temperature:
        wanted = lead_temperature.statuses_for(temperature)
        if wanted is not None:
            query = query.filter(func.lower(Lead.status).in_(wanted))
        else:
            query = query.filter(or_(Lead.status.is_(None),
                                     ~func.lower(Lead.status).in_(lead_temperature.all_classified_statuses())))
    rows = query.order_by(Lead.score.desc(), Lead.created_at.desc()).limit(max(limit, 400)).all()
    out = []
    for lead in rows:
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
