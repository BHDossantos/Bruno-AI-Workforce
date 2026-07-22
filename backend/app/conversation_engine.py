"""Conversation Engine — turn every call into structured, queryable data.

The philosophy (Bruno's): a CRM shouldn't store notes, it should build a sales
intelligence database. Every contact attempt answers four questions:
  1. What happened?      → outcome + conversation_status
  2. Why?                → objection / motivation / timing (carrier, renewal)
  3. What happens next?  → next_action + auto-created follow-up / renewal reminder
  4. What did we learn?  → structured rows the weekly AI loop ranks on

This module owns the option schema (so the UI form is data-driven), the
objection → AI-response map, and ``log_outcome`` which writes the structured row
AND fires the right side effects (follow-up task, renewal reminder, DNC, a call
row on the timeline). Everything is best-effort and failure-isolated so logging a
call never 500s.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from .models import ConversationOutcome, Lead

log = logging.getLogger("bruno.conversation")

# ── Option schema — the dropdowns. Kept here so the API can serve it and the UI
# renders itself; add an option in ONE place and it flows to the form. ──────────
SCHEMA: dict = {
    "method": ["call", "sms", "email", "voicemail", "linkedin", "facebook", "whatsapp"],
    "outcome": ["answered", "no_answer", "busy", "voicemail", "wrong_number",
                "disconnected", "invalid_number"],
    "conversation_status": [
        "interested", "not_interested", "already_insured", "shopping_around",
        "requested_quote", "needs_call_back", "wrong_person", "do_not_contact",
        "language_barrier", "sold", "lost"],
    "insurance_needed": ["auto", "home", "renters", "condo", "umbrella", "life",
                         "commercial", "workers_comp", "general_liability", "flood", "other"],
    "current_carrier": ["Progressive", "GEICO", "State Farm", "Liberty Mutual",
                        "Travelers", "Allstate", "Nationwide", "USAA", "Other"],
    "renewal_month": ["January", "February", "March", "April", "May", "June", "July",
                      "August", "September", "October", "November", "December"],
    "not_interested_reason": ["already_switched", "too_expensive", "happy_with_carrier",
                              "no_vehicle", "no_longer_needs", "doesnt_want_calls", "other"],
    "biggest_concern": ["price", "coverage", "service", "claims", "bundle", "agent"],
    "quote_priority": ["high", "medium", "low"],
    "objection": ["price_too_high", "coverage_too_low", "need_spouse", "need_time",
                  "need_payment_plan", "already_renewed", "already_purchased",
                  "trust_issue", "didnt_request_quote", "other"],
    "next_action": ["call", "text", "email", "renewal", "referral", "birthday", "policy_review"],
    "future_follow_up": ["never", "6_months", "12_months"],
}

# ── Objection → AI-suggested response. The producer sees the exact words to say. ──
OBJECTION_RESPONSES: dict = {
    "already_insured": ("That's great — when does your current policy renew? I'd be "
                        "happy to review it before renewal to make sure you're still "
                        "getting the best value."),
    "not_interested": ("No problem at all. Before I let you go, may I ask if you "
                       "already found coverage elsewhere?"),
    "price_too_high": ("Besides price, what's most important to you in your coverage? "
                       "Sometimes the cheapest policy costs the most at claim time."),
    "coverage_too_low": ("Let's make sure you're actually protected — what coverage "
                         "matters most to you? I can build around that."),
    "need_spouse": ("Absolutely, that's a smart call. What's the best time to catch "
                    "both of you together for five minutes?"),
    "need_time": ("Of course — no pressure. Would it help if I sent the quote over so "
                  "you have the numbers in front of you when you're ready?"),
    "need_payment_plan": ("We have flexible payment options — monthly, or paid in full "
                          "for a discount. Which would fit your budget better?"),
    "trust_issue": ("Totally fair — I'm a licensed producer and happy to send my "
                    "credentials. What would make you feel comfortable moving forward?"),
    "didnt_request_quote": ("Understood — you requested a quote through an insurance "
                            "comparison site. Since I have your info, want me to check "
                            "if I can beat what you're paying now?"),
}


def response_for(*, conversation_status: str | None = None, objection: str | None = None) -> str | None:
    """The AI-suggested next line for a given objection / status (or None)."""
    for key in (objection, conversation_status):
        if key and key in OBJECTION_RESPONSES:
            return OBJECTION_RESPONSES[key]
    return None


_RENEWAL_MONTHS = {m: i for i, m in enumerate(SCHEMA["renewal_month"], start=1)}


def _renewal_reminder_at(renewal_month: str | None) -> datetime | None:
    """~30 days before the next occurrence of the renewal month (day 1)."""
    if not renewal_month or renewal_month not in _RENEWAL_MONTHS:
        return None
    now = datetime.now(timezone.utc)
    month = _RENEWAL_MONTHS[renewal_month]
    year = now.year if month > now.month else now.year + 1
    try:
        renewal = datetime(year, month, 1, tzinfo=timezone.utc)
    except ValueError:  # pragma: no cover
        return None
    return renewal - timedelta(days=30)


def _ai_summary(lead: Lead, row: ConversationOutcome) -> str:
    """A short, deterministic recap (no AI key required). The AI loop can enrich it
    later; this guarantees every row has a readable summary."""
    name = (lead.owner_name or "The lead").split()[0] if lead and lead.owner_name else "The lead"
    bits: list[str] = []
    if row.conversation_status:
        bits.append(row.conversation_status.replace("_", " "))
    if row.current_carrier:
        bits.append(f"with {row.current_carrier}")
    if row.renewal_month:
        bits.append(f"renews {row.renewal_month}")
    if row.objection:
        bits.append(f"objection: {row.objection.replace('_', ' ')}")
    if row.insurance_needed:
        bits.append("wants " + "/".join(row.insurance_needed))
    head = f"{name}: " + ", ".join(bits) + "." if bits else f"{name}: {row.outcome or 'contacted'}."
    if row.next_action:
        head += f" Next: {row.next_action.replace('_', ' ')}"
        if row.next_follow_up_at:
            head += f" on {row.next_follow_up_at.date().isoformat()}"
        head += "."
    return head


def log_outcome(db: Session, lead_id, payload: dict, producer: str = "producer") -> ConversationOutcome:
    """Write ONE structured conversation row and fire its side effects. Best-effort:
    a failing side effect never blocks the log itself."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()

    def _b(key: str) -> bool:
        return bool(payload.get(key))

    row = ConversationOutcome(
        lead_id=lead.id if lead else None,
        attempt_number=payload.get("attempt_number"),
        method=(payload.get("method") or "call"),
        outcome=payload.get("outcome"),
        duration_seconds=payload.get("duration_seconds"),
        voicemail_left=_b("voicemail_left"),
        text_sent=_b("text_sent"),
        email_sent=_b("email_sent"),
        conversation_status=payload.get("conversation_status"),
        insurance_needed=payload.get("insurance_needed") or [],
        objection=payload.get("objection"),
        quote_started=_b("quote_started"),
        quote_completed=_b("quote_completed"),
        quote_sent=_b("quote_sent"),
        current_carrier=payload.get("current_carrier"),
        current_premium=payload.get("current_premium"),
        renewal_month=payload.get("renewal_month"),
        future_review=_b("future_review"),
        not_interested_reason=payload.get("not_interested_reason"),
        quotes_gathered=payload.get("quotes_gathered"),
        biggest_concern=payload.get("biggest_concern"),
        quote_priority=payload.get("quote_priority"),
        next_action=payload.get("next_action"),
        notes=payload.get("notes"),
        close_probability=payload.get("close_probability"),
        producer=producer,
    )

    # Next follow-up: explicit datetime, else derive from an "already insured →
    # review at renewal" or a generic follow-up.
    nf = payload.get("next_follow_up_at")
    if isinstance(nf, str) and nf:
        try:
            row.next_follow_up_at = datetime.fromisoformat(nf.replace("Z", "+00:00"))
        except ValueError:
            row.next_follow_up_at = None
    elif isinstance(nf, datetime):
        row.next_follow_up_at = nf
    if row.next_follow_up_at is None and row.future_review:
        row.next_follow_up_at = _renewal_reminder_at(row.renewal_month)

    row.ai_summary = _ai_summary(lead, row)
    db.add(row)
    db.flush()

    # ── Side effects (all failure-isolated) ──
    if lead:
        try:
            _sync_lead(db, lead, row)
        except Exception:  # pragma: no cover - never block the log
            log.exception("conversation side effects failed for lead %s", lead.id)
    db.commit()
    return row


