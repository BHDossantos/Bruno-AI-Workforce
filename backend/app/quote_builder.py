"""Automatic Quote Builder — turn a lead into a quote packet in one call.

Rule-based (no AI key needed). From a lead's quote-intake answers plus its
business category it assembles:
  • the line of business (auto / home / life / commercial),
  • the recommended coverages for that risk (insurance_needs),
  • a shortlist of carriers that actually fit the line + state,
  • a ballpark MONTHLY-PREMIUM ESTIMATE range — clearly labeled as an estimate to
    set expectations, NOT a bound quote (we never invent a precise price),
  • what's still missing before a real quote can be run (from the intake profile),
  • a paste-ready summary.

``mark_sent`` advances the lead to the Quote Sent stage (status "Quoted") and
logs a ``quote_built`` event, so the funnel, the AI timeline and the lifecycle
engine all move together. Pure + offline; safe to call anywhere.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from . import insurance_lines, insurance_needs, lead_profile
from .models import ActionLog, Lead

log = logging.getLogger("bruno.quote")

# Ballpark MONTHLY premium ranges by line (USD). Deliberately wide — this is an
# expectation-setting estimate, never a bindable number.
_MONTHLY_RANGE: dict[str, tuple[int, int]] = {
    "auto": (90, 220),
    "home": (85, 260),
    "life": (25, 95),
    "commercial": (160, 650),
}
# Florida runs materially hotter on property + auto; nudge the estimate up.
_FL_FACTOR = {"auto": 1.35, "home": 1.6, "life": 1.0, "commercial": 1.2}

# A small, curated carrier shortlist per line (from carriers.CARRIERS), plus a
# Florida-homeowners set since the FL property market is its own animal.
_CARRIERS: dict[str, list[str]] = {
    "auto": ["Progressive", "GEICO", "Safety Insurance", "Plymouth Rock", "Travelers", "Mercury"],
    "home": ["Amica", "Openly", "Travelers", "The Hanover", "Plymouth Rock", "Vermont Mutual"],
    "life": ["Banner Life", "Haven Life", "Prudential", "MassMutual", "Corebridge (AIG Life)"],
    "commercial": ["The Hartford", "Travelers", "Liberty Mutual", "Chubb", "Nationwide", "The Hanover"],
}
_FL_HOME_CARRIERS = ["Citizens Property Insurance", "Universal Property", "Slide", "Kin",
                     "Tower Hill", "American Integrity"]

_STATES = ("MA", "NH", "FL")


def _detect_state(lead: Lead) -> str | None:
    """Best-effort state from the intake answers / lead text — MA / NH / FL only."""
    intake = lead.intake or {}
    hay = " ".join([
        *(str(v) for v in (intake.get("answers") or {}).values()),
        lead.reason or "", lead.company_name or "", lead.industry or "",
    ]).upper()
    for st in _STATES:
        if f" {st} " in f" {hay} " or f",{st}" in hay or f", {st}" in hay:
            return st
    return None


def _line_for(lead: Lead) -> str:
    """The line to quote — the chosen quote type's line wins, else classify it."""
    intake = lead.intake or {}
    qt = intake.get("quote_type")
    if qt:
        from . import quote_intake
        t = quote_intake.get(qt)
        if t and t.get("line"):
            return t["line"]
    return insurance_lines.line_for(lead.category, lead.segment, lead.industry)


def _estimate(line: str, state: str | None) -> dict:
    lo, hi = _MONTHLY_RANGE.get(line, _MONTHLY_RANGE["home"])
    if state == "FL":
        f = _FL_FACTOR.get(line, 1.0)
        lo, hi = round(lo * f), round(hi * f)
    return {
        "monthly_low": lo, "monthly_high": hi,
        "annual_low": lo * 12, "annual_high": hi * 12,
        "note": "Ballpark estimate to set expectations — a real quote is run once "
                "the intake below is complete.",
    }


def _carriers_for(line: str, state: str | None) -> list[str]:
    base = list(_CARRIERS.get(line, _CARRIERS["home"]))
    if line == "home" and state == "FL":
        base = _FL_HOME_CARRIERS + [c for c in base if c not in _FL_HOME_CARRIERS]
    return base[:6]


def build(db: Session, lead_id: str) -> dict:
    """Assemble the quote packet for one lead."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        return {"ok": False, "reason": "lead not found"}

    line = _line_for(lead)
    state = _detect_state(lead)
    coverages = insurance_needs.coverage_for(lead.category, lead.segment or "commercial")
    profile = lead_profile.profile_for(lead)
    missing = [f["label"] for f in profile["fields"]
               if not (profile["answers"].get(f["key"]) or "").strip()]
    ready = bool(profile["quote_type"]) and profile["complete"]
    est = _estimate(line, state)

    name = lead.company_name or lead.owner_name or lead.email or "this lead"
    carriers = _carriers_for(line, state)
    summary = (
        f"{name} — {line.title()} quote"
        + (f" ({state})" if state else "") + "\n"
        f"Coverages: {coverages}\n"
        f"Carriers to shop: {', '.join(carriers)}\n"
        f"Estimated premium: ${est['monthly_low']}–${est['monthly_high']}/mo "
        f"(${est['annual_low']:,}–${est['annual_high']:,}/yr) — {est['note']}\n"
        + ("Ready to quote — all intake collected." if ready
           else f"Still needed to quote: {', '.join(missing) if missing else 'pick a quote type first'}.")
    )

    return {
        "ok": True,
        "lead": {"id": str(lead.id), "name": name, "status": lead.status,
                 "segment": lead.segment, "category": lead.category},
        "line": line, "state": state, "coverages": coverages,
        "carriers": carriers, "estimate": est,
        "quote_type": profile["quote_type"], "quote_type_label": profile["quote_type_label"],
        "intake": {"collected": profile["collected"], "total": profile["total"],
                   "complete": profile["complete"], "missing": missing},
        "ready_to_send": ready, "summary": summary,
    }


def mark_sent(db: Session, lead_id: str) -> dict:
    """Advance the lead to the Quote Sent stage and log it to the AI timeline."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        return {"ok": False, "reason": "lead not found"}
    packet = build(db, lead_id)
    lead.status = "Quoted"
    lead.last_contacted_at = datetime.now(timezone.utc)
    db.add(ActionLog(
        actor="quote_builder", action="quote_built", entity="lead", entity_id=str(lead.id),
        detail={"line": packet.get("line"),
                "summary": f"Quote sent — {packet.get('line', 'insurance')} "
                           f"(${packet['estimate']['monthly_low']}–"
                           f"${packet['estimate']['monthly_high']}/mo est.)"}))
    db.commit()
    log.info("Quote marked sent for lead %s (%s)", lead_id, packet.get("line"))
    packet["lead"]["status"] = "Quoted"
    packet["marked_sent"] = True
    return packet
