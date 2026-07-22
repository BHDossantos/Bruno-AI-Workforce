"""Mailbox pool — every sending identity in one view.

Like Instantly/Smartlead's inbox pool: each mailbox you can send from (the Gmail
accounts and the Resend verified sender), with its health, today's sends
vs its daily cap, and warmup progress — plus the pool's total daily capacity. So
you can see at a glance how much outreach the whole engine can push today and
which identity is carrying it.

Read-only and network-light: connection state is `is_configured` (the live
send-test lives on Setup → mailbox health), so this loads fast on every visit.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import func

from . import outreach
from .config import settings
from .integrations import gmail, resend
from .models import Message

_GMAIL_ACCOUNTS = [
    (gmail.PERSONAL, "Personal"),
    (gmail.INSURANCE, "Insurance (primary)"),
    (gmail.INSURANCE_BACKUP, "Insurance #2 (backup)"),
    (gmail.BNB, "BnB Global"),
    (gmail.SAVORYMIND, "SavoryMind"),
]


def _warmup(db, account: str) -> dict:
    """Warmup progress for a Gmail mailbox: which ramp day it's on and whether it
    has reached the full cap yet."""
    if not settings.email_warmup_enabled:
        return {"enabled": False, "day": None, "at_ceiling": True}
    first = db.query(func.min(Message.sent_at)).filter(
        Message.from_account == account, Message.sent_at.isnot(None)).scalar()
    day = (date.today() - first.date()).days if first else 0
    return {
        "enabled": True, "day": day,
        "at_ceiling": outreach.effective_cap(db, account) >= settings.gmail_daily_send_cap,
    }


def snapshot(db) -> dict:
    """Every sending identity + the pool's combined daily capacity."""
    resend_on = resend.is_configured()
    global_sent = outreach.sent_today_count(db)

    mailboxes = []

    # Resend verified sender — the durable, at-volume channel. It shares ONE
    # global daily cap, so capacity is counted once.
    if resend.has_key():
        sender = resend.from_for("insurance")
        if sender:
            mailboxes.append({
                "id": "resend:insurance", "type": "resend", "label": "Resend (verified domain)",
                "address": sender, "reply_to": resend.replyto_for("insurance", sender),
                "connected": resend_on,
                "sent_today": global_sent,
                "daily_cap": settings.gmail_daily_send_cap, "shared_cap": True,
                "warmup": {"enabled": False, "day": None, "at_ceiling": True},
            })

    # Gmail mailboxes — each capped per-account with warmup.
    for account, label in _GMAIL_ACCOUNTS:
        connected = gmail.is_configured(account)
        cap = outreach.effective_cap(db, account)
        sent = outreach.sent_today_count(db, account)
        mailboxes.append({
            "id": f"gmail:{account}", "type": "gmail", "label": label,
            "address": None, "reply_to": None, "connected": connected,
            "sent_today": sent, "daily_cap": cap, "shared_cap": False,
            "remaining": max(0, cap - sent) if connected else 0,
            "warmup": _warmup(db, account),
        })

    # Pool capacity. Resend is one shared global limit (counted once, when a
    # verified sender exists); Gmail mailboxes each add their own effective cap.
    resend_capacity = settings.gmail_daily_send_cap if resend_on else 0
    gmail_capacity = sum(m["daily_cap"] for m in mailboxes
                         if m["type"] == "gmail" and m["connected"])
    total_capacity = resend_capacity + gmail_capacity

    connected_count = sum(1 for m in mailboxes if m["connected"])
    return {
        "active_channel": resend.is_configured() and "resend"
        or (gmail.is_configured(gmail.PERSONAL) and "gmail") or None,
        "mailboxes": mailboxes,
        "connected_count": connected_count,
        "totals": {
            "daily_capacity": total_capacity,
            "sent_today": global_sent,
            "remaining": max(0, total_capacity - global_sent),
            "resend_shared_cap": resend_capacity or None,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