def _sync_lead(db: Session, lead: Lead, row: ConversationOutcome) -> None:
    """Move the lead + fire cross-system effects from a logged conversation."""
    from datetime import datetime as _dt

    from .models import Message

    # 0) The customer profile builds itself — persist durable facts onto the lead.
    try:
        _sync_profile(lead, row)
    except Exception:
        log.debug("profile sync skipped", exc_info=True)

    # 1) A call row on the timeline (keeps the 📞 counter + AI timeline real).
    if row.method == "call":
        db.add(Message(channel="call", direction="outbound", entity_type="lead",
                       entity_id=lead.id, from_account="insurance",
                       body=f"📞 {row.outcome or 'call'} — {row.ai_summary}",
                       status="Sent" if row.outcome == "answered" else "Missed",
                       sent_at=_dt.now(timezone.utc)))

    # 2) Do-Not-Contact → suppress across every channel.
    if row.conversation_status == "do_not_contact":
        try:
            from . import compliance
            reason = "Requested on call (conversation log)"
            if lead.phone:
                compliance.add_dnc(db, value=lead.phone, kind="phone", reason=reason, source="call")
            if lead.email:
                compliance.add_dnc(db, value=lead.email, kind="email", reason=reason, source="call")
        except Exception:
            log.debug("dnc add skipped", exc_info=True)

    # 3) Lead status from the conversation (best-effort mapping).
    status_map = {
        "interested": "Interested", "requested_quote": "Interested",
        "sold": "Closed Won", "lost": "Closed Lost", "not_interested": "Closed Lost",
        "do_not_contact": "Closed Lost",
    }
    new_status = status_map.get(row.conversation_status or "")
    if new_status and lead.status not in ("Closed Won",):
        lead.status = new_status

    # 4) Schedule the next follow-up as a real task if we have a time.
    if row.next_follow_up_at:
        try:
            from .models import FollowUp
            na = (row.next_action or "call")
            channel = "sms" if na == "text" else (na if na in ("call", "email") else "call")
            db.add(FollowUp(entity_type="lead", entity_id=lead.id,
                            step=(row.attempt_number or 1),
                            due_date=row.next_follow_up_at.date(), channel=channel,
                            body=na.replace("_", " ")))
        except Exception:
            log.debug("followup create skipped", exc_info=True)


