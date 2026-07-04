"""Lead Return Assistant — resurrect the dead-ends instead of losing them.

The lifecycle engine flags leads ``return_eligible`` once they've been contacted,
never replied, and burned their whole follow-up sequence. This turns that flag
into action: a queue of returnable leads — each with a FRESH re-engagement angle
tuned to their line — and a one-click ``mark_returned`` that re-arms a short new
follow-up cadence, flips the lead back to active, and logs it to the AI timeline.

Rule-based, no AI key needed. A lead is only in the queue until it's returned
(``lead_returned``) or it engages, so nothing is ever nagged twice.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from . import insurance_lines, lead_temperature
from .insurance_commander import _LOST, _WON
from .models import ActionLog, FollowUp, Lead, Message

log = logging.getLogger("bruno.return")

# A short, fresh cadence for a returned lead (days from today): a new touch now,
# a nudge in 3 days, a final in a week. Distinct from the original 2-week series.
_RETURN_OFFSETS = [1, 3, 7]

# Fresh re-engagement angles by line — a DIFFERENT reason to reach back out, not
# a repeat of the first pitch.
_ANGLES: dict[str, list[str]] = {
    "auto": [
        "Rates have shifted this quarter — worth a 5-minute re-shop on the same coverage?",
        "Circling back: many carriers just refiled auto rates. Want me to check if you're still competitive?",
    ],
    "home": [
        "Home rates (especially in FL) move fast — happy to re-benchmark yours with no obligation.",
        "New markets have opened up for homeowners since we last spoke — want a fresh comparison?",
    ],
    "life": [
        "Life rates are near historic lows for healthy applicants — worth locking a number while it's cheap?",
        "Quick follow-up: even a small term policy is often cheaper than people expect. Want a ballpark?",
    ],
    "commercial": [
        "New quarter, new budget cycle — good moment to re-shop your commercial coverage. Want me to run it?",
        "Circling back with a different angle: a quick coverage-gap check for your business, no obligation.",
    ],
}
_DEFAULT_ANGLE = [
    "Circling back with a fresh angle — has anything changed on your side since we last spoke?",
    "Quick check-in: happy to re-benchmark what you're paying, no obligation at all.",
]


def _flagged(db: Session, action: str) -> set[str]:
    return {eid for (eid,) in db.query(ActionLog.entity_id).filter(
        ActionLog.action == action, ActionLog.entity == "lead").all() if eid}


def _angle_for(lead: Lead) -> str:
    line = insurance_lines.line_for(lead.category, lead.segment, lead.industry)
    options = _ANGLES.get(line, _DEFAULT_ANGLE)
    # Deterministic pick (no RNG): rotate by the lead id so it's stable per lead.
    idx = sum(ord(c) for c in str(lead.id)) % len(options)
    return options[idx]


def queue(db: Session, limit: int = 100) -> list[dict]:
    """Leads flagged return-eligible that are still open and not yet returned."""
    eligible = _flagged(db, "return_eligible") - _flagged(db, "lead_returned")
    if not eligible:
        return []
    rows = (db.query(Lead).filter(Lead.id.in_(eligible)).all())
    out = []
    today = date.today()
    for lead in rows:
        status_l = (lead.status or "").strip().lower()
        replied = lead_temperature.classify(lead.status) in (
            lead_temperature.WARM, lead_temperature.HOT)
        if status_l in (_WON | _LOST) or replied:
            continue  # engaged or closed since the flag — drop from the return list
        last = db.query(func.max(Message.created_at)).filter(
            Message.entity_type == "lead", Message.entity_id == lead.id).scalar()
        days = (today - last.date()).days if last else None
        out.append({
            "lead_id": str(lead.id),
            "name": lead.company_name or lead.owner_name or lead.email or "Lead",
            "email": lead.email, "phone": lead.phone,
            "line": insurance_lines.line_for(lead.category, lead.segment, lead.industry),
            "days_since_touch": days, "angle": _angle_for(lead),
        })
        if len(out) >= limit:
            break
    out.sort(key=lambda r: (r["days_since_touch"] is None, -(r["days_since_touch"] or 0)))
    return out


def mark_returned(db: Session, lead_id: str) -> dict:
    """Re-arm a fresh follow-up cadence for the lead and flip it back to active."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        return {"ok": False, "reason": "lead not found"}

    today = date.today()
    # Close any leftover open follow-ups, then schedule the short fresh cadence.
    db.query(FollowUp).filter(FollowUp.entity_type == "lead", FollowUp.entity_id == lead.id,
                              FollowUp.completed.is_(False)).update(
        {FollowUp.completed: True}, synchronize_session=False)
    for step, off in enumerate(_RETURN_OFFSETS, start=1):
        db.add(FollowUp(entity_type="lead", entity_id=lead.id, step=step,
                        due_date=today + timedelta(days=off), completed=False))

    angle = _angle_for(lead)
    lead.status = "Contacted"  # back into the active pipeline
    db.add(ActionLog(actor="lead_return", action="lead_returned", entity="lead",
                     entity_id=str(lead.id),
                     detail={"angle": angle, "summary": f"Returned to pipeline — {angle}"}))
    db.commit()
    log.info("Lead %s returned with fresh cadence", lead_id)
    return {"ok": True, "lead_id": str(lead.id), "angle": angle,
            "follow_ups_scheduled": len(_RETURN_OFFSETS)}


def summary(db: Session) -> dict:
    """Count of leads currently awaiting a return."""
    return {"return_queue": len(queue(db, limit=10_000))}
