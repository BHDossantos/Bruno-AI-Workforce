"""Isolated intake tests. No source fetch, production data or provider calls."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from uuid import uuid4
from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from app.database import get_db
import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from app.models import ActionLog, DoNotContact, InsuranceProspectReview, Lead, Message
from app import insurance_source_intake as source

@compiles(JSONB, 'sqlite')
def sqlite_json(element, compiler, **kw):
    return 'JSON'

@pytest.fixture
def workspace():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    for model in (Lead, DoNotContact, InsuranceProspectReview, ActionLog, Message):
        model.__table__.create(engine)
    with Session(engine) as db:
        lead = Lead(id=uuid4(), segment='commercial', company_name='Fixture', phone='+16175550101')
        db.add(lead)
        db.commit()
        lead_id = lead.id
    yield engine, lead_id
    engine.dispose()

def payload(lead_id, **changes):
    now = datetime.now(timezone.utc) - timedelta(minutes=1)
    ref = 'export://fixture/v1'
    return {'authorization': {'method': 'agency_export', 'organization': 'Fixture agency',
        'authorization_ref': 'approval://fixture/123', 'source_ref': ref,
        'checked_at': now.isoformat(), 'valid_until': (now+timedelta(days=1)).isoformat(),
        'purpose': 'insurance_research', 'collection_and_reuse_authorized': True,
        'contains_no_restricted_scraped_data': True},
        'rows': [{'lead_id': str(lead_id), 'expected_revision': 0, 'review': {
            'source_kind': 'authorized_agency', 'source_ref': ref,
            'observed_at': now.isoformat(), 'contacts': [{'phone': '+16175550102',
            'name': 'Owner', 'role': 'Owner', 'status': 'verified',
            'checked_at': now.isoformat(), 'evidence_ref': 'evidence://fixture/1'}]}}], **changes}

def test_preview_has_no_writes(workspace):
    engine, lead_id = workspace
    with Session(engine) as db:
        result = source.import_reviews(db, source.parse_import(json.dumps(payload(lead_id))), actor='tester')
        assert result['dry_run'] and result['would_change'] == 1 and result['saved'] == 0
        assert db.scalar(select(func.count()).select_from(InsuranceProspectReview)) == 0
        assert db.scalar(select(func.count()).select_from(ActionLog)) == 0

def test_idempotency_and_dispatch_untouched(workspace):
    engine, lead_id = workspace
    batch = source.ResearchImport.model_validate(payload(lead_id, dry_run=False))
    with Session(engine) as db:
        assert source.import_reviews(db, batch, actor='tester')['saved'] == 1
        db.commit()
        assert source.import_reviews(db, batch, actor='tester')['unchanged'] == 1
        assert db.get(InsuranceProspectReview, lead_id).revision == 1
        assert db.get(Lead, lead_id).phone == '+16175550101'
        assert db.scalar(select(func.count()).select_from(Message)) == 0
        logs = db.scalars(select(ActionLog)).all()
        assert len(logs) == 1 and logs[0].detail['outreach_enqueued'] == 0
        assert logs[0].detail['authorization']['authorization_ref'] == 'approval://fixture/123'
        source.ResearchReview.model_validate(db.get(InsuranceProspectReview, lead_id).payload)

def test_stale_conflict_and_fresh_revision(workspace):
    engine, lead_id = workspace
    value = payload(lead_id, dry_run=False)
    with Session(engine) as db:
        source.import_reviews(db, source.ResearchImport.model_validate(value), actor='tester')
        db.commit()
        value['rows'][0]['review']['contacts'][0]['role'] = 'CFO'
        with pytest.raises(source.ImportConflict):
            source.import_reviews(db, source.ResearchImport.model_validate(value), actor='tester')
        value['rows'][0]['expected_revision'] = 1
        assert source.import_reviews(db, source.ResearchImport.model_validate(value), actor='tester')['saved'] == 1
        assert db.get(InsuranceProspectReview, lead_id).revision == 2

def test_invalid_batch_no_partial_import(workspace):
    engine, lead_id = workspace
    value = payload(lead_id, dry_run=False)
    extra = deepcopy(value['rows'][0]); extra['lead_id'] = str(uuid4())
    value['rows'].append(extra)
    with Session(engine) as db:
        with pytest.raises(source.ImportConflict):
            source.import_reviews(db, source.ResearchImport.model_validate(value), actor='tester')
        assert db.scalar(select(func.count()).select_from(InsuranceProspectReview)) == 0

def test_suppression_preserved(workspace):
    engine, lead_id = workspace
    with Session(engine) as db:
        db.add(DoNotContact(kind='phone', value='6175550102', reason='fixture')); db.commit()
        result = source.import_reviews(db, source.ResearchImport.model_validate(payload(lead_id, dry_run=False)), actor='tester')
        assert result['rows'][0]['suppressed'] is True and result['outreach_enqueued'] == 0
        assert db.scalar(select(func.count()).select_from(DoNotContact)) == 1

@pytest.mark.parametrize('mutation', [
    lambda x: x['authorization'].update(collection_and_reuse_authorized=False),
    lambda x: x['authorization'].update(contains_no_restricted_scraped_data=False),
    lambda x: x['authorization'].update(authorization_ref=''),
    lambda x: x['authorization'].update(valid_until='2020-01-01T00:00:00Z'),
    lambda x: x['authorization'].update(checked_at='2099-01-01T00:00:00Z'),
    lambda x: x['authorization'].update(source_ref='https://corp.sec.state.ma.us/corpweb/'),
    lambda x: x['rows'][0]['review'].update(policy_number='private'),
    lambda x: x['rows'][0]['review'].update(notes='raw policy document'),
    lambda x: x['rows'][0]['review'].update(source_ref='export://other'),
    lambda x: x['rows'][0]['review'].update(renewal_date='2027-01-01'),
    lambda x: x['rows'][0]['review']['contacts'][0].update(evidence_ref='https://example.test/doc?token=secret'),
    lambda x: x['rows'].append(deepcopy(x['rows'][0])),
])
def test_invalid_data_rejected(workspace, mutation):
    _, lead_id = workspace
    value = payload(lead_id); mutation(value)
    with pytest.raises(ValidationError):
        source.ResearchImport.model_validate(value)

def test_parser_limits():
    with pytest.raises(ValueError, match='1 MB'):
        source.parse_import(' '*1_000_001)
    with pytest.raises(ValueError, match='Duplicate JSON'):
        source.parse_import('{"rows": [], "rows": []}')


def test_authenticated_api_preview_save_and_conflict(workspace):
    engine, lead_id = workspace
    app = FastAPI()
    app.include_router(source.router)
    def db():
        with Session(engine) as session:
            yield session
    app.dependency_overrides[get_db] = db
    with TestClient(app) as client:
        assert client.post('/insurance-growth/import-research', json=payload(lead_id)).status_code in (401, 403)
        app.dependency_overrides[source._write] = lambda: SimpleNamespace(id='authenticated-reviewer')
        value = payload(lead_id)
        assert client.post('/insurance-growth/import-research', json=value).json()['saved'] == 0
        value['dry_run'] = False
        assert client.post('/insurance-growth/import-research', json=value).json()['saved'] == 1
        value['rows'][0]['review']['contacts'][0]['role'] = 'CFO'
        assert client.post('/insurance-growth/import-research', json=value).status_code == 409
    with Session(engine) as db:
        assert db.get(InsuranceProspectReview, lead_id).reviewed_by == 'authenticated-reviewer'
        assert db.get(InsuranceProspectReview, lead_id).payload['contacts'][0]['role'] == 'Owner'