# ── Phase 2: the customer profile builds itself, opportunity, renewals ──────────
# Conversation facts that should persist onto the lead's profile so it compounds
# across calls (not just live in one conversation row).
_PROFILE_FIELDS = ("current_carrier", "current_premium", "renewal_month")


def _sync_profile(lead: Lead, row: ConversationOutcome) -> None:
    """Persist durable facts from a conversation onto lead.intake['profile'] so the
    Customer Profile builds itself over successive calls (last non-empty wins)."""
    intake = dict(lead.intake or {})
    profile = dict(intake.get("profile") or {})
    for f in _PROFILE_FIELDS:
        v = getattr(row, f, None)
        if v not in (None, "", []):
            profile[f] = float(v) if f == "current_premium" else v
    if row.insurance_needed:
        have = set(profile.get("insurance_needed") or [])
        profile["insurance_needed"] = sorted(have | set(row.insurance_needed))
    intake["profile"] = profile
    lead.intake = intake  # reassign so SQLAlchemy flags the JSONB dirty


def estimate_opportunity(lead: Lead, convos: list[ConversationOutcome] | None = None) -> dict:
    """Deterministic per-line cross-sell estimate (0-100) from the lead's data +
    conversation signals — Bruno's 'Auto 95% · Home 82% · Umbrella 78%' view. No AI
    key needed; the weekly learning loop (Phase 3) can calibrate these later."""
    eq = ((lead.intake or {}).get("everquote") or {}) if lead else {}
    homeowner = bool(eq.get("homeowner"))
    married = "marr" in (eq.get("marital_status") or "").lower()
    luxury = bool(eq.get("is_luxury"))
    wants = set()
    for c in (convos or []):
        wants |= set(c.insurance_needed or [])

    est = {
        "auto": 92 if (eq.get("vehicle_make") or lead and lead.category and "Auto" in (lead.category or "")) else 65,
        "home": 84 if homeowner else 28,
        "renters": 20 if homeowner else 62,
        "umbrella": 76 if (homeowner and (married or luxury)) else 34,
        "life": 58 if married else 40,
        "commercial": 78 if (eq.get("business_owner")) else 12,
    }
    # A line the customer explicitly named gets a strong bump.
    for line in wants:
        if line in est:
            est[line] = min(99, est[line] + 15)
    return {k: v for k, v in sorted(est.items(), key=lambda x: -x[1])}


