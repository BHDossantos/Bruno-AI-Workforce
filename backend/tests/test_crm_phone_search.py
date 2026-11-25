"""Exercise the actual CRM list query with synthetic data, no app/provider startup."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.crm import list_contacts
from app.models import ManualContact


@pytest.fixture
def contacts():
    engine = create_engine("sqlite://")
    ManualContact.__table__.create(engine)
    with Session(engine) as db:
        db.add_all([
            ManualContact(name="Example Local", phone="202-555-0142"),
            ManualContact(name="Example NANP", phone="+1 (202) 555-0142"),
            ManualContact(name="Example Italian", phone="+39 02\u00a05555 0142"),
            ManualContact(name="Example Italian Dialing Prefix", phone="0039 02 5555 0142"),
            ManualContact(name="Example Other Country", phone="+44 20 2555 0142"),
            ManualContact(name="Example No Phone", email="contact@example.test"),
        ])
        db.commit()
        yield db
    engine.dispose()


@pytest.mark.parametrize("query", ["2025550142", "(202) 555-0142", "12025550142", "+1 202 555 0142", "0012025550142"])
def test_north_american_format_variants_keep_other_country_out(contacts, query):
    assert {row["name"] for row in list_contacts(contacts, source="manual", q=query)} == {
        "Example Local", "Example NANP",
    }


@pytest.mark.parametrize("query", ["+390255550142", "0039 02 5555 0142", "+39 (02) 5555-0142"])
def test_international_country_code_and_significant_zero(contacts, query):
    assert {row["name"] for row in list_contacts(contacts, source="manual", q=query)} == {
        "Example Italian", "Example Italian Dialing Prefix",
    }


def test_preserves_text_email_and_partial_phone_matching(contacts):
    assert [row["name"] for row in list_contacts(contacts, source="manual", q="CONTACT@EXAMPLE")] == [
        "Example No Phone",
    ]
    assert {row["name"] for row in list_contacts(contacts, source="manual", q="555-0142")} == {
        "Example Local", "Example NANP",
    }
