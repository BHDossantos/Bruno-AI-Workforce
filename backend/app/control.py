"""Global execution control — the Emergency Stop kill-switch.

One runtime flag, `agents_paused`, that immediately halts all autonomous action:
scheduled jobs are skipped, outreach sends degrade to drafts, and content stops
publishing. It's checked at the few central choke points so nothing slips through.
Stored in the Setting table so it survives restarts and takes effect without a
redeploy.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from .models import Setting

log = logging.getLogger("bruno.control")

_PAUSED_KEY = "agents_paused"
_MODE_KEY = "automation_mode"
_OUTREACH_KEY = "outreach_autopilot"
_AUTOAPPLY_KEY = "auto_apply_mode"
MODES = ("manual", "semi", "auto")
_DEFAULT_MODE = "semi"  # agents prepare everything; you approve to send/post
AUTO_APPLY_MODES = ("off", "compliant", "aggressive")


def auto_apply_mode(db: Session) -> str:
    """How the auto-apply engine submits job applications:
    - off (default): prepare only — you click apply (no auto-submit).
    - compliant: auto-submit on company ATS pages (Greenhouse/Lever/etc.);
      LinkedIn/Indeed/unknown are queued for one click.
    - aggressive: ALSO auto-submit LinkedIn/Indeed Easy Apply via your stored
      session (higher volume; violates those platforms' ToS — account risk).
    Stored in Settings so it survives restarts and toggles without a redeploy."""
    try:
        row = db.get(Setting, _AUTOAPPLY_KEY)
        val = (row.value or "").lower() if row else ""
        return val if val in AUTO_APPLY_MODES else "off"
    except Exception:  # pragma: no cover - defensive
        return "off"


def set_auto_apply_mode(db: Session, mode: str) -> str:
    mode = (mode or "").lower()
    if mode not in AUTO_APPLY_MODES:
        mode = "off"
    row = db.get(Setting, _AUTOAPPLY_KEY)
    if row is None:
        row = Setting(key=_AUTOAPPLY_KEY)
        db.add(row)
    row.value = mode
    db.commit()
    return mode


def outreach_autopilot(db: Session) -> bool:
    """When ON, SALES outreach (cold leads + their follow-ups) auto-sends even in
    semi mode — so the lead machine runs on its own — while content still drafts
    for approval. Default ON: the user explicitly wants automated outreach. Stored
    in Settings so it survives restarts and toggles without a redeploy."""
    try:
        row = db.get(Setting, _OUTREACH_KEY)
        if row is None or row.value is None:
            return True  # default on
        return (row.value or "").lower() in ("1", "true", "yes", "on")
    except Exception:  # pragma: no cover - defensive
        return True


def set_outreach_autopilot(db: Session, on: bool) -> bool:
    row = db.get(Setting, _OUTREACH_KEY)
    if row is None:
        row = Setting(key=_OUTREACH_KEY)
        db.add(row)
    row.value = "true" if on else "false"
    db.commit()
    return on


def get_mode(db: Session) -> str:
    """manual | semi | auto. Default 'semi' — agents draft, you hit send."""
    try:
        row = db.get(Setting, _MODE_KEY)
        val = (row.value or "").lower() if row else ""
        return val if val in MODES else _DEFAULT_MODE
    except Exception:  # pragma: no cover - defensive
        return _DEFAULT_MODE


def set_mode(db: Session, mode: str) -> str:
    mode = (mode or "").lower()
    if mode not in MODES:
        mode = _DEFAULT_MODE
    row = db.get(Setting, _MODE_KEY)
    if row is None:
        row = Setting(key=_MODE_KEY)
        db.add(row)
    row.value = mode
    db.commit()
    return mode


def is_autopilot(db: Session) -> bool:
    """True only in full-auto mode — otherwise agents draft and wait for approval."""
    return get_mode(db) == "auto"


def is_paused(db: Session) -> bool:
    row = db.get(Setting, _PAUSED_KEY)
    return bool(row and (row.value or "").lower() in ("1", "true", "yes", "on"))


def set_paused(db: Session, paused: bool) -> bool:
    row = db.get(Setting, _PAUSED_KEY)
    if row is None:
        row = Setting(key=_PAUSED_KEY)
        db.add(row)
    row.value = "true" if paused else "false"
    db.commit()
    log.warning("Emergency stop %s — all agents %s",
                "ENGAGED" if paused else "released",
                "paused" if paused else "resumed")
    return paused


def is_paused_safe(db: Session) -> bool:
    """Never let a bad/missing settings row block normal operation."""
    try:
        return is_paused(db)
    except Exception:  # pragma: no cover - defensive
        return False
