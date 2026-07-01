"""CSV export of leads / jobs / restaurants for spreadsheets and offline review."""
import csv
import io

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Client, Job, Lead, Restaurant
from ..security import require_role

router = APIRouter(prefix="/export", tags=["export"])
_read = require_role("admin", "operator", "viewer")


def _csv(rows: list[dict], columns: list[str], filename: str) -> StreamingResponse:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/leads.csv")
def export_leads(db: Session = Depends(get_db), _=Depends(_read)):
    cols = ["company_name", "owner_name", "segment", "category", "email", "phone",
            "website", "linkedin", "industry", "score", "status", "reason", "created_at"]
    rows = [{c: getattr(l, c) for c in cols} for l in db.query(Lead).order_by(Lead.score.desc()).all()]
    return _csv(rows, cols, "leads.csv")


@router.get("/jobs.csv")
def export_jobs(db: Session = Depends(get_db), _=Depends(_read)):
    cols = ["title", "company", "location", "remote", "salary_min", "salary_max",
            "source", "url", "score", "found_at"]
    rows = [{c: getattr(j, c) for c in cols} for j in db.query(Job).order_by(Job.score.desc()).all()]
    return _csv(rows, cols, "jobs.csv")


@router.get("/clients.csv")
def export_clients(business: str | None = None, db: Session = Depends(get_db), _=Depends(_read)):
    """The client book (won insurance/other clients) as CSV, optionally by business."""
    cols = ["business", "name", "email", "phone", "address", "city", "state", "zip",
            "line", "carrier", "policy_number", "premium_monthly", "quote_amount",
            "status", "signed_at", "expires_at", "services", "last_contacted_at", "created_at"]
    q = db.query(Client)
    if business:
        q = q.filter(Client.business == business)
    rows = [{c: getattr(cl, c) for c in cols} for cl in q.order_by(Client.created_at.desc()).all()]
    return _csv(rows, cols, "clients.csv")


@router.get("/restaurants.csv")
def export_restaurants(db: Session = Depends(get_db), _=Depends(_read)):
    cols = ["name", "owner_manager", "cuisine", "city", "email", "phone",
            "website", "instagram", "status", "created_at"]
    rows = [{c: getattr(r, c) for c in cols}
            for r in db.query(Restaurant).filter(Restaurant.kind == "prospect").all()]
    return _csv(rows, cols, "restaurants.csv")
