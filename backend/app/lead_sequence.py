"""Multi-touch insurance cadence — the sequence engine.

Every lead that gets a first touch is enrolled into a structured, multi-CHANNEL
cadence (email → call task → SMS → check-in → nurture) instead of a single email.
Each touch has a distinct job so the sequence adds value instead of nagging, and
the channels are spaced the way top producers actually work a lead.

The cadence is stored as ``FollowUp`` rows (one per step, each carrying its
``channel`` and, in ``body``, the purpose the touch should accomplish). The shared
follow-up engine (followups.process_due_followups) executes whatever is due —
email via the outreach dispatcher, SMS as a compliance-gated draft, and calls as a
Task in the call queue — hot leads first. Enrollment is idempotent and only starts
AFTER the first touch, so it never double-sends the opener.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from .models import FollowUp, Lead, Message

log = logging.getLogger("bruno.sequence")

# (day offset from enrollment, channel, purpose). Day 0 is the first touch, already
# sent when the lead is enrolled — the cadence is the FOLLOW-UP arc after it.
INSURANCE_CADENCE: list[tuple[int, str, str]] = [
    (2, "email", "Value follow-up: share one concrete insight or quick win about their "
                 "coverage (a common gap or a likely discount) — give value, ask for nothing big."),
    (3, "call",  "Call task: call to book a 10-minute policy review. Lead with the specific "
                 "line they need and one reason it matters right now."),
    (5, "email", "Social proof: a brief, specific result for someone like them (a real "
                 "saving or a gap caught) — no fluff, one concrete outcome."),
    (7, "sms",   "Short, friendly text: it takes 2 minutes to verify a couple details and "
                 "get an accurate quote — ask for the best time to talk."),
    (10, "call", "Call task: second attempt from a DIFFERENT angle than the first call — "
                 "maybe the prior reason wasn't their priority; try another concrete need."),
    (14, "email", "Human check-in on timing: is this even a priority right now? Make it easy "
                  "to say 'not now' and offer to circle back."),
    (30, "email", "Nurture / breakup: you'll close their file for now, keep the door open — "
                  "'reply anytime and I'll pick it right back up.' Warm, zero pressure."),
]

# Statuses that mean the lead is done with prospecting outreach — never enroll or
# keep sequencing these (won/lost/dead/opted-out advance past the cadence).
_STOP_STATUSES = {"won", "bound", "lost", "dead", "unsubscribed", "do_not_contact", "closed"}


def _already_enrolled(db: Session, lead_id) -> bool:
    return db.query(FollowUp.id).filter(
        FollowUp.entity_type == "lead", FollowUp.entity_id == lead_id).first() is not None


def enroll(db: Session, lead: Lead, start: date | None = None) -> int:
    """Enroll one lead into the multi-touch cadence. Idempotent — a lead that
    already has follow-ups is left alone. Returns the number of steps created."""
    if _already_enrolled(db, lead.id):
        return 0
    start = start or date.today()
    created = 0
    for i, (day, channel, purpose) in enumerate(INSURANCE_CADENCE, start=1):
        db.add(FollowUp(entity_type="lead", entity_id=lead.id, step=i,
                        due_date=start + timedelta(days=day), channel=channel,
                        body=purpose, completed=False))
        created += 1
    return created


def enroll_active_leads(db: Session, limit: int = 200) -> dict:
    """Enroll every contacted, still-open lead that isn't already in a cadence —
    HOT LEADS FIRST — so a fresh EverQuote lead automatically gets the full arc
    (email → call → SMS → check-in → nurture) after its opener, with no manual
    setup. Returns how many leads were enrolled + steps scheduled."""
    # Candidates: open leads (not won/lost/dead), NOT yet enrolled, whose opener has
    # already gone out. Both conditions are in the query so the limit counts only
    # eligible leads (a pile of un-contacted leads can't crowd out a real one). Hot
    # first so the best leads get the cadence soonest.
    contacted = db.query(Message.id).filter(
        Message.entity_type == "lead", Message.entity_id == Lead.id,
        Message.direction == "outbound", Message.status.in_(["Sent", "Queued"])).exists()
    enrolled_already = db.query(FollowUp.id).filter(
        FollowUp.entity_type == "lead", FollowUp.entity_id == Lead.id).exists()
    q = (db.query(Lead)
         .filter(func.lower(Lead.status).notin_(_STOP_STATUSES))
         .filter(~enrolled_already)
         .filter(contacted)
         .order_by(func.coalesce(Lead.score, 0).desc(), Lead.created_at.asc())
         .limit(max(1, limit)))
    enrolled = steps = 0
    for lead in q.all():
        n = enroll(db, lead)
        if n:
            enrolled += 1
            steps += n
    db.commit()
    result = {"enrolled": enrolled, "steps": steps}
    if enrolled:
        log.info("Sequence enrollment: %s", result)
    return result


def steps_for(db: Session, lead_id) -> list[dict]:
    """This lead's cadence steps (for the profile view): channel, due date, done."""
    rows = (db.query(FollowUp)
            .filter(FollowUp.entity_type == "lead", FollowUp.entity_id == lead_id)
            .order_by(FollowUp.due_date, FollowUp.step).all())
    return [{"step": r.step, "channel": r.channel or "email",
             "due_date": r.due_date.isoformat() if r.due_date else None,
             "completed": bool(r.completed)} for r in rows]
