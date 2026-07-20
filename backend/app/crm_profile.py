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

# ── SavoryMind restaurant module ──────────────────────────────────────────────
_RESTAURANT_SECTIONS: list[dict] = [
    {"key": "restaurant_profile", "label": "Restaurant", "fields": [
        _f("name", "Restaurant Name"), _f("legal_name", "Legal Business Name"),
        _f("business_type", "Business Type", "select",
           ["", "Restaurant", "Cafe", "Bar", "Food Truck", "Bakery", "Pizzeria",
            "Fast Food", "Fine Dining", "Ghost Kitchen"]),
        _f("cuisine", "Cuisine Type"), _f("website", "Website"),
        _f("phone", "Phone", "phone"), _f("email", "Email", "email"),
        _f("instagram", "Instagram"), _f("facebook", "Facebook"), _f("tiktok", "TikTok"),
        _f("google_business", "Google Business"),
        _f("address", "Address"), _f("city", "City"), _f("state", "State"),
        _f("zip", "ZIP"), _f("country", "Country"),
        _f("opening_date", "Opening Date", "date"),
        _f("locations_count", "Number of Locations", "number"),
        _f("max_seating", "Maximum Seating", "number"),
        _f("pos_provider", "POS Provider"), _f("reservation_system", "Reservation System"),
        _f("delivery_partners", "Delivery Partners (Uber Eats, DoorDash, …)"),
        _f("business_hours", "Business Hours"),
        _f("parking", "Parking", "bool"), _f("wifi", "WiFi", "bool"),
        _f("pet_friendly", "Pet Friendly", "bool"), _f("outdoor_seating", "Outdoor Seating", "bool"),
    ]},
    {"key": "owner_crm", "label": "Owner", "fields": [
        _f("owner_name", "Owner Name"), _f("manager", "Manager"),
        _f("chef", "Chef"), _f("birthday", "Birthday", "date"),
        _f("preferred_contact", "Preferred Contact", "select", ["", "Call", "Text", "Email", "WhatsApp"]),
        _f("phone", "Phone", "phone"), _f("email", "Email", "email"),
        _f("whatsapp", "WhatsApp", "phone"), _f("linkedin", "LinkedIn"),
        _f("investment_goals", "Investment Goals", "textarea"),
        _f("expansion_plans", "Expansion Plans", "textarea"),
        _f("last_meeting", "Last Meeting", "date"),
        _f("relationship_score", "Relationship Score (0-100)", "number"),
        _f("notes", "Notes", "textarea"),
    ]},
    {"key": "intelligence", "label": "Restaurant Intelligence", "fields": [
        _f("revenue_estimate", "Revenue Estimate", "number"),
        _f("google_rating", "Google Rating"), _f("review_count", "Review Count", "number"),
        _f("review_sentiment", "Review Sentiment"), _f("busy_hours", "Busy Hours"),
        _f("health_score", "Health Score (0-100)", "number"),
        _f("growth_score", "Growth Score (0-100)", "number"),
        _f("risk_score", "Risk Score (0-100)", "number"),
    ]},
    {"key": "finance", "label": "Finance", "fields": [
        _f("monthly_revenue", "Monthly Revenue", "number"), _f("cogs", "COGS", "number"),
        _f("labor_pct", "Labor %", "number"), _f("food_cost_pct", "Food Cost %", "number"),
        _f("average_ticket", "Average Ticket", "number"),
        _f("revenue_per_seat", "Revenue Per Seat", "number"),
    ]},
    {"key": "sales_pipeline", "label": "SavoryMind Sales", "fields": [
        _f("stage", "Pipeline Stage", "select",
           ["", "Restaurant Found", "Owner Identified", "First Contact", "Demo Scheduled",
            "Demo Completed", "Proposal Sent", "Negotiation", "Contract Signed",
            "Onboarding", "Go Live", "Customer Success", "Expansion", "Referral"]),
        _f("assigned_rep", "Assigned Rep"), _f("deal_size", "Deal Size", "number"),
        _f("close_probability", "Close Probability (0-100)", "number"),
        _f("next_action", "Next Action"), _f("next_followup", "Next Follow-up", "date"),
    ]},
]
_RESTAURANT_LISTS: list[dict] = [
    {"key": "locations", "label": "Locations", "fields": [
        _f("address", "Address"), _f("phone", "Phone", "phone"), _f("manager", "Manager"),
        _f("seats", "Seats", "number"), _f("revenue", "Revenue", "number"),
        _f("employees", "Employees", "number"), _f("pos", "POS"),
    ]},
    {"key": "employees", "label": "Employees", "fields": [
        _f("name", "Name"),
        _f("position", "Position", "select",
           ["", "Manager", "Chef", "Cook", "Server", "Bartender", "Host", "Dishwasher", "Cleaner"]),
        _f("phone", "Phone", "phone"), _f("email", "Email", "email"),
        _f("hire_date", "Hire Date", "date"), _f("hourly_rate", "Hourly Rate", "number"),
        _f("performance_score", "Performance Score", "number"),
    ]},
    {"key": "customers", "label": "Customers", "fields": [
        _f("first_name", "First Name"), _f("last_name", "Last Name"),
        _f("phone", "Phone", "phone"), _f("email", "Email", "email"),
        _f("birthday", "Birthday", "date"), _f("allergies", "Allergies"),
        _f("favorite_dishes", "Favorite Dishes"), _f("average_spend", "Average Spend", "number"),
        _f("visit_count", "Visit Count", "number"), _f("lifetime_value", "Lifetime Value", "number"),
        _f("vip", "VIP", "bool"), _f("loyalty_level", "Loyalty Level"),
        _f("marketing_consent", "Marketing Consent", "bool"),
    ]},
    {"key": "reservations", "label": "Reservations", "fields": [
        _f("customer", "Customer"), _f("party_size", "Party Size", "number"),
        _f("date", "Date", "date"), _f("time", "Time"), _f("table", "Table"),
        _f("occasion", "Special Occasion"),
        _f("status", "Status", "select", ["", "Confirmed", "Cancelled", "No Show", "Completed"]),
        _f("notes", "Notes"),
    ]},
    {"key": "menu", "label": "Menu", "fields": [
        _f("category", "Category", "select", ["", "Appetizers", "Main", "Dessert", "Drinks", "Specials"]),
        _f("item", "Item"), _f("description", "Description"), _f("price", "Price", "number"),
        _f("food_cost", "Food Cost", "number"), _f("margin", "Margin", "number"),
        _f("allergens", "Allergens"), _f("popularity_score", "Popularity Score", "number"),
        _f("available", "Available", "bool"),
    ]},
    {"key": "inventory", "label": "Inventory", "fields": [
        _f("ingredient", "Ingredient"), _f("supplier", "Supplier"),
        _f("current_quantity", "Current Quantity", "number"),
        _f("reorder_level", "Reorder Level", "number"), _f("unit", "Unit"),
        _f("cost", "Cost", "number"), _f("expiration", "Expiration", "date"),
    ]},
    {"key": "suppliers", "label": "Suppliers", "fields": [
        _f("name", "Supplier Name"), _f("contact", "Contact"),
        _f("phone", "Phone", "phone"), _f("email", "Email", "email"),
        _f("products", "Products"), _f("lead_time", "Lead Time"),
        _f("payment_terms", "Payment Terms"), _f("performance_score", "Performance Score", "number"),
    ]},
    {"key": "reviews", "label": "Reviews", "fields": [
        _f("platform", "Platform", "select", ["", "Google", "TripAdvisor", "Yelp", "Facebook", "OpenTable"]),
        _f("rating", "Rating", "number"), _f("date", "Date", "date"),
        _f("sentiment", "Sentiment", "select", ["", "Positive", "Neutral", "Negative"]),
        _f("text", "Review", "textarea"),
    ]},
]

