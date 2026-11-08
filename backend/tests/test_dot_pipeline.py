"""Real ORM/router tests with an isolated database; no scheduler/provider calls."""
import os
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SECRET_KEY", "test-only")
import unittest
from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB
from app.database import get_db
from app.models import DotReviewCase, Lead, Message, DoNotContact
from app.routers import dot_review as routes

@compiles(JSONB, "sqlite")
def sqlite_json(element, compiler, **kw):
    return "JSON"

def observation(**changes):
    return {"source_kind": "vendor", "source_name": "DOT Leads New Ventures",
            "source_ref": "fixture://export", "source_record_id": "r1",
            "fetched_at": "2026-11-06T17:00:00Z", "posted_at": "2026-11-06T12:00:00Z",
            "fields": {"usdot": "00123", "legal_name": "Fixture LLC", "email": "contact@example.test"}, **changes}

class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        for model in (DotReviewCase, Lead, Message, DoNotContact):
            model.__table__.create(self.engine)
        self.app = FastAPI()
        self.app.include_router(routes.router)
        def db():
            with Session(self.engine) as session:
                yield session
        self.app.dependency_overrides[get_db] = db
        self.app.dependency_overrides[routes._operator] = lambda: SimpleNamespace(id="operator-1")
        self.client = TestClient(self.app)
    def tearDown(self):
        self.client.close()
        self.engine.dispose()
    def intake(self, observations=None):
        return self.client.post("/dot-review/intake", json={"observations": observations or [observation()],
            "posted_from": "2026-11-06T00:00:00Z", "posted_through": "2026-11-06T23:59:59Z"})

    def update(self, **changes):
        return self.client.post('/dot-review/123/pipeline', json={
            'event_id': 'p1', 'expected_revision': 0, 'stage': 'verified',
            'note': 'Registry lookup not found; ask company to clarify',
            'evidence_ref': 'fixture://registry', 'next_action': 'Recheck registry with client',
            'occurred_at': '2026-11-06T12:00:00Z', 'due_at': '2026-11-06T13:00:00Z', **changes})

    def test_all_stages_summary_and_no_fake_conversions(self):
        self.intake()
        initial = self.client.get('/dot-review/pipeline/summary').json()
        self.assertEqual(initial['stage_counts']['new'], 1)
        self.assertEqual(set(initial['stage_counts']), set(routes.STAGES))
        self.assertIsNone(initial['independently_verified_conversions'])
        self.assertEqual(self.update(stage='contacted').status_code, 200)
        summary = self.client.get('/dot-review/pipeline/summary').json()
        self.assertEqual(summary['operator_reported_issued'], 0)
        self.assertEqual(summary['stage_counts']['contacted'], 1)
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(Message)), 0)
            self.assertEqual(db.scalar(select(func.count()).select_from(Lead)), 0)

    def test_retry_conflict_and_stale_revision(self):
        self.intake()
        first = self.update()
        self.assertEqual(first.status_code, 200)
        self.assertEqual(self.update().json(), first.json())
        self.assertEqual(self.update(note='Different content').status_code, 409)
        self.assertEqual(self.update(event_id='p2', stage='contacted').status_code, 409)
        updated = self.update(event_id='p2', expected_revision=1, stage='contacted')
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(len(updated.json()['history']), 2)
        self.assertEqual(updated.json()['revision'], 2)

    def test_issued_requires_actual_attestation_and_reference(self):
        self.intake()
        self.assertEqual(self.update(stage='policy_issued').status_code, 422)
        self.assertEqual(self.update(stage='policy_issued', issuance_confirmed=True).status_code, 422)
        self.assertEqual(self.update(stage='policy_issued', issuance_confirmed=True,
                                     policy_reference='fixture-issued-policy').status_code, 200)
        summary = self.client.get('/dot-review/pipeline/summary').json()
        self.assertEqual(summary['operator_reported_issued'], 1)
        self.assertEqual(summary['operator_reported_conversion_rate'], 1)
        self.assertIsNone(summary['independently_verified_conversions'])

    def test_reminders_owned_and_missing_registry_not_a_call_hold(self):
        self.intake()
        self.assertEqual(self.update().status_code, 200)
        reminders = self.client.get('/dot-review/pipeline/reminders').json()
        self.assertEqual([r['usdot'] for r in reminders], ['123'])
        self.assertNotIn('history', reminders[0])
        self.app.dependency_overrides[routes._operator] = lambda: SimpleNamespace(id='operator-2')
        self.assertEqual(self.client.get('/dot-review/pipeline/reminders').json(), [])
        self.assertEqual(self.update(event_id='p2', expected_revision=1, stage='contacted').status_code, 200)
        self.assertEqual(self.client.get('/dot-review/123').json()['pipeline']['owner_id'], 'operator-2')

    def test_contacted_pipeline_requires_contact_reconciliation_even_after_rollback(self):
        self.intake()
        self.update(stage='contacted')
        self.assertTrue(self.client.get('/dot-review/123').json()['prior_contact_review'])
        self.update(event_id='p2', expected_revision=1, stage='new')
        self.assertTrue(self.client.get('/dot-review/123').json()['prior_contact_review'])

    def test_whitespace_future_time_and_unknown_stage_rejected(self):
        self.intake()
        for changes in ({'note': '  '}, {'occurred_at': '2099-01-01T00:00:00Z'}, {'stage': 'converted'}):
            self.assertEqual(self.update(**changes).status_code, 422)
