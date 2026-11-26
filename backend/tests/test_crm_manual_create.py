"""Use actual transactions and synthetic contacts without provider calls."""
import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app import crm
from app.models import ManualContact


@pytest.fixture
def engine():
    engine = create_engine("sqlite://")
    ManualContact.__table__.create(engine)
    yield engine
    engine.dispose()


def test_name_only_save_returns_the_canonical_contact(engine, monkeypatch):
    calls = []
    monkeypatch.setattr(crm.memory, "add", lambda *a, **kw: calls.append(kw))
    with Session(engine) as db:
        result = crm.add_contact(db, name="Synthetic Name Only")
    with Session(engine) as reader:
        row = reader.scalars(select(ManualContact)).one()
        assert result["id"] == f"contact:{row.id}"
        assert result["name"] == row.name == "Synthetic Name Only"
        assert result["email"] is None and result["phone"] is None
    assert len(calls) == 1


def test_primary_commit_error_still_fails_without_indexing(engine, monkeypatch):
    calls = []
    monkeypatch.setattr(crm.memory, "add", lambda *a, **kw: calls.append(kw))
    with Session(engine) as db:
        @event.listens_for(db, "before_commit")
        def fail_commit(session):
            raise OperationalError("COMMIT", {}, RuntimeError("synthetic failure"))

        with pytest.raises(OperationalError):
            crm.add_contact(db, name="Synthetic Uncommitted Contact")
    with Session(engine) as reader:
        assert reader.scalars(select(ManualContact)).first() is None
    assert calls == []


def test_index_failure_rolls_back_secondary_work_and_returns_saved_contact(engine, monkeypatch, caplog):
    calls = []

    def broken_index(db, content, **kwargs):
        calls.append(content)
        db.add(ManualContact(name="Synthetic Secondary Transaction Marker"))
        db.flush()
        raise RuntimeError(f"private message: {content}")

    monkeypatch.setattr(crm.memory, "add", broken_index)
    with Session(engine) as db:
        result = crm.add_contact(db, name="Synthetic Committed Contact")
        assert not db.in_transaction()
        assert len(db.scalars(select(ManualContact)).all()) == 1
    with Session(engine) as reader:
        row = reader.scalars(select(ManualContact)).one()
        assert result["id"] == f"contact:{row.id}"
        assert result["name"] == row.name == "Synthetic Committed Contact"
    assert len(calls) == 1
    assert "optional search memory update failed" in caplog.text
    assert "Synthetic Committed Contact" not in caplog.text