MODULES: dict[str, dict] = {
    # ``core``: does this module use the shared PERSON-centric core sections
    # (identity/contact/address/…)? Insurance does (the record is a person).
    # Restaurant does not — its record is a business, fully described by its own
    # sections — so it opts out and stays self-contained.
    "insurance": {"label": "Insurance", "core": True,
                  "sections": _INSURANCE_SECTIONS, "lists": _INSURANCE_LISTS},
    "restaurant": {"label": "SavoryMind (Restaurant)", "core": False,
                   "sections": _RESTAURANT_SECTIONS, "lists": _RESTAURANT_LISTS},
    # Future plug-ins (consulting / real_estate / education / music / …) register
    # here with the same shape — the core CRM + UI need no changes to support them.
    "general": {"label": "General", "core": True, "sections": [], "lists": []},
}

# The CRM engine is entity-generic: it drives both Lead (insurance/general) and
# Restaurant (SavoryMind) records, storing the profile in whichever JSONB column
# that entity already has — no schema migration needed.
_JSON_ATTR = {"lead": "intake", "restaurant": "menu_analysis"}


def _kind(entity) -> str:
    return "restaurant" if type(entity).__name__ == "Restaurant" else "lead"


def _blob(entity) -> dict:
    return dict(getattr(entity, _JSON_ATTR[_kind(entity)], None) or {})


