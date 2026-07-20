"""Editable CRM record — the universal customer profile.

A schema-driven, module-based customer record so the SAME core CRM serves every
business, with industry-specific field groups plugged in on top:

    CORE (shared by every business): identity, contact, address, source, sales,
    compliance, plus unlimited free-form CUSTOM fields.
    MODULES (industry plug-ins): "insurance" adds customer_profile / property /
    coverage and the repeatable vehicles / drivers / quotes / policies / claims.

Everything is stored as JSON under ``Lead.intake["crm"]`` — an EXISTING JSONB
column — so the whole record is editable and extensible with NO database
migration (the prod DB can't safely add columns). The frontend renders the form
generically from ``schema_for()``, so adding a field or a whole new module is a
change here only. A handful of fields also sync down to the real Lead columns
(name/email/phone/status/score) so the rest of the app keeps working unchanged.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from .models import Lead


def _f(key: str, label: str, type: str = "text", options: list[str] | None = None) -> dict:
    d = {"key": key, "label": label, "type": type}
    if options:
        d["options"] = options
    return d


# ── Shared core sections (every business, every module) ───────────────────────
CORE_SECTIONS: list[dict] = [
    {"key": "identity", "label": "Personal", "fields": [
        _f("first_name", "First Name"), _f("middle_name", "Middle Name"),
        _f("last_name", "Last Name"), _f("dob", "Date of Birth", "date"),
        _f("gender", "Gender", "select", ["", "Female", "Male", "Other", "Prefer not to say"]),
        _f("marital_status", "Marital Status", "select",
           ["", "Single", "Married", "Divorced", "Widowed", "Domestic Partner"]),
        _f("occupation", "Occupation"), _f("employer", "Employer"),
        _f("years_at_employer", "Years at Employer", "number"),
        _f("annual_income", "Annual Income", "number"),
        _f("language", "Language Preference"),
    ]},
    {"key": "contact", "label": "Contact", "fields": [
        _f("primary_phone", "Primary Phone", "phone"), _f("secondary_phone", "Secondary Phone", "phone"),
        _f("work_phone", "Work Phone", "phone"), _f("email", "Email", "email"),
        _f("secondary_email", "Secondary Email", "email"),
        _f("preferred_contact", "Preferred Contact Method", "select", ["", "Call", "Text", "Email"]),
        _f("best_time", "Best Time to Call", "select", ["", "Morning", "Afternoon", "Evening", "Weekend"]),
        _f("timezone", "Time Zone"),
    ]},
    {"key": "address", "label": "Address", "fields": [
        _f("street", "Street"), _f("apartment", "Apartment"), _f("city", "City"),
        _f("state", "State"), _f("zip", "ZIP"), _f("county", "County"), _f("country", "Country"),
        _f("years_at_address", "Years at Address", "number"),
        _f("residency", "Own / Rent", "select", ["", "Own", "Rent"]),
        _f("move_in_date", "Move-in Date", "date"),
    ]},
    {"key": "source", "label": "Lead Source", "fields": [
        _f("lead_source", "Lead Source", "select",
           ["", "EverQuote", "SmartFinancial", "QuoteWizard", "Google", "Facebook",
            "Referral", "Website", "Walk-in", "Phone", "Commercial Prospecting"]),
        _f("campaign_name", "Campaign Name"), _f("cost_per_lead", "Cost Per Lead", "number"),
        _f("acquisition_date", "Acquisition Date", "date"),
        _f("lead_temp", "Lead Score", "select", ["", "Hot", "Warm", "Cold"]),
        _f("intent_score", "Intent Score (0-100)", "number"),
    ]},
    {"key": "sales", "label": "Sales", "fields": [
        _f("assigned_producer", "Assigned Producer"),
        _f("status", "Status", "select",
           ["", "New", "Contacted", "Qualified", "Quoted", "Sold", "Lost", "Renewal", "Referral"]),
        _f("next_action", "Next Action"), _f("next_followup", "Next Follow-up", "date"),
        _f("last_contact", "Last Contact", "date"), _f("last_contact_method", "Last Contact Method"),
    ]},
    {"key": "compliance", "label": "Compliance", "fields": [
        _f("consent_to_call", "Consent to Call", "bool"),
        _f("consent_to_text", "Consent to Text", "bool"),
        _f("consent_to_email", "Consent to Email", "bool"),
        _f("tcpa", "TCPA Consent", "bool"), _f("dnc", "Do Not Call", "bool"),
        _f("opt_out", "Opted Out", "bool"), _f("privacy_accepted", "Privacy Accepted", "bool"),
        _f("disclosure_sent", "Disclosure Sent", "bool"),
    ]},
]

# ── Industry modules (plug-ins layered on top of the shared core) ─────────────
_INSURANCE_SECTIONS: list[dict] = [
    {"key": "customer_profile", "label": "Current Coverage", "fields": [
        _f("current_carrier", "Current Carrier"), _f("current_premium", "Current Premium", "number"),
        _f("renewal_date", "Renewal Date", "date"), _f("years_with_carrier", "Years With Carrier", "number"),
        _f("reason_for_shopping", "Reason for Shopping", "select",
           ["", "Price", "Service", "Coverage", "New Vehicle", "Moved", "Referral", "Bad Experience", "Other"]),
    ]},
    {"key": "property", "label": "Property (Home)", "fields": [
        _f("address", "Address"),
        _f("residence_type", "Residence Type", "select",
           ["", "Primary Residence", "Secondary", "Rental", "Condo", "Townhouse"]),
        _f("year_built", "Year Built", "number"), _f("square_feet", "Square Feet", "number"),
        _f("construction", "Construction"), _f("roof", "Roof"), _f("garage", "Garage"),
        _f("foundation", "Foundation"), _f("replacement_cost", "Replacement Cost", "number"),
        _f("mortgage_company", "Mortgage Company"),
    ]},
    {"key": "coverage", "label": "Lines of Coverage", "fields": [
        _f("lines", "Coverage Lines (comma-separated: Auto, Home, Renters, Condo, Umbrella, "
                    "Flood, Life, Commercial, Workers Comp, General Liability, Cyber, Commercial Auto)",
           "textarea"),
    ]},
]

# Repeatable lists per module: each row is a dict of these fields.
_INSURANCE_LISTS: list[dict] = [
    {"key": "vehicles", "label": "Vehicles", "fields": [
        _f("year", "Year", "number"), _f("make", "Make"), _f("model", "Model"),
        _f("vin", "VIN"), _f("plate", "Plate"),
        _f("ownership", "Ownership", "select", ["", "Owned", "Finance", "Lease"]),
        _f("annual_mileage", "Annual Mileage", "number"),
        _f("use", "Use", "select", ["", "Personal", "Business"]),
        _f("garaged_address", "Garaged Address"), _f("primary_driver", "Primary Driver"),
    ]},
    {"key": "drivers", "label": "Drivers", "fields": [
        _f("name", "Name"), _f("relationship", "Relationship"), _f("dob", "DOB", "date"),
        _f("dl_number", "Driver License #"), _f("dl_state", "State"),
        _f("license_status", "License Status"), _f("years_licensed", "Years Licensed", "number"),
        _f("accidents", "Accidents", "number"), _f("violations", "Violations", "number"),
        _f("claims", "Claims", "number"), _f("excluded", "Excluded Driver", "bool"),
        _f("good_student", "Good Student", "bool"), _f("military", "Military", "bool"),
        _f("senior", "Senior", "bool"), _f("occupation", "Occupation"),
    ]},
    {"key": "quotes", "label": "Quotes", "fields": [
        _f("carrier", "Carrier"), _f("premium", "Premium", "number"),
        _f("effective_date", "Effective Date", "date"), _f("expiration", "Expiration", "date"),
        _f("deductible", "Deductible", "number"), _f("limits", "Coverage Limits"),
        _f("discounts", "Discounts"), _f("bundle", "Bundle", "bool"),
        _f("status", "Status", "select", ["", "Proposal Sent", "Accepted", "Declined"]),
        _f("reason_lost", "Reason Lost"),
    ]},
    {"key": "policies", "label": "Policies", "fields": [
        _f("policy_number", "Policy Number"), _f("carrier", "Carrier"),
        _f("effective", "Effective", "date"), _f("expiration", "Expiration", "date"),
        _f("premium", "Premium", "number"), _f("payment_plan", "Payment Plan"),
        _f("status", "Status", "select", ["", "Active", "Cancelled", "Expired", "Pending"]),
    ]},
    {"key": "claims", "label": "Claims", "fields": [
        _f("claim_number", "Claim Number"), _f("date", "Date", "date"),
        _f("status", "Status"), _f("amount", "Amount", "number"),
        _f("description", "Description", "textarea"), _f("adjuster", "Claim Adjuster"),
        _f("followup", "Follow-up", "date"),
    ]},
]

MODULES: dict[str, dict] = {
    "insurance": {"label": "Insurance", "sections": _INSURANCE_SECTIONS, "lists": _INSURANCE_LISTS},
    # Future plug-ins (restaurant / consulting / real_estate / …) register here with
    # the same shape — the core CRM + UI need no changes to support them.
    "general": {"label": "General", "sections": [], "lists": []},
}

# Which module a lead belongs to. Insurance leads are personal/EverQuote; everything
# else uses the shared core only until its module is built.
def module_for(lead: Lead) -> str:
    seg = (lead.segment or "").lower()
    cat = (lead.category or "").lower()
    if seg == "personal" or "everquote" in cat or "insurance" in cat:
        return "insurance"
    return "insurance" if seg in ("", "commercial") and not cat else "general"


def schema_for_module(module: str = "insurance") -> dict:
    """The form schema for a module WITHOUT needing a lead — used by the 'Add
    client' form, which has no lead yet."""
    mod = MODULES.get(module, MODULES["general"])
    return {
        "module": module if module in MODULES else "general",
        "module_label": mod["label"],
        "core_sections": CORE_SECTIONS,
        "module_sections": mod["sections"],
        "lists": mod["lists"],
        "modules_available": [{"key": k, "label": v["label"]} for k, v in MODULES.items()],
    }