def upcoming_renewals(db: Session, limit: int = 200) -> list[dict]:
    """Leads with a renewal on the horizon (already-insured + a review requested),
    sorted by the ~30-day-before reminder date — the renewal pipeline to work."""
    rows = (db.query(ConversationOutcome)
            .filter(ConversationOutcome.renewal_month.isnot(None),
                    ConversationOutcome.future_review.is_(True))
            .order_by(ConversationOutcome.created_at.desc()).limit(1000).all())
    # Keep the latest row per lead, then sort by reminder date.
    seen: dict = {}
    for r in rows:
        if r.lead_id and r.lead_id not in seen:
            seen[r.lead_id] = r
    out = []
    for r in seen.values():
        lead = db.query(Lead).filter(Lead.id == r.lead_id).first()
        remind = _renewal_reminder_at(r.renewal_month)
        out.append({
            "lead_id": str(r.lead_id),
            "name": (lead.owner_name if lead else None) or "Lead",
            "phone": lead.phone if lead else None,
            "email": lead.email if lead else None,
            "current_carrier": r.current_carrier,
            "renewal_month": r.renewal_month,
            "remind_at": remind.date().isoformat() if remind else None,
        })
    out.sort(key=lambda x: x["remind_at"] or "9999")
    return out[:limit]


def dashboard(db: Session) -> dict:
    """Segment the book by conversation status + surface today's activity — the
    'Already Insured 48 · Shopping 22 · Needs Quote 18' view."""
    from sqlalchemy import func as _f

    rows = dict(db.query(ConversationOutcome.conversation_status, _f.count())
                .filter(ConversationOutcome.conversation_status.isnot(None))
                .group_by(ConversationOutcome.conversation_status).all())
    by_status = {k: int(v) for k, v in rows.items() if k}

    start = datetime.combine(datetime.now(timezone.utc).date(),
                             datetime.min.time(), tzinfo=timezone.utc)
    today_q = db.query(ConversationOutcome).filter(ConversationOutcome.created_at >= start)
    total = db.query(_f.count(ConversationOutcome.id)).scalar() or 0
    answered = db.query(_f.count(ConversationOutcome.id)).filter(
        ConversationOutcome.outcome == "answered").scalar() or 0

    # Competitor intel: which carriers we're up against, most common first.
    carriers = dict(db.query(ConversationOutcome.current_carrier, _f.count())
                    .filter(ConversationOutcome.current_carrier.isnot(None))
                    .group_by(ConversationOutcome.current_carrier).all())

    return {
        "by_status": by_status,
        "today": int(today_q.count()),
        "total": int(total),
        "answered": int(answered),
        "contact_rate": round(100.0 * answered / total, 1) if total else 0.0,
        "top_carriers": sorted(({"carrier": k, "count": int(v)} for k, v in carriers.items()),
                               key=lambda x: -x["count"])[:8],
    }
