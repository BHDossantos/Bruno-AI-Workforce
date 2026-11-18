"""SEO audit API — grade a page's on-page SEO and track it over time.

Thin HTTP layer over ``seo_audit``; all fetch/scoring logic lives in the service.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import seo_audit
from ..database import get_db
from ..security import require_role

router = APIRouter(prefix="/seo", tags=["seo"])
_read = require_role("admin", "operator", "viewer")
_write = require_role("admin", "operator")


class AuditIn(BaseModel):
    url: str = Field(min_length=1)
    business: str | None = None


@router.get("/audits")
def list_audits(url: str | None = None, limit: int = 100,
                db: Session = Depends(get_db), _=Depends(_read)):
    return seo_audit.list_audits(db, url=url, limit=limit)


@router.post("/audit")
def run_audit(body: AuditIn, db: Session = Depends(get_db), _=Depends(_write)):
    row = seo_audit.audit(db, url=body.url, business=body.business)
    return seo_audit.get_audit(db, row.id)


@router.get("/audits/{audit_id}")
def get_audit(audit_id: str, db: Session = Depends(get_db), _=Depends(_read)):
    out = seo_audit.get_audit(db, audit_id)
    if out is None:
        raise HTTPException(404, "audit not found")
    return out


@router.delete("/audits/{audit_id}")
def delete_audit(audit_id: str, db: Session = Depends(get_db), _=Depends(_write)):
    if not seo_audit.delete_audit(db, audit_id):
        raise HTTPException(404, "audit not found")
    return {"ok": True}