def module_for(entity) -> str:
    """Which module an entity belongs to. Restaurants → restaurant; leads →
    insurance (personal/EverQuote/commercial) else general."""
    if _kind(entity) == "restaurant":
        return "restaurant"
    seg = (entity.segment or "").lower()
    cat = (entity.category or "").lower()
    if seg == "personal" or "everquote" in cat or "insurance" in cat:
        return "insurance"
    return "insurance" if seg in ("", "commercial") and not cat else "general"


def schema_for_module(module: str = "insurance") -> dict:
    """The form schema for a module WITHOUT needing an entity — used by the 'Add'
    forms, which have no record yet."""
    module = module if module in MODULES else "general"
    mod = MODULES[module]
    return {
        "module": module,
        "module_label": mod["label"],
        "core_sections": CORE_SECTIONS if mod.get("core", True) else [],
        "module_sections": mod["sections"],
        "lists": mod["lists"],
        "modules_available": [{"key": k, "label": v["label"]} for k, v in MODULES.items()],
    }


def schema_for(entity) -> dict:
    """The full form schema for this entity: (shared core if the module uses it) +
    the module's sections + repeatable lists. Rendered generically by the UI."""
    return schema_for_module(module_for(entity))


def get_crm(entity) -> dict:
    """The stored CRM record (all sections + lists + custom fields), seeded from the
    entity's real columns so a never-edited record still shows its live data."""
    kind = _kind(entity)
    crm = dict(_blob(entity).get("crm") or {})
    if kind == "lead":
        crm.setdefault("identity", {})
        crm.setdefault("contact", {})
        crm.setdefault("sales", {})
        crm["contact"].setdefault("email", entity.email or "")
        crm["contact"].setdefault("primary_phone", entity.phone or "")
        crm["sales"].setdefault("status", entity.status or "New")
        if entity.owner_name and not (crm["identity"].get("first_name") or crm["identity"].get("last_name")):
            parts = entity.owner_name.split(None, 1)
            crm["identity"]["first_name"] = parts[0]
            crm["identity"]["last_name"] = parts[1] if len(parts) > 1 else ""
    else:  # restaurant
        rp = crm.setdefault("restaurant_profile", {})
        owner = crm.setdefault("owner_crm", {})
        rp.setdefault("name", entity.name or "")
        rp.setdefault("email", entity.email or "")
        rp.setdefault("phone", entity.phone or "")
        rp.setdefault("cuisine", entity.cuisine or "")
        rp.setdefault("city", entity.city or "")
        rp.setdefault("website", entity.website or "")
        rp.setdefault("instagram", entity.instagram or "")
        owner.setdefault("owner_name", entity.owner_manager or "")
        crm.setdefault("sales_pipeline", {}).setdefault("stage", entity.status or "New")
    return {
        "lead_id": str(entity.id),
        "module": module_for(entity),
        "profile": crm,
        "custom": _blob(entity).get("crm", {}).get("custom") or {},
        "updated_at": _blob(entity).get("crm_updated_at"),
    }


