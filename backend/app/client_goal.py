"""Client-acquisition engine — drive toward a daily NEW-CLIENT target (default 15).

The standing order is blunt: "bring me clients 24/7 — at least 15 per day, I
don't care how." We can't manufacture a signed client out of thin air, but we
CAN size the machine so that — at the funnel's *measured* conversion rate — it
produces the target number of clients per day, and keep ramping volume
automatically until it does.

How it works:
  • Measure the real funnel — prospects contacted → clients won → conversion rate.
  • Back-calculate the daily cold-touch volume needed to hit the client target at
    that rate (a conservative default rate is used until there's enough data).
  • Auto-scale the runtime knobs (per-business lead targets + the daily send cap)
    up toward that volume, within safe ceilings that protect the mailbox.
  • Surface progress (clients today / target, on-track?) and, when the math can't
    reach the goal within safe limits, say exactly what's binding (add a mailbox,
    or improve targeting/conversion) instead of silently falling short.

Overrides are persisted in the Setting table (key prefix "scale:") and applied
onto the live ``settings`` object at startup and on every autoscale pass, so the
existing agents keep reading ``settings.*`` unchanged and the ramp survives
restarts. An explicit environment variable always wins over an autoscaled value.
"""
from __future__ import annotations

import json
import logging
import math
import os
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from .config import settings
from .models import Setting

log = logging.getLogger("bruno.client_goal")

_PREFIX = "scale:"
_SNAPSHOT_KEY = _PREFIX + "won_snapshot"  # {"date": "YYYY-MM-DD", "total": N}

# Won/closed statuses across every pipeline (case-insensitive).
_WON = {"won", "closed won", "client", "customer", "signed", "closed-won"}

# Runtime volume knobs the autoscaler is allowed to raise, paired with a per-field
# safety ceiling. These are the only fields it touches — content/quality settings
# are never auto-changed.
_SCALABLE: dict[str, str] = {
    "gmail_daily_send_cap": "client_send_cap_ceiling",
    "commercial_lead_daily_target": "client_lead_target_ceiling",
    "homeowner_lead_daily_target": "client_lead_target_ceiling",
    "referral_partner_daily_target": "client_lead_target_ceiling",
    "consulting_lead_daily_target": "client_lead_target_ceiling",
}


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _get(db: Session, key: str) -> str:
    try:
        row = db.get(Setting, key)
        return (row.value or "") if row else ""
    except Exception:  # pragma: no cover - defensive
        return ""


def _set(db: Session, key: str, value: str) -> None:
    row = db.get(Setting, key)
    if row is None:
        row = Setting(key=key)
        db.add(row)
    row.value = value


# ── persisted overrides ───────────────────────────────────────────────────────
def apply_overrides(db: Session) -> None:
    """Load autoscaled volume knobs into the live settings object (env vars win)."""
    if not os.environ.get("DAILY_CLIENT_TARGET"):
        tgt = _get(db, _PREFIX + "daily_client_target")
        if tgt:
            try:
                settings.daily_client_target = int(tgt)
            except Exception:  # pragma: no cover
                pass
    for field in _SCALABLE:
        if os.environ.get(field.upper()):
            continue
        val = _get(db, _PREFIX + field)
        if not val:
            continue
        try:
            setattr(settings, field, int(val))
        except Exception:  # pragma: no cover
            log.warning("could not apply scaled override %s=%s", field, val)


# ── funnel measurement ────────────────────────────────────────────────────────
def _count_won(db: Session) -> int:
    """Clients won across every sales pipeline (best-effort, source-isolated)."""
    from sqlalchemy import func as _f

    from .models import Contact, Lead, Opportunity, Restaurant

    total = 0
    for model in (Lead, Restaurant, Contact):
        try:
            for status, n in (db.query(model.status, _f.count()).group_by(model.status).all()):
                if (status or "").strip().lower() in _WON:
                    total += int(n)
        except Exception:  # pragma: no cover - a model without status, etc.
            continue
    try:
        total += db.query(Opportunity).filter(Opportunity.status == "Won").count()
    except Exception:  # pragma: no cover
        pass
    return total


def _count_contacted(db: Session) -> int:
    """Distinct prospects we've actually reached out to (the funnel's top line)."""
    from .models import Lead

    try:
        return db.query(Lead).filter(Lead.times_contacted > 0).count()
    except Exception:  # pragma: no cover
        return 0


def _sent_today(db: Session) -> int:
    from sqlalchemy import func as _f

    from .models import Message

    try:
        return (db.query(Message)
                .filter(Message.direction == "outbound", Message.status == "Sent",
                        _f.date(Message.sent_at) == _today())
                .count())
    except Exception:  # pragma: no cover
        return 0


