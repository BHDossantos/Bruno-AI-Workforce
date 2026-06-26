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
