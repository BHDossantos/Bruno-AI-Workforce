"""One reserved licensed handler per outbound leg. No predictive overdialing.

Provider uncertainty never times out into a new attempt. Reservations survive
process restarts; only confirmed terminal/no-attempt outcomes release capacity.
All mutations use the caller's SQLAlchemy transaction; reserve commits BEFORE I/O.
"""
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from . import compliance, control, outbound_guard, sms_engine
from .calling_capacity_models import CallHandler, CallPermit, CallReservation, CallLeadHold
from .config import settings
from .models import Lead

TERMINAL = {"completed", "busy", "no-answer", "failed", "canceled"}


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def reserve(db, lead, now=None):
    now = now or datetime.now(timezone.utc)
    permit = db.get(CallPermit, lead.id)
    from .integrations.sms import _e164
    if (not permit or utc(permit.expires_at) <= now or permit.phone != _e164(lead.phone)
            or not permit.authorization_ref or lead.segment not in {"commercial", "personal"}):
        return None
    if compliance.is_dnc(db, phone=permit.phone, email=lead.email):
        return None
    if db.get(CallLeadHold, lead.id):
        return None
    # PostgreSQL skips rows already reserved by another worker. The conditional
    # update below also fences engines without FOR UPDATE support (unit tests).
    handlers = db.scalars(select(CallHandler).where(
        CallHandler.reservation_id.is_(None), CallHandler.verified_until > now,
        CallHandler.available_until > now).order_by(CallHandler.id).with_for_update(skip_locked=True)).all()
    for handler in handlers:
        if permit.state not in handler.states or not handler.authorization_ref:
            continue
        rid = uuid4()
        changed = db.execute(update(CallHandler).where(
            CallHandler.id == handler.id, CallHandler.reservation_id.is_(None),
            CallHandler.available_until > now, CallHandler.verified_until > now
        ).values(reservation_id=rid).execution_options(synchronize_session="fetch"))
        if changed.rowcount != 1:
            continue
        row = CallReservation(id=rid, handler_id=handler.id, lead_id=lead.id,
                              phone=permit.phone, status="reserved", created_at=now)
        db.add(row)
        try:
            db.flush()
            db.add(CallLeadHold(lead_id=lead.id, reservation_id=rid))
            db.commit()
        except IntegrityError:
            db.rollback()  # another worker owns this lead; do NOT call
            return None
        return row
    db.rollback()  # release read locks before returning
    return None


def release(db, row, result):
    row.status, row.result = "terminal", result
    db.execute(update(CallHandler).where(CallHandler.id == row.handler_id,
        CallHandler.reservation_id == row.id).values(reservation_id=None))
    db.execute(delete(CallLeadHold).where(CallLeadHold.reservation_id == row.id))


def provider_result(db, rid, sid, error):
    row = db.scalar(select(CallReservation).where(CallReservation.id == rid).with_for_update())
    if not row or row.status == "terminal":
        return
    if sid:
        if row.provider_id and row.provider_id != sid:
            row.status = "uncertain"
        else:
            row.provider_id, row.status = sid, "in_flight"
    elif getattr(error, "kind", None) == "not_attempted":
        release(db, row, "not_attempted")
    else:
        row.status = "uncertain"  # no automatic expiry/retry/release
    db.commit()


def callback(db, rid, sid, status):
    row = db.scalar(select(CallReservation).where(CallReservation.id == rid).with_for_update())
    if not row or not sid or (row.provider_id and row.provider_id != sid):
        return False
    if row.status == "terminal":
        return row.provider_id == sid
    row.provider_id = sid  # signed callback can arrive before HTTP submit returns
    if status in TERMINAL:
        release(db, row, status)
    elif row.status != "uncertain":
        row.status = "in_flight"
    db.commit()
    return True


def transfer_target(db, rid, sid, now=None):
    now = now or datetime.now(timezone.utc)
    row = db.get(CallReservation, rid)
    if not row or row.status == "terminal" or not callback(db, rid, sid, "answered"):
        return None
    handler, permit, lead = db.get(CallHandler, row.handler_id), db.get(CallPermit, row.lead_id), db.get(Lead, row.lead_id)
    if (not handler or handler.reservation_id != rid or utc(handler.verified_until) <= now
            or not handler.available_until or utc(handler.available_until) <= now
            or not permit or utc(permit.expires_at) <= now or permit.state not in handler.states
            or permit.phone != row.phone or not lead
            or compliance.is_dnc(db, phone=row.phone, email=lead.email)):
        return None
    return handler.phone


def recipient_in_window(zone, now=None):
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    try:
        hour = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo(zone)).hour
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        return False
    return 9 <= hour < 20


def dispatch(db, lead):
    """Opt-in scheduler path. Existing gates and outbound idempotency stay in place."""
    from .integrations import voice
    from .auto_dial import auto_dial_enabled
    if not settings.auto_dial_capacity_enabled or not auto_dial_enabled():
        return None, "capacity calling disabled"
    if control.is_paused_safe(db) or (control.get_mode(db) != "auto" and not control.outreach_autopilot(db)):
        return None, "outreach paused"
    if not sms_engine.in_call_window() or voice.active() != "twilio":
        return None, "calling window or supported provider unavailable"
    if not settings.secure_runtime:
        return None, "secure callback verification required"
    permit = db.get(CallPermit, lead.id)
    if not permit:
        return None, "reviewed calling permission and jurisdiction required"
    gate = compliance.gate(db, channel="call", phone=lead.phone, email=lead.email,
        state=permit.state, entity_type="lead", entity_id=lead.id, actor="capacity_calling")
    if not gate.allowed:
        return None, gate.reason
    if not recipient_in_window(permit.recipient_timezone):
        return None, "outside verified recipient local calling window"
    # Persist preceding pass results and this compliance decision before reserve
    # opens its own short transaction and commits capacity before external I/O.
    db.commit()
    row = reserve(db, lead)
    if not row:
        return None, "no verified available handler or current calling permission"
    try:
        result = voice.place_auto_call(lead.phone, str(lead.id), reservation_id=str(row.id))
        sid, error = result
    except Exception:
        provider_result(db, row.id, None, "provider outcome unknown")
        raise
    provider_result(db, row.id, sid, error)
    return sid, error
