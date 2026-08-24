"""EverQuote twice-a-day cadence — call AND text every EverQuote lead twice daily.

Bruno's rule: EverQuote leads (paid, time-sensitive) get two touches a day on both
channels — a MORNING wave (from 8am ET) and an AFTERNOON wave (from 3pm ET). This
module is the single owner of that cadence.

How it stays at exactly two touches/day per channel (not three), without touching
the other outreach jobs: each wave DEDUPES against *every* outbound message since
that wave started. So if the general auto-dialer or auto-send already reached a
lead this wave, the cadence skips it; otherwise the cadence places it. Net per
EverQuote lead: at most one call + one text per wave → two of each per day.

It rides the same rails as the rest of the engine so it can't misbehave:
  • gated by Outreach Autopilot / full-auto and the Emergency Stop;
  • compliance-gated per touch (opt-out/DNC, the 8am-9pm legal window, daily caps);
  • paced one lead per run (the scheduler calls it once a minute in each window);
  • dead/closed leads and blank phones excluded.

No-ops cleanly when calling/texting isn't connected.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func

from . import compliance, control, lead_temperature, sms_engine
from .config import settings
from .integrations import voice
from .models import Lead, Message

log = logging.getLogger("bruno.everquote_cadence")

# When each wave opens, in the operator's local (recipient) timezone. The morning
# wave runs from 8am until the afternoon wave opens at 3pm; the afternoon wave runs
# from 3pm until the legal 9pm cutoff.
_AM_HOUR = 8
_PM_HOUR = 15

_CALL_MARKER = "📞 EverQuote cadence"


def _tz() -> ZoneInfo:
    try:
        return ZoneInfo(settings.sms_timezone or "America/New_York")
    except Exception:  # pragma: no cover - bad tz string
        return ZoneInfo("America/New_York")


def current_wave(now: datetime | None = None) -> str | None:
    """Which wave is open right now: 'am' (8am-3pm), 'pm' (3pm-9pm), or None."""
    local = (now or datetime.now(timezone.utc)).astimezone(_tz())
    if _AM_HOUR <= local.hour < _PM_HOUR:
        return "am"
    if _PM_HOUR <= local.hour < settings.sms_send_window_end:
        return "pm"
    return None


def _wave_start_utc(wave: str, now: datetime | None = None) -> datetime:
    """The instant this wave opened, in UTC — the dedup boundary. A lead touched at
    or after this is already done for the wave."""
    tz = _tz()
    local = (now or datetime.now(timezone.utc)).astimezone(tz)
    hour = _AM_HOUR if wave == "am" else _PM_HOUR
    start_local = datetime.combine(local.date(), time(hour), tzinfo=tz)
    return start_local.astimezone(timezone.utc)


def _touched_ids(db, channel: str, since: datetime) -> set:
    """Lead ids we've SENT this channel to since `since` — the per-wave dedup set.
    Only counts touches that actually went out (sent_at set), so a failed/blocked
    attempt doesn't wrongly mark a lead done for the wave."""
    rows = db.query(Message.entity_id).filter(
        Message.channel == channel, Message.entity_type == "lead",
        Message.direction == "outbound", Message.sent_at.isnot(None),
        Message.sent_at >= since).all()
    return {r[0] for r in rows}


def _calls_today(db) -> int:
    """EverQuote-cadence calls placed today — so the day's total honors the cap even
    across the once-per-minute runs (two waves)."""
    start = datetime.combine(date.today(), datetime.min.time(), tzinfo=timezone.utc)
    return db.query(func.count()).select_from(Message).filter(
        Message.channel == "call", Message.direction == "outbound",
        Message.sent_at >= start, Message.body.like(f"{_CALL_MARKER}%")).scalar() or 0


def _followup_text(wave: str) -> str:
    """A short, warm EverQuote insurance follow-up with a clear next step. Kept brief
    and first-person so a twice-daily touch reads like a real producer, not a blast."""
    from . import email_template
    book = email_template.booking_link("insurance")
    cta = f"Grab a time here: {book}" if book else "Reply or call when you have 2 minutes."
    name = settings.producer_name or "your agent"
    if wave == "am":
        return (f"Good morning! It's {name} — following up on your insurance quote. "
                f"I can likely beat what you're paying now. {cta}")
    return (f"Hi again, it's {name}. Still happy to run your insurance numbers today "
            f"and see what I can save you. {cta}")


