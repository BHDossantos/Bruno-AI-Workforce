"""Insurance outreach to your imported personal contacts (warm network).

These are people you know (a Google Contacts import), so the tone is a warm,
personal intro — not a cold pitch — offering a free insurance review through
Thrust. Each contact is emailed once (status → 'insurance_emailed'), routed via
outreach.dispatch_email so it respects the daily send cap + warmup + same-day
dedupe. Optional SMS is gated behind contacts_sms_enabled (automated marketing
SMS needs prior consent — TCPA), includes a STOP opt-out, and never re-texts.
"""
from __future__ import annotations

import logging

from sqlalchemy import or_
from sqlalchemy.orm import Session

from . import memory, outreach
from .ai import client
from .config import settings
from .integrations import sms
from .models import ManualContact, Message

log = logging.getLogger("bruno.contacts_outreach")

_EMAILED = "insurance_emailed"
_EXCLUDED = "do_not_contact"
_SUBJECT = "Quick question about your insurance"


def _exclude_set() -> set[str]:
    return {e.strip().lower() for e in (settings.contacts_outreach_exclude or "").split(",")
            if e.strip()}


def _fallback_body(first: str) -> str:
    return (f"Hi {first},\n\nIt's Bruno — hope you're doing well! I'm now helping people "
            "with insurance through Thrust Insurance (home, auto, life, and business "
            "coverage). I'd love to make sure you're getting the best coverage at the best "
            "rate.\n\nWould you be open to a quick, no-pressure review of your current "
            "policies? Even if you're all set, I'm glad to give you a free second opinion.\n\n"
            "Just reply here and we'll find a time.\n\nBest,\nBruno")


def _message_for(db: Session, contact: ManualContact) -> tuple[str, str]:
    first = (contact.name or "there").split()[0]
    if not client.is_live():
        return _SUBJECT, _fallback_body(first)
    mem = memory.entity_context(db, name=contact.name, email=contact.email)
    prompt = (f"Write a SHORT, warm, personal email from Bruno Dos Santos to {first}, "
              "someone in Bruno's personal network (NOT a cold lead). Bruno now offers "
              "insurance through Thrust Insurance (home, auto, life, business). Offer a "
              "free, no-pressure review / second opinion of their current coverage and ask "
              "to find a time. Friendly, brief, no hype. "
              + (f"\n{mem}\nUse anything you remember to make it genuinely personal "
                 "(reference the relationship naturally); never contradict it.\n" if mem else "")
              + 'Return JSON: {"subject": "...", "body": "..."}.')
    out = client.complete_json(prompt, system="You output only valid JSON.")
    if isinstance(out, dict) and out.get("body"):
        return out.get("subject") or _SUBJECT, out["body"]
    return _SUBJECT, _fallback_body(first)


def _has_prior_sms(db: Session, phone: str) -> bool:
    return db.query(Message).filter(Message.channel == "sms",
                                    Message.to_email == phone).first() is not None


def run(db: Session, limit: int | None = None, sms_enabled: bool | None = None) -> dict:
    """Email (and optionally text) the next batch of un-contacted personal contacts
    with a warm insurance intro. Returns a per-run summary."""
    limit = limit or settings.contacts_outreach_batch
    sms_on = settings.contacts_sms_enabled if sms_enabled is None else sms_enabled
    exclude = _exclude_set()
    contacts = (db.query(ManualContact)
                .filter(ManualContact.kind == "contact",
                        ManualContact.email.isnot(None),
                        or_(ManualContact.status.is_(None),
                            ManualContact.status.notin_([_EMAILED, _EXCLUDED])))
                .limit(limit).all())
    emailed = texted = excluded = 0
    for c in contacts:
        if (c.email or "").lower() in exclude:
            c.status = _EXCLUDED  # permanently skip (family / opt-out)
            excluded += 1
            continue
        if not outreach.is_real_email(c.email):
            continue
        subject, body = _message_for(db, c)
        msg = outreach.dispatch_email(db, entity_type="contact", entity_id=c.id,
                                      to_email=c.email, subject=subject, body=body,
                                      account="insurance", actor="contacts_insurance")
        if msg.status in ("Sent", "Drafted"):
            c.status = _EMAILED  # one outreach per contact (sent now, or a draft to send)
            emailed += 1
            try:  # remember the touch so follow-ups never repeat the intro
                memory.add(db, "Sent a warm Thrust insurance intro (free policy review).",
                           kind="event", subject=c.name or c.email, source="contacts_insurance")
            except Exception:
                log.debug("contact memory capture skipped", exc_info=True)
        # Optional warm SMS — only when explicitly enabled (consent/TCPA), Twilio is
        # configured, and we haven't texted this number before.
        if sms_on and c.phone and sms.is_configured() and not _has_prior_sms(db, c.phone):
            first = (c.name or "there").split()[0]
            text = (f"Hi {first}, it's Bruno — I now help with insurance through Thrust. "
                    "Happy to give your home/auto/life a free review. Open to it? "
                    "Reply STOP to opt out.")
            sid = sms.send_sms(c.phone, text, account="insurance")
            db.add(Message(channel="sms", direction="outbound", entity_type="contact",
                           entity_id=c.id, to_email=c.phone, body=text,
                           status="Sent" if sid else "Failed", provider_id=sid))
            if sid:
                texted += 1
    db.commit()
    return {"contacts": len(contacts), "emailed": emailed, "texted": texted,
            "excluded": excluded, "sms_enabled": sms_on}