def schema_for(lead: Lead) -> dict:
    """The full form schema for this lead: shared core sections + its module's
    sections + repeatable lists. The frontend renders inputs straight from this."""
    module = module_for(lead)
    mod = MODULES.get(module, MODULES["general"])
    return {
        "module": module,
        "module_label": mod["label"],
        "core_sections": CORE_SECTIONS,
        "module_sections": mod["sections"],
        "lists": mod["lists"],
        "modules_available": [{"key": k, "label": v["label"]} for k, v in MODULES.items()],
    }


def get_crm(lead: Lead) -> dict:
    """The stored CRM record (all sections + lists + custom fields). Core columns
    are surfaced too so the form shows the live name/email/phone/status."""
    crm = dict((lead.intake or {}).get("crm") or {})
    # Seed the identity/contact/sales fields from the real columns when the CRM
    # blob hasn't overridden them, so a never-edited lead still shows its data.
    crm.setdefault("identity", {})
    crm.setdefault("contact", {})
    crm.setdefault("sales", {})
    crm["contact"].setdefault("email", lead.email or "")
    crm["contact"].setdefault("primary_phone", lead.phone or "")
    crm["sales"].setdefault("status", lead.status or "New")
    if lead.owner_name and not (crm["identity"].get("first_name") or crm["identity"].get("last_name")):
        parts = lead.owner_name.split(None, 1)
        crm["identity"]["first_name"] = parts[0]
        crm["identity"]["last_name"] = parts[1] if len(parts) > 1 else ""
    return {
        "lead_id": str(lead.id),
        "module": module_for(lead),
        "profile": crm,
        "custom": (lead.intake or {}).get("crm", {}).get("custom") or {},
        "updated_at": (lead.intake or {}).get("crm_updated_at"),
    }


