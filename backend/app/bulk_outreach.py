"""Bulk / automatic outreach dispatch.

Sends the cold email/pitch to every pending lead and restaurant prospect. Used by
the manual "Send all pending" buttons AND the daily auto-outreach cron, so leads
never sit in Drafted. Every send goes through outreach.dispatch_email, which
enforces the daily send cap + mailbox warmup + real-email guard — so even
"send everything" is safely paced and won't get the Gmail account flagged.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from . import outreach
from .models import Lead, Message, Restaurant

_PENDING = (None, "New", "Drafted")


def dispatch_leads(db: Session, segment: str | None = None, limit: int = 1000,
                   autonomous: bool = True) -> dict:
    from . import importer
    from .integrations import gmail
    q = db.query(Lead).filter(Lead.status.in_(_PENDING), Lead.email.isnot(None))
    if segment:
        q = q.filter(Lead.segment == segment)
    rows = q.order_by(Lead.score.desc()).limit(limit).all()
    sent = failed = retired = drafted = 0
    # Pace to each mailbox's remaining daily headroom (the ramp cap). We consume one
    # unit of budget per lead we WORK — so a fresh 2,000-lead import doesn't trigger
    # 2,000 AI drafts in one tick; it's spread across sending windows just like sends.
    _room: dict[str, int] = {}

    def room(acct: str) -> int:
        if acct not in _room:
            _room[acct] = max(0, outreach.effective_cap(db, acct) - outreach.sent_today_count(db, acct))
        return _room[acct]

    for lead in rows:
        # Retire un-sendable (synthetic/placeholder) addresses so they stop sitting
        # in the queue forever and inflating the backlog.
        if not outreach.is_real_email(lead.email):
            lead.status = "Skipped"
            retired += 1
            continue
        needs_draft = not (lead.cold_email or "").strip()
        if needs_draft:
            # A lead with no written body is either (a) a fresh CSV-import lead that
            # still needs its AI email, or (b) an EverQuote/quote-intake lead whose
            # personalized copy already lives in its own Drafted Message (sent by
            # send_email_drafts). Only draft (a); never blank-send or double-send (b).
            has_message = db.query(Message.id).filter(
                Message.entity_type == "lead", Message.entity_id == lead.id,
                Message.channel == "email").first()
            if has_message:
                continue
        account = gmail.account_for_segment(lead.segment)
        if room(account) <= 0:
            continue  # mailbox hit its daily cap — leave pending for the next window
        _room[account] -= 1
        # Write the AI cold email now if the lead doesn't have one yet (CSV import
        # inserts leads without it so the upload stays instant).
        subject = None
        if needs_draft:
            try:
                subject = importer.draft_lead_email(db, lead)
            except Exception:
                failed += 1
                continue
        subject = subject or f"A quick idea for {lead.company_name or lead.owner_name}"
        try:
            msg = outreach.dispatch_email(db, entity_type="lead", entity_id=lead.id,
                                          to_email=lead.email, subject=subject,
                                          body=lead.cold_email, account=account, actor="bulk",
                                          autonomous=autonomous)
            if msg.status == "Sent":
                if lead.status in (None, "New", "Drafted"):
                    lead.status = "Sent"
                sent += 1
            elif msg.status == "Drafted":
                drafted += 1
            else:
                failed += 1
        except Exception:
            failed += 1
    db.commit()
    return {"pending": len(rows), "dispatched": sent, "drafted": drafted,
            "failed": failed, "retired": retired}


def dispatch_restaurants(db: Session, limit: int = 1000, autonomous: bool = True) -> dict:
    rows = (db.query(Restaurant).filter(
        Restaurant.kind == "prospect", Restaurant.status.in_(_PENDING),
        Restaurant.email.isnot(None)).limit(limit).all())
    sent = failed = retired = 0
    for r in rows:
        if not outreach.is_real_email(r.email):
            r.status = "Skipped"  # retire un-sendable synthetic/placeholder rows
            retired += 1
            continue
        subject = f"Growing revenue at {r.name} with SavoryMind"
        try:
            from .integrations import gmail
            msg = outreach.dispatch_email(db, entity_type="restaurant", entity_id=r.id,
                                          to_email=r.email, subject=subject,
                                          body=r.pitch_email, account=gmail.restaurant_account(), actor="bulk",
                                          autonomous=autonomous)
            if msg.status in ("Sent", "Drafted"):
                if msg.status == "Sent" and r.status in (None, "New", "Drafted"):
                    r.status = "Sent"
                sent += 1
            else:
                failed += 1
        except Exception:
            failed += 1
    db.commit()
    return {"pending": len(rows), "dispatched": sent, "failed": failed, "retired": retired}
