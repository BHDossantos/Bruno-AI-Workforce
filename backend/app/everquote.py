"""EverQuote lead import + per-lead AI personalization.

Reads an EverQuote CSV export (or parsed rows), pulls every useful field — name,
vehicle, current carrier, coverage level, credit, marital status, residence,
insurance expiration — including the rich JSON in the ``detail`` column, and
creates personal-auto leads with a pre-filled quote intake. Then, per lead, it
generates a PERSONALIZED email, SMS, voicemail script and pre-call notes that
reference the lead's actual vehicle and carrier — so 500 leads take the same
effort as 5.

Rule-based templates (work fully offline, no AI key); when the OpenAI key is
connected the email/SMS are additionally rewritten for warmth, but the accurate
template always stands. Nothing is sent here — outreach is generated for review.
"""
from __future__ import annotations

import csv
import io
import json
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from .config import settings
from .models import Lead

log = logging.getLogger("bruno.everquote")

# Carrier strings EverQuote uses that don't name a real prior carrier.
_NO_CARRIER = {"", "company not listed", "not insured", "none", "no prior insurance"}


def _title(s: str | None) -> str:
    return " ".join(w.capitalize() for w in (s or "").split())


def _extract(row: dict) -> dict:
    """Flatten one EverQuote CSV row (+ its JSON detail) into the fields we use."""
    detail = {}
    raw = row.get("detail")
    if raw:
        try:
            detail = json.loads(raw)
        except (ValueError, TypeError):
            detail = {}

    person = detail.get("person") or {}
    auto = detail.get("autoPolicy") or {}
    car = auto.get("primaryCar") or {}
    exp = auto.get("insuranceExpiration") or {}

    carrier = (auto.get("currentInsurer") or row.get("current_insurer") or "").strip()
    listed_carrier = carrier if carrier.lower() not in _NO_CARRIER else ""
    residence = (auto.get("residence") or "").strip().lower()
    homeowner = residence in ("own", "home", "mortgage", "owned")

    return {
        "eq_uuid": (row.get("eqLeadUUID") or "").strip(),
        "first_name": _title(row.get("first_name") or person.get("firstName")),
        "last_name": _title(row.get("last_name") or person.get("lastName")),
        "email": (row.get("email") or person.get("email") or "").strip().lower() or None,
        "phone": (row.get("phone") or person.get("phone") or "").strip() or None,
        "city": _title(row.get("city") or (person.get("address") or {}).get("city")),
        "state": (row.get("state") or (person.get("address") or {}).get("state") or "").strip().upper(),
        "zip": (row.get("zip_code") or (person.get("address") or {}).get("zip") or "").strip(),
        "product": (row.get("product") or "").strip(),
        "cost": (row.get("cost") or "").strip(),
        "vertical": (detail.get("vertical") or "auto").strip().lower(),
        "vehicle_year": car.get("year"),
        "vehicle_make": _title(car.get("make")),
        "vehicle_model": (car.get("model") or "").strip().upper(),
        "vehicle_submodel": (car.get("submodel") or "").strip(),
        "ownership": (car.get("ownership") or "").strip(),          # Financed | Leased | Owned
        "coverage_type": (car.get("coverageType") or "").strip(),   # Lower | Typical | Higher
        "miles_per_year": car.get("milesPerYear"),
        "is_luxury": bool(car.get("isLuxury")),
        "current_carrier": listed_carrier,
        "credit_rating": (auto.get("creditRating") or "").strip(),
        "months_insured": auto.get("monthsInsured"),
        "bi_liability": (auto.get("currentBiLiability") or "").strip(),
        "marital_status": (person.get("maritalStatus") or "").strip(),
        "gender": (person.get("gender") or "").strip(),
        "homeowner": homeowner,
        "residence": (auto.get("residence") or "").strip(),
        "expiration": (f"{exp.get('month')}/{exp.get('year')}" if exp.get("year") else ""),
    }


def parse_csv(text: str) -> list[dict]:
    """Parse an EverQuote CSV export into normalized field dicts."""
    reader = csv.DictReader(io.StringIO(text))
    return [_extract(r) for r in reader]


def _vehicle(f: dict) -> str:
    parts = [str(f["vehicle_year"]) if f["vehicle_year"] else "", f["vehicle_make"],
             f["vehicle_model"].title()]
    return " ".join(p for p in parts if p).strip() or "vehicle"


def _lead_name(f: dict) -> str:
    return (f"{f['first_name']} {f['last_name']}").strip() or (f["email"] or "EverQuote lead")


