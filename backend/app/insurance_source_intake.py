"""Authorized export intake into research reviews, never into live dispatch.

No network client, scraper, credential, scheduler or provider is used here.
Authorization is an operator assertion with a reference, not a legal determination.
"""
from datetime import datetime, timezone
import hashlib
import json
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import AwareDatetime, Field, field_validator, model_validator
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import compliance, insurance_growth
from .database import get_db
from .models import ActionLog, InsuranceProspectReview, Lead
from .routers.insurance_growth import ResearchReview, StrictModel
from .security import require_role


def _reference(value: str) -> str:
    """References only: reject inline documents, credentials and signed URLs."""
    if any(c in value for c in ('\n', '\r', '\t')):
        raise ValueError('Use a single-line evidence reference, not document contents')
    url = urlsplit(value)
    if url.scheme and (url.username or url.password or url.query or url.fragment):
        raise ValueError('Evidence references must not contain credentials, queries or fragments')
    if url.scheme in ('data', 'javascript', 'file'):
        raise ValueError('Unsupported evidence reference')
    return value


class SourceAuthorization(StrictModel):
    method: Literal['agency_export', 'authorized_dataset_export']
    organization: str = Field(min_length=1, max_length=200)
    authorization_ref: str = Field(min_length=1, max_length=500)
    source_ref: str = Field(min_length=1, max_length=500)
    checked_at: AwareDatetime
    valid_until: AwareDatetime
    purpose: Literal['insurance_research']
    collection_and_reuse_authorized: Literal[True]
    contains_no_restricted_scraped_data: Literal[True]

    _refs = field_validator('authorization_ref', 'source_ref')(_reference)

    @model_validator(mode='after')
    def valid_scope(self):
        now = datetime.now(timezone.utc)
        if self.checked_at > now or self.valid_until <= now or self.valid_until <= self.checked_at:
            raise ValueError('Source authorization must be current, checked and unexpired')
        # This service must never turn the known restricted registry into a feed.
        host = (urlsplit(self.source_ref).hostname or '').lower()
        if host == 'sec.state.ma.us' or host.endswith('.sec.state.ma.us'):
            raise ValueError('Massachusetts corporate registry harvesting is not supported')
        return self


class ImportReview(ResearchReview):
    # Opaque evidence references are sufficient. Never import policy documents,
    # policy numbers or raw customer exports into a free-form notes field.
    notes: Literal[''] = ''

    _source_reference = field_validator('source_ref')(_reference)

    @model_validator(mode='after')
    def reference_only(self):
        if self.renewal_evidence_ref:
            _reference(self.renewal_evidence_ref)
        for contact in self.contacts:
            _reference(contact.evidence_ref)
        return self


class ImportRow(StrictModel):
    lead_id: UUID
    expected_revision: int = Field(ge=0)
    review: ImportReview


class ResearchImport(StrictModel):
    authorization: SourceAuthorization
    rows: list[ImportRow] = Field(min_length=1, max_length=200)
    dry_run: bool = True

    @model_validator(mode='after')
    def consistent(self):
        if len({row.lead_id for row in self.rows}) != len(self.rows):
            raise ValueError('Duplicate lead IDs in batch')
        for row in self.rows:
            if row.review.source_ref != self.authorization.source_ref:
                raise ValueError('Every row must reference the authorized source')
            if self.authorization.method == 'agency_export' and row.review.source_kind != 'authorized_agency':
                raise ValueError('Agency exports require authorized_agency provenance')
        return self


def parse_import(raw: str) -> ResearchImport:
    """Parse an export prepared by the authorized operator, without fetching it."""
    if len(raw.encode('utf-8')) > 1_000_000:
        raise ValueError('Research import exceeds 1 MB')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON field')
            result[key] = value
        return result
    return ResearchImport.model_validate(json.loads(raw, object_pairs_hook=unique))


class ImportConflict(ValueError):
    pass


def import_reviews(db: Session, batch: ResearchImport, *, actor: str) -> dict:
    """Atomic compare-and-set research write; caller owns the outer transaction.

    An exact retry is a no-op even if its expected revision is old. A different
    payload at an old revision conflicts. Entire batch rolls back on any conflict.
    Suppression is reported, never edited or treated as source permission.
    """
    # Recheck time-sensitive approval even if a validated object was held in memory.
    batch = ResearchImport.model_validate(batch.model_dump(mode='json'))
    if not actor or not actor.strip():
        raise ValueError('An authenticated reviewer is required')
    planned = []
    manifest = batch.authorization.model_dump(mode='json')
    for row in batch.rows:
        lead = db.get(Lead, row.lead_id)
        if lead is None or lead.segment not in insurance_growth.SEGMENTS:
            raise ImportConflict(f'Insurance lead not found: {row.lead_id}')
        payload = row.review.model_dump(mode='json')
        digest = hashlib.sha256(json.dumps({'review': payload, 'authorization': manifest},
                                          sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        old = db.get(InsuranceProspectReview, row.lead_id)
        unchanged = old is not None and old.payload == payload
        revision = old.revision if old else 0
        if not unchanged and revision != row.expected_revision:
            raise ImportConflict(f'Review changed; reload lead {row.lead_id}')
        suppressed = compliance.is_dnc(db, phone=lead.phone, email=lead.email) or any(
            compliance.is_dnc(db, phone=c.phone) for c in row.review.contacts)
        planned.append((row, payload, unchanged, suppressed, revision, digest))
    if not batch.dry_run:
        try:
            with db.begin_nested():
                for row, payload, unchanged, _, revision, digest in planned:
                    if unchanged:
                        continue
                    if revision == 0:
                        db.add(InsuranceProspectReview(lead_id=row.lead_id, revision=1,
                                                      payload=payload, reviewed_by=actor))
                        db.flush()
                    else:
                        changed = db.execute(update(InsuranceProspectReview).where(
                            InsuranceProspectReview.lead_id == row.lead_id,
                            InsuranceProspectReview.revision == revision).values(
                                payload=payload, reviewed_by=actor, revision=revision + 1))
                        if changed.rowcount != 1:
                            raise ImportConflict(f'Review changed; reload lead {row.lead_id}')
                    db.add(ActionLog(actor=actor, action='insurance_research_import',
                                     entity='lead', entity_id=str(row.lead_id),
                                     detail={'authorization': manifest, 'sha256': digest,
                                             'revision': revision + 1, 'outreach_enqueued': 0}))
                db.flush()
        except IntegrityError as exc:
            raise ImportConflict('Review changed during import; reload before retry') from exc
    return {'mode': 'review_only', 'dry_run': batch.dry_run,
            'would_change': sum(not r[2] for r in planned),
            'saved': 0 if batch.dry_run else sum(not r[2] for r in planned),
            'unchanged': sum(r[2] for r in planned), 'outreach_enqueued': 0,
            'rows': [{'lead_id': str(r[0].lead_id), 'suppressed': r[3],
                      'revision': r[4] + int(not r[2] and not batch.dry_run)} for r in planned]}


router = APIRouter(prefix='/insurance-growth', tags=['insurance growth review'])
_write = require_role('admin', 'operator')


@router.post('/import-research')
def import_research(body: ResearchImport, db: Session = Depends(get_db), user=Depends(_write)):
    try:
        result = import_reviews(db, body, actor=str(user.id))
        if not body.dry_run:
            db.commit()
        return result
    except ImportConflict as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from exc
