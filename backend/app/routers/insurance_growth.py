"""Research-only insurance growth workspace; no provider calls or queued sends."""
from datetime import date, datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import insurance_growth as growth
from ..database import get_db
from ..models import InsuranceProspectReview, Lead
from ..security import require_role

router = APIRouter(prefix="/insurance-growth", tags=["insurance growth review"])
_read = require_role("admin", "operator", "viewer")
_write = require_role("admin", "operator")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ContactEvidence(StrictModel):
    phone: str = Field(pattern=r"^\+[1-9][0-9]{7,14}$")
    name: str = Field(default="", max_length=200)
    role: str = Field(default="", max_length=100)
    status: Literal["unverified", "verified", "wrong_number", "disconnected"] = "unverified"
    evidence_ref: str = Field(min_length=1, max_length=1000)
    checked_at: AwareDatetime

    @model_validator(mode="after")
    def validate_evidence(self):
        if self.checked_at > datetime.now(timezone.utc):
            raise ValueError("Contact check cannot be in the future")
        if self.status == "verified" and (not self.name or not self.role):
            raise ValueError("A verified decision-maker needs a name and role")
        return self


class ResearchReview(StrictModel):
    source_kind: Literal["customer_report", "authorized_agency", "public_business_record", "massachusetts_public_record"]
    source_ref: str = Field(min_length=1, max_length=1000)
    observed_at: AwareDatetime
    contacts: list[ContactEvidence] = Field(default_factory=list, max_length=5)
    renewal_date: date | None = None
    renewal_basis: Literal["unknown", "customer_confirmed", "authorized_policy_record"] = "unknown"
    renewal_evidence_ref: str | None = Field(default=None, max_length=1000)
    notes: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def validate_evidence(self):
        if self.observed_at > datetime.now(timezone.utc):
            raise ValueError("Observation cannot be in the future")
        if len({c.phone for c in self.contacts}) != len(self.contacts):
            raise ValueError("Duplicate contact number")
        if self.renewal_date and (self.renewal_basis == "unknown" or not self.renewal_evidence_ref):
            raise ValueError("Renewal requires policy/customer evidence, not a business registration date")
        if not self.renewal_date and (self.renewal_basis != "unknown" or self.renewal_evidence_ref):
            raise ValueError("Renewal evidence requires an observed renewal date")
        return self


class ReviewUpdate(StrictModel):
    expected_revision: int = Field(ge=0)
    review: ResearchReview


@router.get("/overview")
def overview(days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db), _=Depends(_read)):
    now = datetime.now(timezone.utc)
    return {"mode": "review_only",
            "official_sources": growth.OFFICIAL_SOURCES,
            "source_status": {"massachusetts": "manual_evidence_only",
                              "live_routing": "existing_single_producer_path_not_verified"},
            "prospects": growth.prospects(db, now), "cross_sell": growth.cross_sell(db),
            "funnel": growth.funnel(db, days, now)}


@router.post("/leads/{lead_id}/review")
def record_review(lead_id: UUID, body: ReviewUpdate, db: Session = Depends(get_db), user=Depends(_write)):
    lead = db.get(Lead, lead_id)
    if lead is None or lead.segment not in growth.SEGMENTS:
        raise HTTPException(404, "Insurance lead not found")
    payload = body.review.model_dump(mode="json")
    revision = body.expected_revision + 1
    try:
        if body.expected_revision == 0:
            db.add(InsuranceProspectReview(lead_id=lead_id, revision=revision,
                   payload=payload, reviewed_by=str(user.id)))
            db.flush()
        else:
            changed = db.execute(update(InsuranceProspectReview).where(
                InsuranceProspectReview.lead_id == lead_id,
                InsuranceProspectReview.revision == body.expected_revision).values(
                revision=revision, payload=payload, reviewed_by=str(user.id)))
            if changed.rowcount != 1:
                db.rollback()
                raise HTTPException(409, "Review changed; reload before saving")
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Review changed; reload before saving") from exc
    return {"revision": revision, "review": payload, "outreach_enqueued": 0}
