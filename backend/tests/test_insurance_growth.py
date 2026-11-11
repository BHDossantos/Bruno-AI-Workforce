"""Review-only insurance workflow. Isolated ORM, no scheduler or providers."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import get_db
from app.models import (Client, ConversationOutcome, DoNotContact,
                        InsuranceProspectReview, Lead, Message)
from app.routers import insurance_growth as routes


@compiles(JSONB, "sqlite")
def sqlite_json(element, compiler, **kw):
    return "JSON"


@pytest.fixture
def workspace():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    for model in (Lead, Client, ConversationOutcome, DoNotContact, InsuranceProspectReview, Message):
        model.__table__.create(engine)
    app = FastAPI()
    app.include_router(routes.router)
    def db():
        with Session(engine) as session:
            yield session
    app.dependency_overrides[get_db] = db
    app.dependency_overrides[routes._read] = lambda: SimpleNamespace(id="operator")
    app.dependency_overrides[routes._write] = lambda: SimpleNamespace(id="operator")
    with TestClient(app) as client:
        yield client, engine, app
    engine.dispose()


def add_lead(engine, **values):
    with Session(engine) as db:
        row = Lead(id=uuid4(), segment=values.pop("segment", "commercial"),
                   company_name="Fixture business", phone="+16175550101", **values)
        db.add(row)
        db.commit()
        return str(row.id)


def review(**changes):
    now = datetime.now(timezone.utc) - timedelta(seconds=5)
    return {"source_kind": "massachusetts_public_record", "source_ref": "fixture://business-record",
            "observed_at": now.isoformat(), "contacts": [{"phone": "+16175550102", "name": "Fixture Owner",
                "role": "Owner", "status": "verified", "evidence_ref": "fixture://confirmed-business-contact",
                "checked_at": now.isoformat()}], "renewal_date": None, "renewal_basis": "unknown",
            "renewal_evidence_ref": None, "notes": "Business record is not policy-expiration evidence.", **changes}


def save(client, lead, payload=None, revision=0):
    return client.post(f"/insurance-growth/leads/{lead}/review", json={
        "expected_revision": revision, "review": payload or review()})


def test_empty_workspace_and_no_fabricated_rates(workspace):
    client, _, _ = workspace
    result = client.get("/insurance-growth/overview").json()
    assert result["mode"] == "review_only"
    assert result["funnel"]["answer_to_quote_rate"] is None
    assert result["funnel"]["quote_to_sale_rate"] is None
    assert result["prospects"]["items"] == []
    assert result["source_status"]["massachusetts"] == "manual_evidence_only"


def test_review_does_not_change_contact_enqueue_or_claim_permission(workspace):
    client, engine, _ = workspace
    lead = add_lead(engine)
    assert save(client, lead).json()["outreach_enqueued"] == 0
    result = client.get("/insurance-growth/overview").json()["prospects"]["items"][0]
    assert result["review_revision"] == 1
    assert result["phone"] == "+16175550101"
    assert result["review"]["contacts"][0]["phone"] == "+16175550102"
    assert "outreach_authorization_and_licensed_handler_review_required" in result["review_flags"]
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Message)) == 0
        assert db.scalar(select(func.count()).select_from(ConversationOutcome)) == 0
        assert db.get(Lead, UUID(lead)).intake is None


def test_optimistic_revision_prevents_overwriting_or_duplicate_initial_save(workspace):
    client, engine, _ = workspace
    lead = add_lead(engine)
    assert save(client, lead).status_code == 200
    assert save(client, lead).status_code == 409
    assert save(client, lead, review(notes="New evidence"), revision=1).json()["revision"] == 2
    assert save(client, lead, review(notes="Stale editor"), revision=1).status_code == 409
    item = client.get("/insurance-growth/overview").json()["prospects"]["items"][0]
    assert item["review"]["notes"] == "New evidence"


@pytest.mark.parametrize("changes", [
    {"source_ref": "  "}, {"observed_at": "2099-01-01T00:00:00Z"},
    {"observed_at": "2026-01-01T00:00:00"},
    {"renewal_date": "2027-01-01"},
    {"renewal_date": "2027-01-01", "renewal_basis": "business_registration"},
    {"renewal_basis": "customer_confirmed", "renewal_evidence_ref": "fixture://customer"},
    {"policy_number": "not-permitted"},
])
def test_reject_unsupported_unproven_or_future_evidence(workspace, changes):
    client, engine, _ = workspace
    assert save(client, add_lead(engine), review(**changes)).status_code == 422


@pytest.mark.parametrize("field,value", [
    ("name", ""), ("role", ""), ("evidence_ref", " "),
    ("checked_at", "2099-01-01T00:00:00Z"), ("phone", "not a number"),
])
def test_verified_contact_requires_supported_identity_and_evidence(workspace, field, value):
    client, engine, _ = workspace
    payload = review()
    payload["contacts"][0][field] = value
    assert save(client, add_lead(engine), payload).status_code == 422


def test_duplicate_phone_and_excess_contacts_rejected(workspace):
    client, engine, _ = workspace
    payload = review()
    payload["contacts"] *= 2
    assert save(client, add_lead(engine), payload).status_code == 422
    payload["contacts"] *= 3
    assert save(client, add_lead(engine), payload).status_code == 422


def test_suppression_covers_alternate_contacts_and_stale_verification(workspace):
    client, engine, _ = workspace
    lead = add_lead(engine)
    payload = review(observed_at=(datetime.now(timezone.utc) - timedelta(days=100)).isoformat())
    payload["contacts"][0]["checked_at"] = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
    assert save(client, lead, payload).status_code == 200
    with Session(engine) as db:
        db.add(DoNotContact(kind="phone", value="6175550102", source="fixture"))
        db.commit()
    row = client.get("/insurance-growth/overview").json()["prospects"]["items"][0]
    assert row["suppressed"]
    assert {"do_not_contact", "source_evidence_stale", "decision_maker_contact_not_recently_verified"} <= set(row["review_flags"])


def test_cross_sell_uses_explicit_relationship_and_never_assumes_missing_cover(workspace):
    client, engine, _ = workspace
    lead_id = UUID(add_lead(engine))
    with Session(engine) as db:
        db.add_all([
            Client(name="Commercial fixture", business="insurance", lead_id=lead_id, line="commercial", status="Active"),
            Client(name="Auto fixture", business="insurance", lead_id=lead_id, line="auto", status="Renewed"),
            Client(name="Other business", business="music", line="commercial", status="Active"),
            Client(name="Cancelled fixture", business="insurance", line="commercial", status="Cancelled"),
            Client(name="Unknown fixture", business="insurance", status="Active"),
        ])
        db.commit()
    result = client.get("/insurance-growth/overview").json()["cross_sell"]
    assert result["total_records"] == 3
    assert len(result["items"]) == 2
    group = next(r for r in result["items"] if r["lead_id"])
    assert group["recorded_lines"] == ["auto", "commercial"]
    assert not any("personal auto" in q for q in group["questions"])
    assert any("home or renters" in q for q in group["questions"])
    assert result["basis"] == "recorded_active_client_policies_not_complete_coverage"


def test_cross_sell_dnc_removes_questions_even_when_lead_contact_differs(workspace):
    client, engine, _ = workspace
    lead_id = UUID(add_lead(engine))
    with Session(engine) as db:
        db.add(Client(name="Suppressed fixture", lead_id=lead_id, business="insurance", line="commercial",
                      phone="+16175550109", status="Active"))
        db.add(DoNotContact(kind="phone", value="6175550101"))
        db.commit()
    item = client.get("/insurance-growth/overview").json()["cross_sell"]["items"][0]
    assert item["suppressed"] and item["questions"] == []


def test_funnel_deduplicates_leads_and_uses_intersections_not_unrelated_sales(workspace):
    client, engine, _ = workspace
    ids = [UUID(add_lead(engine)) for _ in range(3)]
    unrelated = UUID(add_lead(engine, segment="consulting"))
    now = datetime.now(timezone.utc) - timedelta(seconds=5)
    with Session(engine) as db:
        db.add_all([
            ConversationOutcome(lead_id=ids[0], method="call", outcome="answered", created_at=now),
            ConversationOutcome(lead_id=ids[0], method="call", outcome="answered", quote_sent=True, created_at=now),
            ConversationOutcome(lead_id=ids[0], method="email", quote_sent=True, conversation_status="sold", created_at=now),
            ConversationOutcome(lead_id=ids[1], method="call", outcome="wrong_number", created_at=now),
            ConversationOutcome(lead_id=ids[2], method="email", conversation_status="sold", created_at=now),
            ConversationOutcome(lead_id=unrelated, method="call", outcome="answered", created_at=now),
            ConversationOutcome(lead_id=ids[1], method="call", outcome="answered", created_at=now-timedelta(days=31)),
            ConversationOutcome(lead_id=ids[1], method="call", outcome="answered", created_at=now+timedelta(days=1)),
        ])
        db.commit()
    save(client, str(ids[0]))
    f = client.get("/insurance-growth/overview?days=30").json()["funnel"]
    assert f["call_attempts"] == 3
    assert f["answered_leads"] == 1 and f["quoted_leads"] == 1 and f["sold_leads"] == 2
    assert f["quoted_and_sold_leads"] == 1
    assert f["answer_to_quote_rate"] == 1 and f["quote_to_sale_rate"] == 1
    assert f["invalid_number_attempts"] == 1
    assert {r["source"] for r in f["by_source"]} == {"unattributed", "massachusetts_public_record"}
    assert f["source_attribution"] == "current_review_source_not_historical_acquisition"


def test_non_insurance_leads_and_invalid_identifiers_rejected(workspace):
    client, engine, _ = workspace
    assert save(client, add_lead(engine, segment="consulting")).status_code == 404
    assert save(client, str(uuid4())).status_code == 404
    assert save(client, "not-a-uuid").status_code == 422
    assert client.get("/insurance-growth/overview?days=0").status_code == 422


def test_real_role_dependencies_block_unauthenticated_requests(workspace):
    client, _, app = workspace
    del app.dependency_overrides[routes._read]
    del app.dependency_overrides[routes._write]
    assert client.get("/insurance-growth/overview").status_code == 401
    assert save(client, str(uuid4())).status_code == 401
