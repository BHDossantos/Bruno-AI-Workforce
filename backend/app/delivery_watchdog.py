"""Delivery Watchdog — the daily audit that proves the three core channels work.

Bruno's rule: automatic emails, texts, and calls must actually go out every day,
EverQuote leads first, and NEVER blank. This is the one place that answers, once a
day: did we send what we should have, were EverQuote leads worked first, and are
any drafts silently stuck (blank / held for review)? It raises loud, specific
issues so the system can't quietly stop working.

Read-only + failure-isolated: composed from the existing per-channel views so it
can run on a schedule or be hit on demand without side effects.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from .config import settings
from .models import Lead, Message

log = logging.getLogger("bruno.delivery_watchdog")


def _day_start() -> datetime:
    return datetime.combine(date.today(), datetime.min.time(), tzinfo=timezone.utc)


def _sent_today(db: Session, channel: str) -> int:
    return int(db.query(func.count()).select_from(Message).filter(
        Message.channel == channel, Message.direction == "outbound",
        Message.sent_at >= _day_start()).scalar() or 0)


def _days_since_last(db: Session, channel: str) -> int | None:
    """Days since the last outbound message on a channel (None if never). Surfaces a
    silently stalled channel — e.g. 'no call has actually gone out in 10 days' —
    which is exactly how a broken carrier/provider hides."""
    last = db.query(func.max(Message.sent_at)).filter(
        Message.channel == channel, Message.direction == "outbound",
        Message.sent_at.isnot(None)).scalar()
    if not last:
        return None
    return (datetime.now(timezone.utc) - last).days


def _everquote_backlog(db: Session) -> int:
    """EverQuote leads that still haven't been worked (New/Drafted) — these must
    always be sent FIRST, so any backlog here while other leads get sent is a
    priority problem worth flagging."""
    return int(db.query(func.count()).select_from(Lead).filter(
        func.lower(func.coalesce(Lead.category, "")).like("everquote%"),
        Lead.status.in_(["New", "Drafted"]),
        Lead.email.isnot(None)).scalar() or 0)


def _blanks_held(db: Session) -> int:
    """Drafts pulled from the queue because their body was empty — they never send
    until they get real copy. Should be zero now that drafts have template fallbacks."""
    return int(db.query(func.count()).select_from(Message).filter(
        Message.status == "Needs Review", Message.channel == "email").scalar() or 0)


def audit(db: Session) -> dict:
    """One report answering: did email / text / call all send today, EverQuote-first,
    zero blanks? Returns per-channel numbers, a list of concrete issues, and a healthy
    flag. Best-effort — a failure in one probe never breaks the audit."""
    from . import control

    issues: list[str] = []
    paused = False
    autopilot = False
    try:
        paused = control.is_paused_safe(db)
        autopilot = control.get_mode(db) == "auto" or control.outreach_autopilot(db)
    except Exception:
        pass

    # EMAIL
    email = {"sent": 0, "cap": 0, "backlog": 0}
    try:
        from . import deliverability
        snap = deliverability.snapshot(db)
        email = {"sent": snap.get("sent_today", 0), "cap": snap.get("daily_cap", 0),
                 "backlog": snap.get("backlog", 0), "can_send": snap.get("can_send", False)}
        if not snap.get("can_send"):
            issues.append("EMAIL: no sender connected — nothing can send. Connect Resend/Gmail in Setup.")
        elif email["backlog"] and email["sent"] == 0:
            issues.append(f"EMAIL: {email['backlog']} queued but 0 sent today — the sender may be stuck.")
    except Exception as exc:
        issues.append(f"EMAIL: audit failed — {str(exc)[:120]}")

    # SMS
    sms = {"sent": _sent_today(db, "sms"), "cap": int(settings.sms_daily_send_cap or 0)}
    try:
        from . import sms_engine
        sms["sent"] = int(sms_engine.sms_sent_today(db))
    except Exception:
        pass

    # CALLS
    calls = {"placed": _sent_today(db, "call"), "cap": int(settings.auto_dial_daily_cap or 0)}

    # Stalled-channel detection — a channel that hasn't ACTUALLY sent anything in days
    # is the clearest sign a provider quietly broke (e.g. no real call reached the
    # carrier since a given date). Flag any channel silent for 3+ days.
    stale_days = {c: _days_since_last(db, c) for c in ("email", "sms", "call")}
    for chan, label in (("email", "EMAIL"), ("sms", "TEXT"), ("call", "CALL")):
        d = stale_days[chan]
        if d is None:
            issues.append(f"{label}: no {chan} has EVER actually sent — this channel isn't working.")
        elif d >= 3:
            issues.append(f"{label}: last {chan} actually sent {d} days ago — the channel looks "
                          "STALLED (provider/config broke or autopilot is off). Check the carrier.")

    # Blanks + EverQuote priority
    blanks = _blanks_held(db)
    eq_backlog = _everquote_backlog(db)
    if blanks:
        issues.append(f"BLANKS: {blanks} email draft(s) held for review with an empty body — "
                      "they need real copy or they never send.")
    if eq_backlog and (email["sent"] or sms["sent"] or calls["placed"]):
        issues.append(f"PRIORITY: {eq_backlog} EverQuote lead(s) still unworked while other outreach "
                      "went out — EverQuote must be worked first.")
    if paused:
        issues.append("PAUSED: Emergency Stop is on — no automatic outreach is going out.")
    elif not autopilot:
        issues.append("AUTOPILOT OFF: automatic sending is off — turn on Outreach Autopilot so the "
                      "day's emails/texts/calls go out on their own.")

    healthy = not issues
    return {
        "date": date.today().isoformat(),
        "healthy": healthy,
        "paused": paused, "autopilot_on": autopilot,
        "email": email, "sms": sms, "calls": calls,
        "days_since_last": stale_days,
        "blanks_held": blanks, "everquote_backlog": eq_backlog,
        "issues": issues,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def run(db: Session) -> dict:
    """Scheduler entrypoint — run the audit and log loudly if anything's wrong so a
    silent delivery failure surfaces instead of costing a day of leads."""
    report = audit(db)
    if report["issues"]:
        log.warning("DELIVERY WATCHDOG — %d issue(s): %s",
                    len(report["issues"]), " | ".join(report["issues"]))
    else:
        log.info("DELIVERY WATCHDOG — all channels healthy: email=%s sms=%s calls=%s",
                 report["email"]["sent"], report["sms"]["sent"], report["calls"]["placed"])
    return report