def _sync_core_columns(entity, crm: dict) -> None:
    """Push the handful of fields the rest of the app reads back onto the entity's
    real columns, so editing the CRM keeps name/email/phone/status consistent."""
    if _kind(entity) == "lead":
        ident, contact, sales = crm.get("identity") or {}, crm.get("contact") or {}, crm.get("sales") or {}
        name = " ".join(p for p in [ident.get("first_name"), ident.get("last_name")] if p).strip()
        if name:
            entity.owner_name = name
        if contact.get("email"):
            entity.email = str(contact["email"]).strip()
        if contact.get("primary_phone"):
            entity.phone = str(contact["primary_phone"]).strip()
        if sales.get("status"):
            entity.status = sales["status"]
    else:  # restaurant
        rp, owner, sp = (crm.get("restaurant_profile") or {}, crm.get("owner_crm") or {},
                         crm.get("sales_pipeline") or {})
        if rp.get("name"):
            entity.name = str(rp["name"]).strip()
        if rp.get("email"):
            entity.email = str(rp["email"]).strip()
        if rp.get("phone"):
            entity.phone = str(rp["phone"]).strip()
        if rp.get("cuisine"):
            entity.cuisine = str(rp["cuisine"]).strip()
        if rp.get("city"):
            entity.city = str(rp["city"]).strip()
        if owner.get("owner_name"):
            entity.owner_manager = str(owner["owner_name"]).strip()
        if sp.get("stage"):
            entity.status = sp["stage"]


def update_crm_entity(db: Session, entity, profile: dict, custom: dict | None = None) -> dict:
    """Merge edited sections into the entity's CRM record (deep-merge per section;
    repeatable lists replace wholesale). Reassigns the JSONB column as a new dict so
    SQLAlchemy detects the change, then syncs the handful of mirrored columns."""
    attr = _JSON_ATTR[_kind(entity)]
    blob = dict(getattr(entity, attr, None) or {})
    crm = dict(blob.get("crm") or {})
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
    blob["crm"] = crm
    blob["crm_updated_at"] = datetime.now(timezone.utc).isoformat()
    setattr(entity, attr, blob)                # reassign so the ORM flushes it
    _sync_core_columns(entity, crm)
    db.commit()
    db.refresh(entity)
    return get_crm(entity)


def update_crm(db: Session, lead_id: str, profile: dict, custom: dict | None = None) -> dict | None:
    """Update a LEAD's CRM record by id (the insurance path)."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        return None
    return update_crm_entity(db, lead, profile, custom)


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
    update_crm_entity(db, lead, profile, custom)
    return lead


def create_restaurant(db: Session, profile: dict, custom: dict | None = None):
    """Create a new SavoryMind restaurant prospect from the CRM form."""
    from .models import Restaurant
    rp = (profile or {}).get("restaurant_profile") or {}
    owner = (profile or {}).get("owner_crm") or {}
    rest = Restaurant(kind="prospect", name=(rp.get("name") or "New Restaurant"),
                      owner_manager=(owner.get("owner_name") or None),
                      email=(rp.get("email") or None), phone=(rp.get("phone") or None),
                      cuisine=(rp.get("cuisine") or None), city=(rp.get("city") or None),
                      website=(rp.get("website") or None), instagram=(rp.get("instagram") or None),
                      status="New", menu_analysis={})
    db.add(rest)
    db.flush()
    update_crm_entity(db, rest, profile, custom)
    return rest
