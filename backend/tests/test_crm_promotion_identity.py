"""Synthetic callable-contact integration regressions, without dispatch."""

from uuid import uuid4

import pytest
from fastapi import HTTPException

from .conftest import requires_db


@requires_db
def test_promotion_reuses_full_normalized_phone_and_repeats(client, monkeypatch):
    from app import crm
    from app.database import SessionLocal
    from app.models import Lead, ManualContact

    db = SessionLocal()
    try:
        monkeypatch.setattr(db, "commit", db.flush)
        original = Lead(segment="commercial", phone="+1 212-555-0187")
        contact = ManualContact(name="Synthetic fixture", phone="(212) 555-0187")
        db.add_all([original, contact])
        db.flush()
        before = db.query(Lead).count()
        cid = f"contact:{contact.id}"
        assert crm.promote_to_lead(db, cid) == str(original.id)
        assert crm.promote_to_lead(db, cid) == str(original.id)
        assert db.query(Lead).count() == before
    finally:
        db.rollback()
        db.close()


@requires_db
def test_promotion_disagreeing_or_cross_business_identity_returns_conflict_without_writes(client, monkeypatch):
    from app.database import SessionLocal
    from app.models import Lead, ManualContact
    from app.routers.crm import contact_to_lead

    db = SessionLocal()
    try:
        monkeypatch.setattr(db, "commit", db.flush)
        email = f"synthetic-{uuid4()}@example.test"
        db.add_all([
            Lead(segment="commercial", email=email),
            Lead(segment="commercial", phone="+1 212-555-0193"),
            Lead(segment="consulting", phone="+1 212-555-0194"),
        ])
        mismatch = ManualContact(name="Synthetic mismatch", email=email, phone="2125550193")
        cross = ManualContact(name="Synthetic cross business", phone="2125550194")
        db.add_all([mismatch, cross])
        db.flush()
        before = db.query(Lead).count()
        for c in [mismatch, cross]:
            with pytest.raises(HTTPException) as e:
                contact_to_lead(f"contact:{c.id}", db)
            assert e.value.status_code == 409
        assert db.query(Lead).count() == before
    finally:
        db.rollback()
        db.close()
