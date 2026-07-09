"""Daily auto-dial pass — work the Call List hands-free every morning.

At 8am the scheduler calls this. It auto-dials the Call List (hottest first):
a live answer transfers to the producer's phone (bridged + recorded), voicemail
gets the recorded drop (or a spoken fallback until one is recorded). It reuses the
same rails as the rest of the outreach engine so it can't misbehave:

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
from datetime import datetime, timedelta, timezone

from sqlalchemy import func

from . import compliance, control, lead_temperature, sms_engine
from .config import settings
from .integrations import twilio_voice as voice
from .models import Lead, Message

log = logging.getLogger("bruno.autodial")


def _recently_called_ids(db, since: datetime) -> set:
    """Lead ids we've placed a call to since `since` (manual OR auto) — the cooldown
    set, so the daily pass never re-dials a lead you just reached out to."""
    rows = db.query(Message.entity_id).filter(
        Message.channel == "call", Message.entity_type == "lead",
        Message.sent_at >= since).all()
    return {r[0] for r in rows}


def run(db) -> dict:
    """Place the day's auto-dials. Returns a summary of what it did / why it skipped."""
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

    cooldown = timedelta(days=max(1, settings.auto_dial_cooldown_days))
    recent = _recently_called_ids(db, datetime.now(timezone.utc) - cooldown)
    dead = lead_temperature.statuses_for(lead_temperature.DEAD) or set()

    # Hottest first; only leads with a phone and not in a dead/closed status.
    # Unscored leads sort last (nullslast) so real hot leads are dialed first.
    q = (db.query(Lead)
         .filter(Lead.phone.isnot(None), Lead.phone != "")
         .filter(~func.lower(func.coalesce(Lead.status, "")).in_(dead))
         .order_by(Lead.score.desc().nullslast(), Lead.created_at.desc()))

    placed: list[str] = []
    errors = skipped_recent = skipped_optout = skipped_blocked = 0
    vm = voice.voicemail_configured()

    # Over-fetch: the cooldown + compliance filters thin the set, so pull more than
    # the cap and stop once `cap` calls are actually placed.
    for lead in q.limit(max(cap * 6, cap)).all():
        if len(placed) >= cap:
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
                       body=f"📞 Auto-dial (8am) — transfers to you if answered, {drop} if not…",
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
