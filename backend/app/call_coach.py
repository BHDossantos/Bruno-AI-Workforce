"""AI Call Coach — the 60-second brief a rep reads before they dial.

Synthesises everything the workforce already knows about a lead into one
pre-call card: who they are, the line + coverage they need, their live score /
temperature / stage, a one-line history, the call's goal for that stage, exactly
what to ask for next, an opener, and the two or three objections most likely for
their profile (each with its proven rebuttal).

Rule-based (no AI key needed); when the OpenAI key IS connected it also drafts a
warmer, lead-specific opener — but the template opener is always returned.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from . import (insurance_commander, insurance_needs, lead_profile,
               lead_scoring, lead_temperature, objection_ai)
from .models import Lead, Message

log = logging.getLogger("bruno.callcoach")

# The goal of the call, by pipeline stage.
_GOALS: dict[str, str] = {
    "New": "Make first contact and collect the 3-4 details needed to quote.",
    "Attempting Contact": "Reach a live person and get the intake details to quote.",
    "Reached": "Build trust, confirm the real need, and set up the quote.",
    "Quote Sent": "Walk the quote, handle price/coverage objections, and ask for the bind.",
    "Needs Follow-up": "Re-engage, answer the open question, and move to a quote or a bind.",
    "Negotiation": "Close the remaining gap and bind the policy today.",
    "Policy Bound": "Confirm onboarding, ask for a referral, and set the renewal reminder.",
    "Lost": "Re-open with a fresh angle — ask what's changed since last time.",
}

# The objections most likely for each segment, in priority order.
_LIKELY: dict[str, list[str]] = {
    "personal": ["price", "have_insurance", "think_about_it", "renewal_hike"],
    "commercial": ["price", "loyal_agent", "bad_timing", "renewal_hike"],
    "referral_partner": ["trust", "loyal_agent", "bad_timing"],
}


def _history(db: Session, lead: Lead) -> dict:
    n_out = int(db.query(func.count()).select_from(Message).filter(
        Message.entity_type == "lead", Message.entity_id == lead.id,
        Message.direction == "outbound").scalar() or 0)
    last = db.query(func.max(Message.created_at)).filter(
        Message.entity_type == "lead", Message.entity_id == lead.id).scalar()
    replied = lead_temperature.classify(lead.status) in (
        lead_temperature.WARM, lead_temperature.HOT)
    return {"outbound_touches": n_out, "last_touch": last.isoformat() if last else None,
            "replied": replied}


def _opener(name: str, line: str, who: str) -> str:
    return (f"Hi {name}, this is your agent with Thrust Insurance — I'm reaching out about "
            f"{line} coverage for {who}. Do you have two quick minutes?")


def _likely_objections(segment: str | None) -> list[dict]:
    keys = _LIKELY.get((segment or "").lower(), ["price", "think_about_it", "have_insurance"])
    by_key = {o["key"]: o for o in objection_ai.OBJECTIONS}
    out = []
    for k in keys[:3]:
        o = by_key.get(k)
        if o:
            out.append({"objection": o["label"], "rebuttal": o["rebuttal"], "move": o["move"]})
    return out


def brief(db: Session, lead_id: str) -> dict:
    """Assemble the pre-call brief for one lead."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        return {"ok": False, "reason": "lead not found"}

    name = lead.company_name or lead.owner_name or lead.email or "there"
    who = lead.owner_name or lead.company_name or "you"
    from . import insurance_lines
    intake = lead.intake or {}
    qt = intake.get("quote_type")
    line = insurance_lines.line_for(lead.category, lead.segment, lead.industry)
    if qt:
        from . import quote_intake
        t = quote_intake.get(qt)
        if t and t.get("line"):
            line = t["line"]

    stage = insurance_commander.stage_for(lead.status, lead.times_contacted or 0)
    sc = lead_scoring.score_lead(lead)
    profile = lead_profile.profile_for(lead)
    missing = [f["label"] for f in profile["fields"]
               if not (profile["answers"].get(f["key"]) or "").strip()]
    coverages = insurance_needs.coverage_for(lead.category, lead.segment or "commercial")
    history = _history(db, lead)

    ask_next = ("Confirm the coverage and ask for the bind." if stage in ("Quote Sent", "Negotiation")
                else ("Collect: " + ", ".join(missing)) if missing
                else "Pick a quote type and start the intake." if not qt
                else "Run the quote — all intake is in.")

    opener = _opener(name, line, who)
    tailored = None
    from .ai import client
    if client.is_live():
        try:
            t = client.complete(
                f"Draft a warm, natural 1-2 sentence phone opener for an insurance agent calling "
                f"{name} about {line} coverage. Stage: {stage}. Goal: {_GOALS.get(stage,'')} "
                "No placeholders, no greeting stage-directions — just what to say.",
                system="You are a top insurance sales coach. Warm, concise, never pushy.")
            if t and not t.startswith("["):
                tailored = t
        except Exception:
            log.debug("call-coach opener AI skipped", exc_info=True)

    return {
        "ok": True,
        "lead": {"id": str(lead.id), "name": name, "phone": lead.phone, "email": lead.email,
                 "segment": lead.segment, "category": lead.category},
        "line": line, "coverages": coverages,
        "score": sc["score"], "band": sc["band"], "score_reasons": sc["reasons"],
        "temperature": lead_temperature.classify(lead.status), "stage": stage,
        "history": history,
        "goal": _GOALS.get(stage, "Move the deal one concrete step forward."),
        "ask_next": ask_next,
        "opener": opener, "opener_tailored": tailored,
        "likely_objections": _likely_objections(lead.segment),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