def run(db, per_run_limit: int = 1) -> dict:
    """Place the EverQuote cadence for the open wave: one lead per run (paced), a call
    and a text each, deduped against everything already sent this wave. Returns a
    summary. No-ops outside the two wave windows."""
    if control.is_paused_safe(db):
        return {"skipped": "paused"}
    if control.get_mode(db) != "auto" and not control.outreach_autopilot(db):
        return {"skipped": "autopilot off (turn on Outreach Autopilot to enable)"}

    wave = current_wave()
    if wave is None:
        return {"skipped": "outside wave windows (8am / 3pm ET)"}

    # Cold instances: load live voice number / voicemail / creds, like the webhooks do.
    try:
        from . import runtime_config
        runtime_config.apply_to_settings(db)
    except Exception:  # best-effort — env vars still work
        log.debug("runtime config refresh skipped", exc_info=True)

    can_call = voice.is_configured()
    from .integrations import sms as sms_int
    can_text = sms_int.is_configured() or bool(settings.bridge_token)
    if not (can_call or can_text):
        return {"skipped": "calling and texting both not connected"}

    since = _wave_start_utc(wave)
    called = _touched_ids(db, "call", since)
    texted = _touched_ids(db, "sms", since)
    dead = lead_temperature.statuses_for(lead_temperature.DEAD) or set()

    # Call-cap headroom for the day (shared with the general dialer's intent — protect
    # the line). Texts self-cap inside send_text against sms_daily_send_cap.
    call_cap = max(0, settings.auto_dial_daily_cap)
    call_headroom = (call_cap - _calls_today(db)) if call_cap else 0

    # EverQuote leads only, hottest first, with a phone. Dead/closed excluded.
    category = func.lower(func.coalesce(Lead.category, ""))
    q = (db.query(Lead)
         .filter(Lead.phone.isnot(None), Lead.phone != "")
         .filter(category.like("everquote%"))
         .filter(~func.lower(func.coalesce(Lead.status, "")).in_(dead))
         .order_by(*lead_temperature.dispatch_order(Lead)))

    calls = texts = 0
    errors = skipped_done = skipped_blocked = 0
    vm = voice.voicemail_configured() if can_call else False
    body = _followup_text(wave)

    # Over-fetch: dedup + compliance thin the set; stop once per_run_limit leads acted.
    acted = 0
    for lead in q.limit(max(per_run_limit * 8, 8)).all():
        if acted >= per_run_limit:
            break
        # Skip a masked/invalid phone ("************") entirely — this cadence is
        # phone-only (call + text); a lead without a real number is reached by
        # email elsewhere, never dialed or texted here.
        if not sms_int._e164(lead.phone):
            skipped_blocked += 1
            continue
        need_call = can_call and lead.id not in called and call_headroom > 0
        need_text = can_text and lead.id not in texted
        if not (need_call or need_text):
            skipped_done += 1
            continue

        did_something = False

        if need_call:
            decision = compliance.gate(db, channel="call", phone=lead.phone,
                                       entity_type="lead", entity_id=lead.id,
                                       actor="everquote_cadence")
            if not decision.allowed:
                skipped_blocked += 1
            else:
                sid, err = voice.place_auto_call(lead.phone, str(lead.id))
                if sid:
                    action = ("leaves your recorded voicemail" if vm
                              else "leaves a spoken message")
                    db.add(Message(channel="call", direction="outbound",
                                   entity_type="lead", entity_id=lead.id,
                                   from_account="insurance",
                                   body=f"{_CALL_MARKER} ({wave}) — {action} on answer…",
                                   status="Dialing", provider_id=sid,
                                   sent_at=datetime.now(timezone.utc)))
                    calls += 1
                    call_headroom -= 1
                    did_something = True
                else:
                    errors += 1
                    log.info("cadence call skipped lead %s: %s", lead.id, err)

        if need_text:
            sid = sms_engine.send_text(db, entity_type="lead", entity_id=lead.id,
                                       phone=lead.phone, body=body, account="insurance")
            if sid:
                texts += 1
                did_something = True

        if did_something:
            lead.times_contacted = (lead.times_contacted or 0) + 1
            lead.last_contacted_at = datetime.now(timezone.utc)
            acted += 1

    db.commit()
    log.info("EverQuote cadence [%s]: calls=%d texts=%d errors=%d done=%d blocked=%d",
             wave, calls, texts, errors, skipped_done, skipped_blocked)
    return {"wave": wave, "calls": calls, "texts": texts, "errors": errors,
            "skipped_done": skipped_done, "skipped_blocked": skipped_blocked,
            "voicemail_recorded": vm}
