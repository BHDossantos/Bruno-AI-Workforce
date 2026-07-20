"""Auto-dial pass — work the Call List hands-free, paced one call per minute.

The scheduler calls this every minute starting at 8am (per_run_limit=1), so calls
go out one-per-minute — human pacing, not a burst — until the daily cap. It dials
the Call List (hottest first): a live answer transfers to the producer's CELL
(bridged + recorded), voicemail gets the recorded drop (or a spoken fallback until
one is recorded). It reuses the same rails as the rest of the outreach engine so
it can't misbehave:

  • gated by the same Outreach Autopilot / full-auto switch as auto-send, and by
    the Emergency Stop, plus its own AUTO_DIAL_ENABLED master switch;
  • compliance: opted-out numbers are skipped, the 8am-9pm legal window is
    enforced (TCPA), and a daily cap protects the producer's line;
  • a per-lead cooldown so nobody is auto-called two days running;
  • dead/closed statuses are excluded.

No-ops cleanly when calling isn't connected.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func

from . import compliance, control, lead_temperature, sms_engine
from .config import settings
from .integrations import voice  # dispatcher → Plivo or Twilio/SignalWire
from .models import Lead, Message

log = logging.getLogger("bruno.autodial")

# Marker prefix on the call log line, so we can count auto-dials placed today
# (for the daily cap) without also counting manual calls.
_MARKER = "📞 Auto-dial"


def _recently_called_ids(db, since: datetime) -> set:
    """Lead ids we've placed a call to since `since` (manual OR auto) — the cooldown
    set, so the daily pass never re-dials a lead you just reached out to."""
    rows = db.query(Message.entity_id).filter(
        Message.channel == "call", Message.entity_type == "lead",
        Message.sent_at >= since).all()
    return {r[0] for r in rows}


def _auto_dialed_today(db) -> int:
    """How many auto-dials we've already placed today — so the daily cap holds even
    when the pass runs once-per-minute (1 call each) instead of one burst."""
    start = datetime.combine(date.today(), datetime.min.time(), tzinfo=timezone.utc)
    return db.query(func.count()).select_from(Message).filter(
        Message.channel == "call", Message.direction == "outbound",
        Message.sent_at >= start, Message.body.like(f"{_MARKER}%")).scalar() or 0


def run(db, per_run_limit: int | None = None) -> dict:
    """Place auto-dials, hottest first. ``per_run_limit`` caps how many to place in
    THIS invocation — the scheduler passes 1 so calls go out one-per-minute from 8am
    (paced, human), while the manual 'run now' bursts up to the day's remaining cap.
    The per-day total is always bounded by AUTO_DIAL_DAILY_CAP. Returns a summary."""
    if not settings.auto_dial_enabled:
        return {"skipped": "auto-dial disabled (AUTO_DIAL_ENABLED=false)"}
    if control.is_paused_safe(db):
        return {"skipped": "paused"}
    if control.get_mode(db) != "auto" and not control.outreach_autopilot(db):
        return {"skipped": "autopilot off (turn on Outreach Autopilot to enable)"}

    # Load the live voice number / recorded-voicemail URL onto settings (any Cloud
    # Run instance may be cold), exactly like the call webhooks do.
    try:
        from . import runtime_config
        runtime_config.apply_to_settings(db)
    except Exception:  # runtime config is best-effort — env vars still work
        log.debug("runtime config refresh skipped", exc_info=True)

    if not voice.is_configured():
        return {"skipped": "calling not connected"}
    if not sms_engine.in_send_window():   # reuse the shared 8am-9pm legal window
        return {"skipped": "outside calling hours"}

    cap = max(0, settings.auto_dial_daily_cap)
    if cap == 0:
        return {"skipped": "daily cap is 0"}
    # Daily cap holds across the once-per-minute runs: stop once today's total hits it.
    remaining = cap - _auto_dialed_today(db)
    if remaining <= 0:
        return {"skipped": f"daily cap reached ({cap})"}
    run_cap = remaining if per_run_limit is None else max(0, min(per_run_limit, remaining))
    if run_cap == 0:
        return {"skipped": "nothing to place this run"}

    # Cooldown measured by CALENDAR day (same boundary as the daily cap), so the
    # dialer round-robins: a lead dialed today is skipped today, but eligible again
    # tomorrow. cooldown_days=1 → once/day; N → skip the last N calendar days.
    day_start = datetime.combine(date.today(), datetime.min.time(), tzinfo=timezone.utc)
    cutoff = day_start - timedelta(days=max(0, settings.auto_dial_cooldown_days - 1))
    recent = _recently_called_ids(db, cutoff)
    dead = lead_temperature.statuses_for(lead_temperature.DEAD) or set()

    # Work the Call List in the SAME priority as email/SMS: hot → warm → cold
    # (dead last), uncontacted-first then hottest score within a tier. Keeps every
    # channel dialing/emailing the same lead order. Dead/closed are already excluded.
    q = (db.query(Lead)
         .filter(Lead.phone.isnot(None), Lead.phone != "")
         .filter(~func.lower(func.coalesce(Lead.status, "")).in_(dead))
         .order_by(*lead_temperature.dispatch_order(Lead)))

    placed: list[str] = []
    errors = skipped_recent = skipped_optout = skipped_blocked = 0
    vm = voice.voicemail_configured()

    # Over-fetch: the cooldown + compliance filters thin the set, so pull more than
    # the run cap and stop once `run_cap` calls are actually placed.
    for lead in q.limit(max(run_cap * 6, 6)).all():
        if len(placed) >= run_cap:
            break
        if lead.id in recent:
            skipped_recent += 1
            continue
        # Every call clears the Compliance & Governance gate first (opt-out/DNC,
        # licensing, contact-hours, daily cap) — and the decision is audit-logged.
        decision = compliance.gate(db, channel="call", phone=lead.phone,
                                   entity_type="lead", entity_id=lead.id, actor="auto_dial")
        if not decision.allowed:
            if decision.rule in ("opt_out", "dnc"):
                skipped_optout += 1
            else:
                skipped_blocked += 1
            continue
        sid, err = voice.place_auto_call(lead.phone, str(lead.id))
        if not sid:
            errors += 1
            log.info("auto-dial skipped lead %s: %s", lead.id, err)
            continue
        drop = "leaves your recorded voicemail" if vm else "leaves a spoken message"
        db.add(Message(channel="call", direction="outbound", entity_type="lead",
                       entity_id=lead.id, from_account="insurance",
                       body=f"{_MARKER} — transfers to your cell if answered, {drop} if not…",
                       status="Dialing", provider_id=sid,
                       sent_at=datetime.now(timezone.utc)))
        lead.times_contacted = (lead.times_contacted or 0) + 1
        lead.last_contacted_at = datetime.now(timezone.utc)
        placed.append(str(lead.id))

    db.commit()
    log.info("Auto-dial: placed=%d errors=%d skipped_recent=%d skipped_optout=%d "
             "skipped_blocked=%d cap=%d", len(placed), errors, skipped_recent,
             skipped_optout, skipped_blocked, cap)
    return {"placed": len(placed), "errors": errors, "skipped_recent": skipped_recent,
            "skipped_optout": skipped_optout, "skipped_blocked": skipped_blocked,
            "voicemail_recorded": vm, "cap": cap}
