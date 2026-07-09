"""Compliance & Governance Agent — the single gate every outbound action passes.

Insurance outreach is regulated: TCPA calling/texting windows, opt-out & Do-Not-
Contact suppression, per-state licensing, required producer disclosures. Those
rules used to live scattered across ``sms_engine``, ``auto_dial`` and ``config``.
This module is the ONE front door:

    d = compliance.gate(db, channel="call", phone=lead.phone, state=state,
                        entity_type="lead", entity_id=lead.id, actor="auto_dial")
    if not d.allowed:
        continue            # blocked (opt-out/DNC/hours/cap/unlicensed) or needs review

Two layers:
  • evaluate() — pure decision (read-only): runs the rule pipeline, returns a Decision.
  • gate()     — evaluate() + writes an immutable ComplianceEvent audit row.

Every decision is logged, so there is a permanent, defensible record of what the
automation was allowed to do and why. No-ops to ALLOW when enforcement is off.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from .config import settings
from .models import ComplianceEvent, DoNotContact, Message

log = logging.getLogger("bruno.compliance")

ALLOW, BLOCK, REVIEW = "allow", "block", "review"

# Channels bound by the TCPA contact-hour window + daily caps.
_LIVE_CHANNELS = {"sms", "call"}
# Channels that carry a message body needing a disclosure.
_CONTENT_CHANNELS = {"sms", "email"}


@dataclass
class Decision:
    outcome: str            # allow | block | review
    rule: str               # which rule decided (opt_out, dnc, contact_hours, …)
    reason: str             # human-readable

    @property
    def allowed(self) -> bool:
        return self.outcome == ALLOW

    @property
    def needs_review(self) -> bool:
        return self.outcome == REVIEW


# ── normalization ─────────────────────────────────────────────────────────────
def _phone_key(phone: str | None) -> str:
    return re.sub(r"\D", "", phone or "")[-10:]


def _email_key(email: str | None) -> str:
    return (email or "").strip().lower()


def _licensed_states() -> set[str]:
    return {s.strip().lower() for s in (settings.licensed_states or "").split(",") if s.strip()}


# ── Do-Not-Contact suppression list ───────────────────────────────────────────
def is_dnc(db: Session, *, phone: str | None = None, email: str | None = None) -> bool:
    keys = []
    if phone and _phone_key(phone):
        keys.append(("phone", _phone_key(phone)))
    if email and _email_key(email):
        keys.append(("email", _email_key(email)))
    for kind, value in keys:
        if db.query(DoNotContact.id).filter(
                DoNotContact.kind == kind, DoNotContact.value == value).first():
            return True
    return False


def add_dnc(db: Session, *, value: str, kind: str = "phone",
            reason: str | None = None, source: str = "manual") -> DoNotContact:
    """Suppress a phone/email. Idempotent — re-adding an existing entry is a no-op."""
    key = _phone_key(value) if kind == "phone" else _email_key(value)
    existing = db.query(DoNotContact).filter(
        DoNotContact.kind == kind, DoNotContact.value == key).first()
    if existing:
        return existing
    row = DoNotContact(kind=kind, value=key, reason=reason, source=source)
    db.add(row)
    db.commit()
    return row


def list_dnc(db: Session, limit: int = 200) -> list[DoNotContact]:
    return (db.query(DoNotContact).order_by(DoNotContact.created_at.desc())
            .limit(limit).all())


def remove_dnc(db: Session, dnc_id: str) -> bool:
    row = db.query(DoNotContact).filter(DoNotContact.id == dnc_id).first()
    if not row:
        return False
    db.delete(row)
    db.commit()
    return True


# ── individual rule helpers ───────────────────────────────────────────────────
def _calls_today(db: Session) -> int:
    start = datetime.combine(date.today(), datetime.min.time(), tzinfo=timezone.utc)
    return db.query(func.count()).select_from(Message).filter(
        Message.channel == "call", Message.direction == "outbound",
        Message.sent_at >= start).scalar() or 0


def _has_disclosure(body: str, channel: str) -> bool:
    """A light check that the message identifies the producer / gives an opt-out —
    enough to FLAG a bare message for human review, not to hard-block."""
    low = (body or "").lower()
    if channel == "sms":
        return any(k in low for k in ("stop", "opt out", "optout", "reply stop"))
    # email
    return bool(settings.producer_name and settings.producer_name.lower() in low) \
        or "unsubscribe" in low


# ── the gate ──────────────────────────────────────────────────────────────────
def evaluate(db: Session, *, channel: str, phone: str | None = None,
             email: str | None = None, state: str | None = None,
             body: str | None = None, enforce_hours: bool = True,
             already_sent: int = 0, regulated: bool = False) -> Decision:
    """Run the rule pipeline and return a Decision. Pure/read-only (no audit write).
    First decisive rule wins; ALLOW if nothing objects."""
    if not settings.compliance_enforce:
        return Decision(ALLOW, "enforce_off", "compliance enforcement disabled")

    # A regulated action (binding, coverage advice) always needs a licensed human.
    if regulated:
        return Decision(REVIEW, "regulated_action",
                        "requires a licensed producer to review before it goes out")

    # Hard suppression — DNC and opt-out are legal lines we never cross.
    if is_dnc(db, phone=phone, email=email):
        return Decision(BLOCK, "dnc", "on the Do-Not-Contact list")
    if phone:
        from . import sms_engine  # lazy: sms_engine also imports compliance
        if sms_engine.is_opted_out(db, phone):
            return Decision(BLOCK, "opt_out", "recipient opted out (texted STOP)")

    # Licensing: only sell where the producer is licensed. State is best-effort —
    # unknown state is allowed (and noted), a KNOWN out-of-scope state is blocked.
    licensed = _licensed_states()
    if state and licensed and state.strip().lower() not in licensed:
        return Decision(BLOCK, "unlicensed", f"not licensed to sell in {state}")

    # Contact-hour window + daily cap apply to live channels (calls/texts).
    if channel in _LIVE_CHANNELS:
        from . import sms_engine
        if enforce_hours and not sms_engine.in_send_window():
            noun = "calling" if channel == "call" else "texting"
            return Decision(BLOCK, "contact_hours",
                            f"outside {noun} hours "
                            f"({settings.sms_send_window_start}:00-"
                            f"{settings.sms_send_window_end}:00 {settings.sms_timezone})")
        if channel == "sms":
            if sms_engine.sms_sent_today(db) + already_sent >= settings.sms_daily_send_cap:
                return Decision(BLOCK, "daily_cap",
                                f"daily SMS cap reached ({settings.sms_daily_send_cap})")
        elif channel == "call":
            if _calls_today(db) + already_sent >= settings.call_daily_cap:
                return Decision(BLOCK, "daily_cap",
                                f"daily call cap reached ({settings.call_daily_cap})")

    # Disclosure: a content message with no producer identity / opt-out gets flagged
    # for a human rather than blocked (soft governance).
    if channel in _CONTENT_CHANNELS and body and not _has_disclosure(body, channel):
        return Decision(REVIEW, "missing_disclosure",
                        "message is missing a producer disclosure / opt-out line")

    return Decision(ALLOW, "clear", "cleared all compliance rules")


def record(db: Session, decision: Decision, *, channel: str,
           target: str | None = None, state: str | None = None,
           entity_type: str | None = None, entity_id=None,
           actor: str | None = None) -> None:
    """Append an immutable audit row for a decision. Never updates/deletes."""
    db.add(ComplianceEvent(
        channel=channel, outcome=decision.outcome, rule=decision.rule,
        reason=decision.reason, target=target, state=state,
        entity_type=entity_type, entity_id=entity_id, actor=actor))


def gate(db: Session, *, channel: str, phone: str | None = None,
         email: str | None = None, state: str | None = None,
         body: str | None = None, enforce_hours: bool = True,
         already_sent: int = 0, regulated: bool = False,
         entity_type: str | None = None, entity_id=None,
         actor: str | None = None) -> Decision:
    """evaluate() + write the audit row. The caller commits its own transaction."""
    d = evaluate(db, channel=channel, phone=phone, email=email, state=state,
                 body=body, enforce_hours=enforce_hours, already_sent=already_sent,
                 regulated=regulated)
    record(db, d, channel=channel, target=(phone or email), state=state,
           entity_type=entity_type, entity_id=entity_id, actor=actor)
    return d


# ── read helpers for the /compliance API ──────────────────────────────────────
def audit(db: Session, *, limit: int = 100, outcome: str | None = None) -> list[ComplianceEvent]:
    q = db.query(ComplianceEvent)
    if outcome:
        q = q.filter(ComplianceEvent.outcome == outcome)
    return q.order_by(ComplianceEvent.created_at.desc()).limit(limit).all()


def review_queue(db: Session, limit: int = 100) -> list[ComplianceEvent]:
    return audit(db, limit=limit, outcome=REVIEW)


def status(db: Session) -> dict:
    """Current governance posture — for the compliance dashboard."""
    counts = dict(db.query(ComplianceEvent.outcome, func.count())
                  .group_by(ComplianceEvent.outcome).all())
    return {
        "enforcing": settings.compliance_enforce,
        "licensed_states": [s.strip() for s in (settings.licensed_states or "").split(",") if s.strip()],
        "contact_window": f"{settings.sms_send_window_start}:00-"
                          f"{settings.sms_send_window_end}:00 {settings.sms_timezone}",
        "sms_daily_cap": settings.sms_daily_send_cap,
        "call_daily_cap": settings.call_daily_cap,
        "dnc_count": db.query(func.count()).select_from(DoNotContact).scalar() or 0,
        "decisions": {"allow": int(counts.get("allow", 0)),
                      "block": int(counts.get("block", 0)),
                      "review": int(counts.get("review", 0))},
    }