def import_rows(db: Session, rows: list[dict]) -> dict:
    """Create/refresh personal-auto leads from EverQuote rows. Dedupes by email."""
    imported = updated = skipped = 0
    lead_ids: list[str] = []
    for f in rows:
        if not (f.get("email") or f.get("phone")):
            skipped += 1
            continue
        vehicle = _vehicle(f)
        reason = f"EverQuote {f['vertical']} lead — {vehicle}" + (
            f", currently with {f['current_carrier']}" if f["current_carrier"] else "")
        # Pre-fill the quote intake so the Quote Builder & Call Coach light up at once.
        garaging = ", ".join(p for p in [f["city"], f["state"], f["zip"]] if p)
        intake = {
            "source": "everquote", "everquote": f,
            "quote_type": "personal_auto",
            "answers": {k: v for k, v in {"garaging_address": garaging}.items() if v},
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        existing = (db.query(Lead).filter(Lead.email == f["email"]).first()
                    if f.get("email") else None)
        if existing:
            existing.intake = intake
            existing.reason = reason
            if f["phone"] and not existing.phone:
                existing.phone = f["phone"]
            lead_ids.append(str(existing.id))
            updated += 1
            continue
        lead = Lead(segment="personal", category="EverQuote Auto", owner_name=_lead_name(f),
                    email=f["email"], phone=f["phone"], status="New", times_contacted=0,
                    reason=reason, intake=intake, score=0)
        db.add(lead); db.flush()
        lead_ids.append(str(lead.id))
        imported += 1
    db.commit()
    result = {"imported": imported, "updated": updated, "skipped": skipped,
              "total": len(rows), "lead_ids": lead_ids}
    log.info("EverQuote import: %s", result)
    return result


def _discount_angles(f: dict) -> list[str]:
    angles = []
    if f.get("homeowner"):
        angles.append("bundle home + auto")
    if (f.get("marital_status") or "").lower() == "married":
        angles.append("married / multi-driver discount")
    miles = f.get("miles_per_year")
    if isinstance(miles, (int, float)) and miles and miles < 10000:
        angles.append("low-mileage discount")
    mi = f.get("months_insured")
    if isinstance(mi, (int, float)) and mi and mi >= 6:
        angles.append("prior-insurance / continuous-coverage credit")
    if (f.get("credit_rating") or "").lower() in ("good", "excellent"):
        angles.append("preferred credit tier")
    return angles or ["available discounts you may not be getting today"]


def _signature() -> str:
    lic = f"\nLicensed Insurance Producer #{settings.producer_license}" if settings.producer_license else ""
    return f"{settings.producer_name}{lic}"


def personalize(lead: Lead) -> dict:
    """Generate personalized email + SMS + voicemail + call notes for one lead."""
    intake = lead.intake or {}
    f = intake.get("everquote") or {}
    if not f:
        return {"ok": False, "reason": "not an EverQuote lead (no EverQuote fields on file)"}

    first = f.get("first_name") or "there"
    vehicle = _vehicle(f)
    carrier = f.get("current_carrier")
    angles = _discount_angles(f)
    producer = settings.producer_name

    # Subject + email body, phrased around whether we know their current carrier.
    if carrier:
        subject = f"{first}, I reviewed your {vehicle} quote"
        opener = (f"I finished reviewing the quote request you submitted for your {vehicle}. "
                  f"I noticed you're currently insured with {carrier}, and I'd like to see if we can "
                  "improve your coverage, lower your premium, or both.")
    else:
        subject = f"{first}, I found additional discounts for your {vehicle}"
        opener = (f"I just finished reviewing the information you submitted for your {vehicle}. "
                  "Based on what I see, there may be additional discounts available beyond what was "
                  "initially calculated.")
    email_body = (
        f"Hi {first},\n\n{opener}\n\n"
        "I just need a couple of minutes to verify a few details so you get the most accurate price "
        "and the coverage that best fits your needs.\n\n"
        "You can reply to this email, call me directly, or text me the best time to reach you.\n\n"
        f"Looking forward to helping you.\n\n{_signature()}")

    sms = (f"Hi {first}, it's {producer} with Thrust Insurance. I finished reviewing your {vehicle} "
           "quote and found a few discounts to verify. Reply or call when you have 2 minutes — thanks!")

    callback = f" at {settings.producer_callback}" if settings.producer_callback else ""
    voicemail = (f"Hi {first}, this is {producer} with Thrust Insurance. I just reviewed the quote you "
                 f"requested for your {vehicle} and I think I can help you save or get better coverage. "
                 f"Give me a quick call back{callback} whenever you have a moment. Again, this is "
                 f"{producer}. Talk soon.")

    notes = [f"Vehicle: {vehicle}" + (f" ({f['vehicle_submodel']})" if f.get("vehicle_submodel") else ""),
             f"Current carrier: {carrier or 'none listed'}"
             + (f" · expires {f['expiration']}" if f.get("expiration") else ""),
             f"Coverage level: {f.get('coverage_type') or 'unknown'}"
             + (f" · BI limits {f['bi_liability']}" if f.get("bi_liability") else ""),
             f"Profile: {f.get('marital_status') or '—'}, "
             + ("homeowner" if f.get("homeowner") else "renter")
             + (f", credit {f['credit_rating']}" if f.get("credit_rating") else ""),
             f"Discount angles: {', '.join(angles)}",
             "Goal: verify the details, present the quote, ask for the bind."]

    # Optional AI polish (email + sms) — accurate template always returned as fallback.
    tailored_email = tailored_sms = None
    try:
        from .ai import client
        if client.is_live():
            te = client.complete(
                f"Rewrite this insurance follow-up email warmer and more natural, same facts, "
                f"no placeholders, keep the signature:\n\n{email_body}",
                system="You are a warm, compliant licensed insurance producer. Never invent a price.")
            if te and not te.startswith("["):
                tailored_email = te
            ts = client.complete(
                f"Rewrite this SMS friendlier in under 160 chars, same facts, no placeholders:\n\n{sms}",
                system="You are a warm, compliant licensed insurance producer.")
            if ts and not ts.startswith("["):
                tailored_sms = ts
    except Exception:
        log.debug("EverQuote personalization AI polish skipped", exc_info=True)

    return {
        "ok": True,
        "lead_id": str(lead.id), "name": _lead_name(f), "vehicle": vehicle,
        "email": {"subject": subject, "body": email_body, "tailored": tailored_email},
        "sms": {"body": sms, "tailored": tailored_sms},
        "voicemail": voicemail,
        "call_notes": notes,
        "fields": {k: f.get(k) for k in (
            "vehicle_year", "vehicle_make", "vehicle_model", "current_carrier",
            "coverage_type", "credit_rating", "marital_status", "homeowner",
            "state", "expiration")},
    }
