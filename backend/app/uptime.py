"""Uptime monitoring — watch the live apps and client sites, hands-free.

A self-contained domain: each Monitor is a URL probed on its own interval by the
scheduler (``run_due``). The probe records up/down, latency and HTTP code, rolls
the all-time uptime counters on the row, and keeps a short pruned history in
MonitorCheck for a sparkline. ``_probe`` is the only I/O seam, so tests monkeypatch
it. No new columns on existing tables — two brand-new tables only (create_all safe).
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy.orm import Session

from .models import Monitor, MonitorCheck

log = logging.getLogger("bruno.uptime")

_TIMEOUT = 10.0
_HISTORY_KEEP = 50  # probes retained per monitor


def _probe(url: str, method: str, expected_status: int) -> tuple[bool, int | None, int, str | None]:
    """Make one request. Returns (ok, status_code, latency_ms, error). The only
    network seam — tests monkeypatch this. 2xx/3xx counts as up unless an exact
    expected_status is set and not met."""
    start = time.monotonic()
    try:
        r = httpx.request(method.upper(), url, timeout=_TIMEOUT, follow_redirects=True)
        latency = int((time.monotonic() - start) * 1000)
        if expected_status:
            ok = r.status_code == expected_status
        else:
            ok = 200 <= r.status_code < 400
        return ok, r.status_code, latency, None if ok else f"HTTP {r.status_code}"
    except Exception as exc:  # DNS, TLS, timeout, connection refused…
        latency = int((time.monotonic() - start) * 1000)
        return False, None, latency, str(exc)[:200]


def check(db: Session, monitor: Monitor) -> Monitor:
    """Probe one monitor, persist the result + rolled counters, prune history."""
    ok, code, latency, error = _probe(monitor.url, monitor.method, monitor.expected_status)
    now = datetime.now(timezone.utc)
    monitor.last_status = "up" if ok else "down"
    monitor.last_code = code
    monitor.last_latency_ms = latency
    monitor.last_error = error
    monitor.last_checked_at = now
    monitor.checks_total = (monitor.checks_total or 0) + 1
    monitor.checks_up = (monitor.checks_up or 0) + (1 if ok else 0)
    monitor.consecutive_failures = 0 if ok else (monitor.consecutive_failures or 0) + 1
    db.add(MonitorCheck(monitor_id=monitor.id, status=monitor.last_status,
                        code=code, latency_ms=latency, error=error, checked_at=now))
    db.flush()
    # Prune to the most recent _HISTORY_KEEP probes.
    extra = (db.query(MonitorCheck)
             .filter(MonitorCheck.monitor_id == monitor.id)
             .order_by(MonitorCheck.checked_at.desc())
             .offset(_HISTORY_KEEP).all())
    for row in extra:
        db.delete(row)
    db.commit()
    db.refresh(monitor)
    return monitor


def run_due(db: Session) -> dict:
    """Probe every enabled monitor whose interval has elapsed. Scheduler-run."""
    now = datetime.now(timezone.utc)
    checked = 0
    for m in db.query(Monitor).filter(Monitor.enabled.is_(True)).all():
        due = (m.last_checked_at is None
               or (now - m.last_checked_at) >= timedelta(minutes=max(1, m.interval_minutes)))
        if due:
            try:
                check(db, m)
                checked += 1
            except Exception:
                log.exception("monitor probe failed for %s", m.url)
    return {"checked": checked}


def create_monitor(db: Session, *, name: str, url: str, business: str | None = None,
                   method: str = "GET", expected_status: int = 200,
                   interval_minutes: int = 5) -> Monitor:
    m = Monitor(name=name.strip(), url=url.strip(), business=business,
                method=(method or "GET").upper(), expected_status=expected_status or 200,
                interval_minutes=max(1, interval_minutes or 5), last_status="unknown")
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


def update_monitor(db: Session, monitor_id, **fields) -> Monitor | None:
    m = db.get(Monitor, monitor_id)
    if m is None:
        return None
    for key in ("name", "url", "business", "method"):
        if fields.get(key) is not None:
            setattr(m, key, fields[key])
    if fields.get("expected_status") is not None:
        m.expected_status = fields["expected_status"]
    if fields.get("interval_minutes") is not None:
        m.interval_minutes = max(1, fields["interval_minutes"])
    if fields.get("enabled") is not None:
        m.enabled = bool(fields["enabled"])
    db.commit()
    db.refresh(m)
    return m


def delete_monitor(db: Session, monitor_id) -> bool:
    m = db.get(Monitor, monitor_id)
    if m is None:
        return False
    db.delete(m)
    db.commit()
    return True


def _uptime_pct(m: Monitor) -> float:
    return round(100 * (m.checks_up or 0) / m.checks_total, 1) if m.checks_total else 0.0


def _to_dict(m: Monitor, *, with_history: bool = False) -> dict:
    out = {
        "id": str(m.id), "name": m.name, "url": m.url, "business": m.business,
        "method": m.method, "expected_status": m.expected_status,
        "interval_minutes": m.interval_minutes, "enabled": m.enabled,
        "last_status": m.last_status or "unknown", "last_code": m.last_code,
        "last_latency_ms": m.last_latency_ms, "last_error": m.last_error,
        "last_checked_at": m.last_checked_at.isoformat() if m.last_checked_at else None,
        "consecutive_failures": m.consecutive_failures or 0,
        "uptime_pct": _uptime_pct(m), "checks_total": m.checks_total or 0,
    }
    if with_history:
        hist = sorted(m.checks, key=lambda c: c.checked_at or datetime.min)[-_HISTORY_KEEP:]
        out["history"] = [{
            "status": c.status, "code": c.code, "latency_ms": c.latency_ms,
            "checked_at": c.checked_at.isoformat() if c.checked_at else None,
        } for c in hist]
    return out


def list_monitors(db: Session) -> list[dict]:
    rows = db.query(Monitor).order_by(Monitor.created_at.desc()).all()
    return [_to_dict(m) for m in rows]


def get_monitor(db: Session, monitor_id) -> dict | None:
    m = db.get(Monitor, monitor_id)
    return _to_dict(m, with_history=True) if m else None


def summary(db: Session) -> dict:
    rows = db.query(Monitor).all()
    up = sum(1 for m in rows if m.last_status == "up")
    down = sum(1 for m in rows if m.last_status == "down")
    return {
        "total": len(rows), "up": up, "down": down,
        "unknown": len(rows) - up - down,
    }