def conversion_rate(db: Session) -> tuple[float, bool]:
    """(rate, measured?) — real won/contacted once there's a meaningful sample,
    else the conservative configured default so we don't under-build early."""
    won = _count_won(db)
    contacted = _count_contacted(db)
    default = float(getattr(settings, "client_default_conversion", 0.01) or 0.01)
    if contacted >= 150 and won >= 2:
        return max(won / contacted, 0.001), True
    return default, False


def _roll_snapshot(db: Session, won_total: int) -> int:
    """Maintain a start-of-day baseline so we can report clients won *today*."""
    today = _today()
    raw = _get(db, _SNAPSHOT_KEY)
    base = None
    if raw:
        try:
            snap = json.loads(raw)
            if snap.get("date") == today:
                base = int(snap.get("total", won_total))
        except Exception:  # pragma: no cover
            base = None
    if base is None:  # new day (or first run) → today starts now
        base = won_total
        _set(db, _SNAPSHOT_KEY, json.dumps({"date": today, "total": won_total}))
        try:
            db.commit()
        except Exception:  # pragma: no cover
            db.rollback()
    return max(0, won_total - base)


# ── autoscale ─────────────────────────────────────────────────────────────────
def autoscale(db: Session) -> dict:
    """Raise the runtime volume knobs toward the daily client target. Idempotent;
    only ever raises within ceilings, never lowers a manually-set higher value."""
    if not getattr(settings, "client_autoscale_enabled", True):
        return {"enabled": False}

    apply_overrides(db)
    target = int(getattr(settings, "daily_client_target", 15) or 15)
    rate, measured = conversion_rate(db)
    needed_touches = math.ceil(target / max(rate, 0.001))

    # Cold touches are spread across the outreach mailboxes (personal + insurance).
    cap_ceiling = int(getattr(settings, "client_send_cap_ceiling", 500) or 500)
    desired_cap = min(cap_ceiling, math.ceil(needed_touches / 2))

    lead_ceiling = int(getattr(settings, "client_lead_target_ceiling", 600) or 600)
    # Sourcing must out-pace sending so the queue never starves: aim each of the
    # main finders at a share of the needed volume.
    desired_lead = min(lead_ceiling, max(50, math.ceil(needed_touches / 3)))

    targets = {
        "gmail_daily_send_cap": desired_cap,
        "commercial_lead_daily_target": desired_lead,
        "homeowner_lead_daily_target": max(50, desired_lead // 2),
        "referral_partner_daily_target": max(25, desired_lead // 4),
        "consulting_lead_daily_target": desired_lead,
    }

    changed: dict[str, int] = {}
    for field, want in targets.items():
        if os.environ.get(field.upper()):
            continue  # respect an explicit env override
        current = int(getattr(settings, field, 0) or 0)
        if want > current:
            _set(db, _PREFIX + field, str(want))
            setattr(settings, field, want)
            changed[field] = want
    if changed:
        try:
            db.commit()
        except Exception:  # pragma: no cover
            db.rollback()

    # Honest capacity check: can the safe ceilings actually deliver the target?
    safe_capacity_touches = cap_ceiling * 2  # two mailboxes at the per-account ceiling
    reachable_clients = safe_capacity_touches * rate
    constraint = None
    if reachable_clients < target:
        constraint = (
            f"At the current {rate*100:.1f}% conversion, hitting {target} clients/day "
            f"needs ~{needed_touches} cold touches/day, but the safe mailbox ceiling "
            f"caps us near {int(reachable_clients)} clients/day. Add another sending "
            f"mailbox or improve targeting/conversion to close the gap.")

    log.info("client autoscale: target=%d rate=%.4f needed=%d changed=%s",
             target, rate, needed_touches, changed)
    return {
        "enabled": True, "target": target, "rate": round(rate, 4), "measured": measured,
        "needed_touches": needed_touches, "changed": changed, "constraint": constraint,
    }


# ── status (dashboard + API) ──────────────────────────────────────────────────
def status(db: Session) -> dict:
    target = int(getattr(settings, "daily_client_target", 15) or 15)
    won_total = _count_won(db)
    won_today = _roll_snapshot(db, won_total)
    contacted = _count_contacted(db)
    rate, measured = conversion_rate(db)
    needed_touches = math.ceil(target / max(rate, 0.001))
    sent_today = _sent_today(db)
    return {
        "target": target,
        "won_today": won_today,
        "won_total": won_total,
        "on_track": won_today >= target,
        "deficit": max(0, target - won_today),
        "conversion_rate": round(rate, 4),
        "conversion_measured": measured,
        "prospects_contacted": contacted,
        "needed_touches_per_day": needed_touches,
        "sent_today": sent_today,
    }
