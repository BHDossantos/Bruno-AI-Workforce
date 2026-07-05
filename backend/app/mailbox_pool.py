"""Mailbox pool — every sending identity in one view.

Like Instantly/Smartlead's inbox pool: each mailbox you can send from (the four
Gmail accounts and each verified SendGrid sender), with its health, today's sends
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
from .integrations import gmail, sendgrid
from .models import Message

_GMAIL_ACCOUNTS = [
    (gmail.PERSONAL, "Personal"),
    (gmail.INSURANCE, "Insurance (primary)"),
    (gmail.INSURANCE_BACKUP, "Insurance #2 (backup)"),
    (gmail.BNB, "BnB Global"),
    (gmail.SAVORYMIND, "SavoryMind"),
]
_SENDGRID_BUSINESS = [
    ("insurance", "Thrust Insurance"),
    ("bnb", "BnB Global"),
    ("savorymind", "SavoryMind"),
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
    sendgrid_on = sendgrid.is_configured()
    global_sent = outreach.sent_today_count(db)

    mailboxes = []

    # SendGrid verified senders — the durable, at-volume channel. They share ONE
    # global daily cap (SendGrid's account limit), so capacity is counted once.
    if sendgrid.has_key():
        for business, label in _SENDGRID_BUSINESS:
            sender = sendgrid.from_for(business)
            if not sender:
                continue
            mailboxes.append({
                "id": f"sendgrid:{business}", "type": "sendgrid", "label": label,
                "address": sender, "reply_to": sendgrid.replyto_for(business, sender),
                "connected": sendgrid_on,
                "sent_today": outreach.sent_today_count(db, business),
                "daily_cap": settings.sendgrid_daily_cap, "shared_cap": True,
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

    # Pool capacity. SendGrid is one shared global limit (counted once, when a
    # verified sender exists); Gmail mailboxes each add their own effective cap.
    sendgrid_capacity = settings.sendgrid_daily_cap if sendgrid_on else 0
    gmail_capacity = sum(m["daily_cap"] for m in mailboxes
                         if m["type"] == "gmail" and m["connected"])
    total_capacity = sendgrid_capacity + gmail_capacity

    connected_count = sum(1 for m in mailboxes if m["connected"])
    return {
        "active_channel": sendgrid.is_configured() and "sendgrid"
        or (gmail.is_configured(gmail.PERSONAL) and "gmail") or None,
        "mailboxes": mailboxes,
        "connected_count": connected_count,
        "totals": {
            "daily_capacity": total_capacity,
            "sent_today": global_sent,
            "remaining": max(0, total_capacity - global_sent),
            "sendgrid_shared_cap": sendgrid_capacity or None,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
