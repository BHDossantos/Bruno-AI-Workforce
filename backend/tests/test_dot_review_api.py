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

class DotReviewApiTests(unittest.TestCase):
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
    def event(self, **changes):
        return self.client.post("/dot-review/123/events", json={"event_id": "e1", "kind": "contact_reported",
            "occurred_at": "2026-11-06T16:00:00Z", "evidence_ref": "fixture://message",
            "note": "Already contacted; do not repeat", **changes})
    def test_durable_dedup_without_outbound_queue(self):
        self.assertEqual(self.intake().status_code, 200)
        self.assertEqual(self.intake().json()["outreach_enqueued"], 0)
        cases = self.client.get("/dot-review").json()
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0]["legal_name"], "Fixture LLC")
        self.assertNotIn("observations", cases[0])
        self.assertEqual(len(self.client.get("/dot-review/123").json()["observations"]), 1)
        with Session(self.engine) as db:
            for model in (Lead, Message):
                self.assertEqual(db.scalar(select(func.count()).select_from(model)), 0)
    def test_posted_date_and_vendor_required(self):
        self.assertEqual(self.intake([observation(posted_at="2026-11-05T12:00:00Z")]).json()["usdots"], [])
        for change in ({"posted_at": None}, {"source_kind": "safer"}, {"posted_at": "2026-11-06T12:00:00"}):
            self.assertEqual(self.intake([observation(**change)]).status_code, 422)
    def test_invalid_batch_does_not_partially_write(self):
        self.assertEqual(self.intake([observation(), observation(fields={"usdot": "bad"})]).status_code, 422)
        self.assertEqual(self.client.get("/dot-review").json(), [])
    def test_missing_safer_is_uncertain_and_identity_conflict_retained(self):
        self.intake()
        missing = observation(source_kind="safer", fields={"lookup_status": "not_found", "usdot": "456"})
        self.assertEqual(self.client.post("/dot-review/123/evidence", json=missing).status_code, 200)
        data = self.client.get("/dot-review/123").json()
        self.assertEqual(data["safer_status"], "unverified")
        self.assertFalse(data["sending_enabled"])
        self.assertTrue(any(d["reason"] == "identity_review" for d in data["differences"]))
    def test_event_retry_and_provider_status_distinguished(self):
        self.intake()
        self.assertEqual(self.event().status_code, 200)
        self.assertEqual(self.event().status_code, 200)
        self.assertEqual(self.event(note="Changed").status_code, 409)
        with Session(self.engine) as db:
            db.add(Message(to_email="CONTACT@example.test", channel="email", status="Sent", provider_id="fixture-provider"))
            db.commit()
        data = self.client.get("/dot-review/123").json()
        self.assertTrue(data["prior_contact_review"])
        self.assertEqual(len(data["events"]), 1)
        self.assertEqual(data["message_history"][0]["provider_id"], "fixture-provider")
        self.assertEqual(data["draft"]["status"], "local_review_only")
    def test_optout_uses_existing_global_suppression(self):
        self.intake()
        self.assertEqual(self.event(kind="opt_out").status_code, 200)
        data = self.client.get("/dot-review/123").json()
        self.assertTrue(data["suppressed"])
        self.assertIsNone(data["draft"]["body"])
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(DoNotContact)).value, "contact@example.test")
    def test_events_require_actual_values(self):
        self.intake()
        for kind in ("language_preference", "next_action", "outcome"):
            self.assertEqual(self.event(kind=kind).status_code, 422)
        self.assertEqual(self.event(kind="language_preference", language="pt").status_code, 200)
        self.assertEqual(self.event(kind="outcome", event_id="e2", outcome="voicemail_unavailable").status_code, 200)
    def test_csv_import(self):
        response = self.client.post("/dot-review/import-csv", data={"source_ref": "fixture://export",
            "posted_from": "2026-11-06T00:00:00Z", "posted_through": "2026-11-06T23:59:59Z"},
            files={"file": ("leads.csv", "usdot,source_record_id,posted_at,legal_name\n123,r1,2026-11-06T12:00:00Z,Fixture LLC\n", "text/csv")})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["usdots"], ["123"])
    def test_local_draft_requires_evidenced_recipient_and_no_prior_contact(self):
        self.intake([observation(fields={"usdot": "123", "email": "contact@example.com"})])
        digest = routes.Observation.model_validate(observation(fields={"usdot": "123", "email": "contact@example.com"})).snapshot().digest
        payload = {"to": "contact@example.com", "bcc": ["reviewer@example.com"],
                   "subject": "Insurance questions", "body": "Which language do you prefer?",
                   "evidence_digests": [digest]}
        response = self.client.post("/dot-review/123/draft", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsNone(response.json()["sent_at"])
        self.assertIsNone(response.json()["provider_id"])
        self.assertTrue(response.json()["bcc_requires_identity_verification"])
        self.assertEqual(self.client.post("/dot-review/123/draft", json={**payload, "to": "other@example.com"}).status_code, 422)
        self.assertEqual(self.client.post("/dot-review/123/draft", json={**payload, "evidence_digests": ["invented"]}).status_code, 422)
        self.event()
        self.assertEqual(self.client.post("/dot-review/123/draft", json=payload).status_code, 409)

    def test_operator_role_required(self):
        from app.security import get_current_user
        self.app.dependency_overrides.pop(routes._operator)
        self.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(role="viewer")
        self.assertEqual(self.client.get("/dot-review").status_code, 403)

    def test_authentication_and_no_send_endpoint(self):
        self.assertEqual(self.client.post("/dot-review/123/send").status_code, 404)
        self.app.dependency_overrides.pop(routes._operator)
        self.assertEqual(self.client.get("/dot-review").status_code, 401)
        self.assertEqual(self.intake().status_code, 401)

if __name__ == "__main__":
    unittest.main()
