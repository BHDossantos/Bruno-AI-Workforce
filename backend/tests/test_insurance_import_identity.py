"""Synthetic import identity fixtures; no dispatch or live records."""

from datetime import date
from uuid import uuid4

from .conftest import requires_db


def test_import_phone_key_compares_full_number_only():
    from app.import_phone_key import import_phone_key

    assert import_phone_key("(202) 555-0187") == import_phone_key("+1 202-555-0187") == "12025550187"
    assert import_phone_key("+44 20 2555 0187") != import_phone_key("2025550187")
    assert import_phone_key("2025550187 x42") is None
    assert import_phone_key("5550187") is None


@requires_db
def test_import_attaches_email_to_single_matching_phone_without_new_followups(client, monkeypatch):
    from app import importer
    from app.database import SessionLocal
    from app.models import FollowUp, Lead

    db = SessionLocal()
    try:
        # All changes stay inside the synthetic test transaction.
        monkeypatch.setattr(db, "commit", db.flush)
        monkeypatch.setattr(importer, "_schedule_followups", lambda *_: (_ for _ in ()).throw(AssertionError("no new follow-ups")))
        phone = "+1 202-555-0187"
        email = f"synthetic-{uuid4()}@example.test"
        original = Lead(segment="commercial", phone=phone, status="New", owner_name="Synthetic")
        db.add(original)
        db.flush()
        db.add(FollowUp(entity_type="lead", entity_id=original.id, step=1, due_date=date(2099, 1, 1)))
        db.flush()

        result = importer.process_leads_csv(db, [
            {"phone": "(202) 555-0187", "email": email},
            {"phone": "(202) 555-0187", "email": email},
        ])

        assert result["imported"] == result["queued"] == result["sent"] == result["skipped_identity_conflict"] == 0
        assert result["updated"] == 2  # both rows map to the same preserved identity
        db.refresh(original)
        assert original.email == email
        assert [lead.id for lead in db.query(Lead).filter(Lead.email == email).all()] == [original.id]
        followups = db.query(FollowUp).filter(FollowUp.entity_id == original.id).all()
        assert [(row.step, row.due_date) for row in followups] == [(1, date(2099, 1, 1))]
    finally:
        db.rollback()
        db.close()


@requires_db
def test_import_conflicts_are_skipped_without_writes_or_new_followups(client, monkeypatch):
    from app import importer
    from app.database import SessionLocal
    from app.models import Lead

    db = SessionLocal()
    try:
        monkeypatch.setattr(db, "commit", db.flush)
        monkeypatch.setattr(importer, "_schedule_followups", lambda *_: (_ for _ in ()).throw(AssertionError("no new follow-ups")))
        fresh = f"fresh-{uuid4()}@example.test"
        foreign_email = f"elsewhere-{uuid4()}@example.test"
        seeded = [
            Lead(segment="commercial", phone="+1 202-555-0193", owner_name="phone record"),
            Lead(segment="commercial", email=fresh, owner_name="email record"),
            Lead(segment="commercial", phone="+1 202-555-0194", owner_name="shared phone A"),
            Lead(segment="commercial", phone="(202) 555-0194", owner_name="shared phone B"),
            Lead(segment="consulting", phone="+1 202-555-0195", owner_name="foreign business"),
            Lead(segment="commercial", phone="+1 202-555-0196", owner_name="local phone"),
            Lead(segment="consulting", email=foreign_email, owner_name="foreign email"),
        ]
        db.add_all(seeded)
        db.flush()
        total_before = db.query(Lead).count()

        result = importer.process_leads_csv(db, [
            {"email": fresh, "phone": "(202) 555-0193", "name": "must not overwrite"},
            {"email": "shared-fixture@example.test", "phone": "2025550194"},
            {"email": "cross-business-fixture@example.test", "phone": "2025550195"},
            {"email": foreign_email, "phone": "2025550196"},
        ])

        assert result["imported"] == result["updated"] == result["queued"] == result["sent"] == 0
        assert result["skipped_identity_conflict"] == 4
        assert result["skipped_no_contact"] == 0
        assert db.query(Lead).count() == total_before
        assert [row.email for row in seeded] == [None, fresh, None, None, None, None, foreign_email]
        assert seeded[0].owner_name == "phone record"
    finally:
        db.rollback()
        db.close()
