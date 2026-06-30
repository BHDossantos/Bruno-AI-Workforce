"""Deliverability & sending dashboard.

The one screen that answers "are my emails actually going out, how many today,
and what's stuck?" — plus a single button to drain the whole outbox now.

It reports the ACTIVE sending channel (Instantly/Smartlead campaign engine,
SendGrid direct delivery, or Gmail), today's sends vs the daily cap, the queued
backlog, a per-mailbox breakdown, and recent failures from the action log. The
cap logic mirrors outreach.dispatch_email exactly: SendGrid has one GLOBAL daily
limit; Gmail mailboxes are capped per-account with warmup.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from . import outreach
from .config import settings
from .integrations import gmail, sender, sendgrid
from .models import ActionLog, Lead, Message, Restaurant

_ACCOUNTS = [
    (gmail.PERSONAL, "Personal"),
    (gmail.INSURANCE, "Thrust Insurance"),
    (gmail.BNB, "BnB Global"),
    (gmail.SAVORYMIND, "SavoryMind"),
]
_PENDING = (None, "New", "Drafted")
# Action-log entries that mean a send DIDN'T happen for a real reason.
_FAIL_ACTIONS = ("provider_handoff_failed", "send_skipped_duplicate",
                 "send_skipped_synthetic", "send_skipped_paused")


def _day_start() -> datetime:
    return datetime.combine(date.today(), datetime.min.time(), tzinfo=timezone.utc)


def _active_channel() -> dict:
    """Which channel actually delivers right now, and a human label for it."""
    pname = sender.name()
    if pname:
        return {"channel": pname, "label": pname.title() + " (campaign engine)",
                "kind": "provider", "paced_externally": True}
    if sendgrid.is_configured():
        return {"channel": "sendgrid", "label": "SendGrid (direct delivery)",
                "kind": "sendgrid", "paced_externally": False}
    for acct, _ in _ACCOUNTS:
        if gmail.is_configured(acct):
            return {"channel": "gmail", "label": "Gmail mailbox", "kind": "gmail",
                    "paced_externally": False}
    return {"channel": None, "label": "No sender connected", "kind": "none",
            "paced_externally": False}


def snapshot(db: Session) -> dict:
    """Everything the deliverability dashboard needs in one payload."""
    from . import control

    start = _day_start()
    week_start = start - timedelta(days=6)
    chan = _active_channel()

    sent_today = outreach.sent_today_count(db)
    sent_week = int(db.query(func.count()).select_from(Message).filter(
        Message.direction == "outbound", Message.sent_at >= week_start).scalar() or 0)

    # Cap mirrors dispatch_email: SendGrid is one global daily limit; otherwise the
    # cap is per-mailbox so we sum each connected account's effective (warmup) cap.
    if sendgrid.is_configured():
        cap = settings.sendgrid_daily_cap
    else:
        cap = sum(outreach.effective_cap(db, a) for a, _ in _ACCOUNTS if gmail.is_configured(a))
    cap = int(cap or 0)
    remaining = max(0, cap - sent_today) if cap else None

    # Per-mailbox breakdown — what each business sent today.
    accounts = []
    for acct, label in _ACCOUNTS:
        connected = gmail.is_configured(acct)
        accounts.append({
            "account": acct, "label": label, "connected": connected,
            "sent_today": outreach.sent_today_count(db, acct),
            "sendgrid_sender": sendgrid.from_for(acct) if sendgrid.has_key() else None,
        })

    # Backlog: real-emailable prospects still waiting to be sent.
    def _backlog(model, *extra):
        return int(db.query(func.count()).select_from(model).filter(
            model.status.in_(_PENDING), model.email.isnot(None), *extra).scalar() or 0)

    lead_backlog = _backlog(Lead)
    rest_backlog = _backlog(Restaurant, Restaurant.kind == "prospect")
    backlog = lead_backlog + rest_backlog

    # Recent send failures (today) so a stall is visible with its reason.
    fail_rows = (db.query(ActionLog.action, func.count())
                 .filter(ActionLog.created_at >= start, ActionLog.action.in_(_FAIL_ACTIONS))
                 .group_by(ActionLog.action).all())
    failures = {action: int(n) for action, n in fail_rows}

    paused = control.is_paused_safe(db)
    autopilot = control.outreach_autopilot(db)
    can_send = chan["channel"] is not None

    # The honest one-line status the UI headlines with.
    if paused:
        status, tone = "Paused — Emergency Stop is on. Nothing is sending.", "bad"
    elif not can_send:
        status, tone = ("No sender connected — connect SendGrid or a Gmail mailbox "
                        "on Setup, or nothing goes out.", "bad")
    elif backlog > 0 and sent_today == 0:
        status, tone = (f"{backlog} queued but 0 sent today — hit 'Send all pending "
                        "now' or check the sender.", "warn")
    elif cap and sent_today >= cap:
        status, tone = (f"Daily cap reached ({sent_today}/{cap}). More will send "
                        "tomorrow, or raise the cap.", "warn")
    else:
        status, tone = (f"Sending healthy — {sent_today} sent today via "
                        f"{chan['label']}.", "good")

    return {
        "status": status, "tone": tone,
        "channel": chan,
        "sent_today": sent_today, "sent_week": sent_week,
        "daily_cap": cap, "remaining_today": remaining,
        "backlog": backlog, "lead_backlog": lead_backlog,
        "restaurant_backlog": rest_backlog,
        "accounts": accounts,
        "failures": failures,
        "paused": paused, "autopilot": autopilot, "can_send": can_send,
    }


def send_pending_now(db: Session) -> dict:
    """Drain the entire outbox NOW — every queued lead + restaurant prospect.

    This is an explicit operator action, so it sends immediately (autonomous=False)
    rather than drafting; it still respects the daily cap, warmup, paused state and
    the real-email guard, so it can't blow past the provider's limit or email
    sample data. Mirrors what the auto-outreach cron does, but one click."""
    from . import bulk_outreach, contacts_outreach

    leads = bulk_outreach.dispatch_leads(db, autonomous=False)
    restaurants = bulk_outreach.dispatch_restaurants(db, autonomous=False)
    try:
        contacts = contacts_outreach.run(db)
    except Exception as exc:  # contacts are optional — never fail the whole drain
        contacts = {"error": str(exc)}

    dispatched = (int(leads.get("dispatched", 0)) + int(restaurants.get("dispatched", 0)))
    return {
        "ok": True, "dispatched": dispatched,
        "leads": leads, "restaurants": restaurants, "contacts": contacts,
        "sent_today": outreach.sent_today_count(db),
    }
