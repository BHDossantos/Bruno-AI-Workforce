"""SMS conversation engine: warm-intro auto-texts + thread storage.

A lead becomes *warm* when they reply to our email (set by inbound email sync).
At that point, if they have a phone and Twilio is configured, we auto-send one
friendly intro text and start a two-way thread that the user continues from the
dashboard. SMS are stored as ``Message`` rows with ``channel='sms'`` and the
contact's phone in ``to_email`` (the thread key).
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from .ai import client, skills
from .ai.prompts import SMS_INTRO
from .config import settings
from .integrations import sms
from .models import Message

log = logging.getLogger("bruno.sms_engine")


# --- Compliance + deliverability guards ------------------------------------
# A hard STOP is a legal line (TCPA): once someone texts an opt-out keyword we
# must never text them again. We also cap daily volume (deliverability) and
# refuse to text outside legal hours (8am-9pm recipient-local).
_STOP_WORDS = {"stop", "stopall", "unsubscribe", "cancel", "end", "quit",
               "optout", "revoke", "remove"}


def _norm_phone(phone: str | None) -> str:
    return re.sub(r"\D", "", phone or "")[-10:]


def is_opted_out(db: Session, phone: str) -> bool:
    """True if this number ever texted us a STOP keyword. Deterministic (no AI):
    a message that IS just a stop word (e.g. 'STOP', 'unsubscribe') opts out.
    Carriers honor STOP too, but we refuse to even queue so we never re-text
    someone who opted out."""
    key = _norm_phone(phone)
    if not key:
        return False
    for m in db.query(Message).filter(
            Message.channel == "sms", Message.direction == "inbound").all():
        if _norm_phone(m.to_email) != key:
            continue
        words = re.findall(r"[a-z]+", (m.body or "").lower())
        if words and words[0] in _STOP_WORDS:
            return True
    return False


def sms_sent_today(db: Session) -> int:
    """Texts actually sent today, across all numbers (the daily cap is global)."""
    start = datetime.combine(date.today(), datetime.min.time(), tzinfo=timezone.utc)
    return db.query(func.count()).select_from(Message).filter(
        Message.channel == "sms", Message.direction == "outbound",
        Message.sent_at >= start).scalar() or 0


def _now_local(now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        return now.astimezone(ZoneInfo(settings.sms_timezone or "America/New_York"))
    except Exception:  # tzdata missing (e.g. slim image) — approximate US Eastern
        return now.astimezone(timezone(timedelta(hours=-5)))


def in_send_window(now: datetime | None = None) -> bool:
    """True if the current recipient-local hour is inside the legal texting
    window (default 8am-9pm)."""
    hour = _now_local(now).hour
    return settings.sms_send_window_start <= hour < settings.sms_send_window_end


def sms_block_reason(db: Session, phone: str, *, enforce_hours: bool = True,
                     already_sent: int = 0) -> str | None:
    """A human reason to BLOCK this text, or None if it's clear to send.
    Opt-out is always enforced; hours/cap are enforced for autonomous + bulk
    sends (a human replying in-thread passes enforce_hours=False)."""
    if is_opted_out(db, phone):
        return "recipient opted out (texted STOP)"
    if enforce_hours and not in_send_window():
        return (f"outside texting hours "
                f"({settings.sms_send_window_start}:00-{settings.sms_send_window_end}:00 "
                f"{settings.sms_timezone})")
    if sms_sent_today(db) + already_sent >= settings.sms_daily_send_cap:
        return f"daily SMS cap reached ({settings.sms_daily_send_cap})"
    return None


def _has_prior_sms(db: Session, phone: str) -> bool:
    return db.query(Message).filter(
        Message.channel == "sms", Message.to_email == phone,
    ).first() is not None


def maybe_warm_text(db: Session, *, entity_type: str, entity_id, name: str | None,
                    phone: str | None, context: str, account: str) -> str | None:
    """Auto-send one warm intro SMS to a freshly-warm lead. Returns the SID or None."""
    from . import control
    if control.is_paused_safe(db):
        return None  # emergency stop — no autonomous texts
    _refresh_config(db)
    # Send via Twilio if configured, else queue for the Mac iMessage bridge.
    use_bridge = not sms.is_configured() and bool(settings.bridge_token)
    if not settings.sms_auto_on_reply or not phone or not (sms.is_configured() or use_bridge):
        return None
    if _has_prior_sms(db, phone):
        return None  # already in an SMS conversation
    block = sms_block_reason(db, phone, enforce_hours=True)
    if block:
        log.info("Warm SMS to %s blocked: %s", phone, block)
        return None

    art = client.complete_json(
        SMS_INTRO.format(name=name or "there", context=context or "your inquiry"),
        system=skills.system_prompt("sms"))
    body = (art.get("body") if isinstance(art, dict) else None) or (
        f"Hi {name or 'there'}, thanks for getting back to us! Happy to help — "
        f"what's the best way to move forward? Reply STOP to opt out.")

    sid = None if use_bridge else sms.send_sms(phone, body, account=account)
    # Bridge → "Queued" (the Mac helper picks it up); Twilio → Sent/Drafted.
    status = "Queued" if use_bridge else ("Sent" if sid else "Drafted")
    db.add(Message(
        channel="sms", direction="outbound", entity_type=entity_type, entity_id=entity_id,
        to_email=phone, from_account=account, body=body,
        status=status, provider_id=sid,
        sent_at=datetime.now(timezone.utc) if sid else None,
    ))
    log.info("Warm SMS to %s (%s): %s", phone, account,
             "queued(bridge)" if use_bridge else ("sent" if sid else "stored"))
    return "queued" if use_bridge else sid


def _refresh_config(db: Session) -> None:
    """Load Twilio/data credentials saved via the in-app Setup page into settings,
    even if THIS server instance started before they were saved (multi-instance
    safe). Without this, a stale instance wrongly reports SMS 'not configured'."""
    try:
        from . import runtime_config
        runtime_config.apply_to_settings(db)
    except Exception:  # never let a config refresh block a send
        pass


def send_text(db: Session, *, entity_type: str, entity_id, phone: str, body: str,
             account: str = "insurance", enforce_hours: bool = True) -> str | None:
    """Send an explicit (non-AI-drafted) text now — e.g. a quote-intake request —
    via Twilio if configured, else queue it for the free Mac iMessage bridge.
    Returns 'queued' (bridge), the provider SID (Twilio), or None if neither
    channel is available or a compliance guard (opt-out/hours/cap) blocks it."""
    _refresh_config(db)
    use_bridge = not sms.is_configured() and bool(settings.bridge_token)
    if not phone or not body or not (sms.is_configured() or use_bridge):
        return None
    if sms_block_reason(db, phone, enforce_hours=enforce_hours):
        return None  # opted out / outside legal hours / daily cap hit
    sid = None if use_bridge else sms.send_sms(phone, body, account=account)
    status = "Queued" if use_bridge else ("Sent" if sid else "Drafted")
    db.add(Message(
        channel="sms", direction="outbound", entity_type=entity_type, entity_id=entity_id,
        to_email=phone, from_account=account, body=body,
        status=status, provider_id=sid,
        sent_at=datetime.now(timezone.utc) if sid else None,
    ))
    db.commit()
    return "queued" if use_bridge else sid


def record_inbound(db: Session, *, phone: str, body: str) -> Message:
    """Store an inbound SMS, classify it, and link it to a known contact by phone
    (matched on the normalized last-10 digits so format differences never miss)."""
    from . import classify
    from .models import Lead, Restaurant

    cls = classify.classify_reply(body)
    msg = Message(channel="sms", direction="inbound", to_email=phone, body=body, status=cls["status"])
    # Best-effort link + apply the classified status (leads/restaurants advance).
    key = _norm_phone(phone)
    for model, etype in ((Lead, "lead"), (Restaurant, "restaurant")):
        if not key:
            break
        row = next((r for r in db.query(model).filter(model.phone.isnot(None)).all()
                    if _norm_phone(r.phone) == key), None)
        if row:
            msg.entity_type, msg.entity_id = etype, row.id
            if row.status not in ("Closed Won", "Closed Lost"):
                row.status = cls["status"]
            break
    db.add(msg)
    db.commit()
    return msg
