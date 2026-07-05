"""Starter knowledge-base content so 'Ask' is useful the moment you open it.

General MA/NH/FL personal-lines reference + EverQuote lead-handling best
practices. These are starting points to personalize — always defer to the actual
carrier's filed rules. Seeded once (only when the base is empty) so it never
duplicates or overwrites what the user adds.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from .models import KnowledgeDoc

log = logging.getLogger("bruno.knowledge.seed")

STARTER_DOCS: list[dict] = [
    {
        "title": "Auto discounts (MA / NH / FL) — the common ones",
        "tags": ["auto", "discounts"],
        "content": (
            "Discounts to check on every auto quote: multi-policy (bundle auto + home/renters), "
            "multi-car, safe/claims-free driver, continuous prior insurance (loyalty), "
            "low-mileage/usage (typically under ~10,000 miles/year), paid-in-full and "
            "auto-pay/EFT, paperless, good-student and student-away-at-school, defensive-driving "
            "course, anti-theft/safety equipment, and telematics/usage-based programs. "
            "Always verify each against the specific carrier's filed rates — availability and "
            "amounts vary by carrier and state."),
    },
    {
        "title": "Homeowner & bundling basics",
        "tags": ["home", "discounts", "bundle"],
        "content": (
            "Bundling home + auto usually produces the largest single discount and improves "
            "retention. For homeowners, quote based on replacement cost (not market value), "
            "confirm roof age and type, and check for new-home, protective-device (alarm, "
            "sprinklers), and claims-free credits. Renters can still bundle a renters policy "
            "with auto for a multi-policy discount — a common miss."),
    },
    {
        "title": "Florida homeowners — what's different",
        "tags": ["home", "FL"],
        "content": (
            "The Florida property market is its own animal: many national carriers limit new "
            "homeowners business, so FL-focused carriers (Citizens, Universal Property, Slide, "
            "Kin, Tower Hill, American Integrity) do much of the writing. Expect wind/hurricane "
            "deductibles (often a percentage of dwelling coverage), roof age and condition to be "
            "decisive, and 4-point / wind-mitigation inspections to matter for older homes."),
    },
    {
        "title": "Massachusetts auto — key notes",
        "tags": ["auto", "MA"],
        "content": (
            "MA runs a managed competition auto market with strong regional carriers (Safety, "
            "Commerce/MAPFRE, Arbella, Plymouth Rock, Vermont Mutual, The Hanover). MA uses its "
            "own SDIP (Safe Driver Insurance Plan) surcharge/credit system rather than typical "
            "national point systems, and it has specific verification requirements — confirm "
            "garaging address, all household drivers, and license status."),
    },
    {
        "title": "EverQuote lead handling — speed + cadence",
        "tags": ["everquote", "process"],
        "content": (
            "Speed is the single biggest controllable factor: aim to make first contact within "
            "60 seconds, and try multiple channels on day one (call, then text, then email, then "
            "voicemail). Most deals close on the 2nd–6th touch, not the first, so follow a "
            "structured cadence (e.g. day 1 multi-touch, then days 3, 4, 11–12, 14, 21, and a "
            "90-day nurture) rather than quitting after one or two tries. Personalize every "
            "message with the lead's actual vehicle and current carrier."),
    },
    {
        "title": "EverQuote returns — valid reasons only",
        "tags": ["everquote", "returns"],
        "content": (
            "EverQuote allows returns only for specific, legitimate reasons — typically invalid "
            "or disconnected phone, invalid/undeliverable email, duplicate leads, or leads "
            "outside your configured footprint (subject to their limits). A consumer simply "
            "saying 'I didn't request this' is NOT a valid return reason — verify the info they "
            "submitted (reference the specific vehicle) and continue the quote."),
    },
    {
        "title": "Objection: 'It's too expensive'",
        "tags": ["objections", "price"],
        "content": (
            "Don't just lower price — reframe to value. Match the exact coverage and limits so "
            "you're comparing apples-to-apples, break the premium into a monthly number, and "
            "surface the discounts they aren't getting today. If you genuinely can't beat it on "
            "the same coverage, say so — credibility wins the next renewal."),
    },
    {
        "title": "Coverage quick-reference (auto)",
        "tags": ["auto", "coverage", "faq"],
        "content": (
            "Bodily Injury (BI) and Property Damage (PD) liability cover others when you're at "
            "fault; limits are shown like 100/300/100. Collision covers your car in a crash; "
            "comprehensive covers non-collision (theft, weather, glass). Uninsured/underinsured "
            "motorist protects you against drivers with little or no coverage. Optional add-ons "
            "clients value: rental reimbursement, roadside/towing, and gap coverage on financed "
            "or leased vehicles."),
    },
]


def seed_if_empty(db: Session) -> dict:
    """Insert the starter docs only when the knowledge base has none. Idempotent."""
    existing = db.query(KnowledgeDoc).count()
    if existing:
        return {"seeded": 0, "existing": existing}
    for d in STARTER_DOCS:
        db.add(KnowledgeDoc(title=d["title"], content=d["content"],
                            tags=d["tags"], source="starter"))
    db.commit()
    log.info("Seeded %d starter knowledge docs", len(STARTER_DOCS))
    return {"seeded": len(STARTER_DOCS), "existing": 0}