def _sync_core_columns(lead: Lead, crm: dict) -> None:
    """Push the handful of fields the rest of the app reads back onto the real
    Lead columns, so editing the CRM keeps name/email/phone/status consistent."""
    ident, contact, sales = crm.get("identity") or {}, crm.get("contact") or {}, crm.get("sales") or {}
    name = " ".join(p for p in [ident.get("first_name"), ident.get("last_name")] if p).strip()
    if name:
        lead.owner_name = name
    if contact.get("email"):
        lead.email = contact["email"].strip()
    if contact.get("primary_phone"):
        lead.phone = str(contact["primary_phone"]).strip()
    if sales.get("status"):
        lead.status = sales["status"]


def update_crm(db: Session, lead_id: str, profile: dict, custom: dict | None = None) -> dict | None:
    """Merge edited sections into the lead's CRM record (deep-merge per section;
    repeatable lists are replaced wholesale). Returns None if the lead is missing.
    Reassigns ``intake`` as a new dict so SQLAlchemy detects the JSONB change."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        return None
    intake = dict(lead.intake or {})
    crm = dict(intake.get("crm") or {})
    for section, value in (profile or {}).items():
        if isinstance(value, list):            # repeatable list → replace
            crm[section] = value
        elif isinstance(value, dict):          # field group → merge
            merged = dict(crm.get(section) or {})
            merged.update({k: v for k, v in value.items()})
            crm[section] = merged
        else:
            crm[section] = value
    if custom is not None:
        crm["custom"] = dict(custom)
    intake["crm"] = crm
    intake["crm_updated_at"] = datetime.now(timezone.utc).isoformat()
    lead.intake = intake                       # reassign so the ORM flushes it
    _sync_core_columns(lead, crm)
    db.commit()
    db.refresh(lead)
    return get_crm(lead)


def create_lead(db: Session, profile: dict, custom: dict | None = None,
                segment: str = "personal", category: str | None = None) -> Lead:
    """Create a new lead from an edited CRM profile (the 'Add client' form)."""
    ident = (profile or {}).get("identity") or {}
    contact = (profile or {}).get("contact") or {}
    name = " ".join(p for p in [ident.get("first_name"), ident.get("last_name")] if p).strip()
    lead = Lead(segment=segment or "personal", category=category,
                owner_name=name or None,
                email=(contact.get("email") or None),
                phone=(contact.get("primary_phone") or None),
                status="New", intake={})
    db.add(lead)
    db.flush()   # assign an id
    updated = update_crm(db, str(lead.id), profile, custom)
    return lead if updated else lead
