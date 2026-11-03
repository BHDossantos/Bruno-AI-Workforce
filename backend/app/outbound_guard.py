"""Fail-closed provider reservations; independent transactions survive caller rollback.

Pending/unknown outcomes hold the recipient indefinitely, including across a restart
or a new operation key. They require provider reconciliation, never a timeout retry.
This provides at-most-one invocation per key, NOT exactly-once external delivery.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from functools import wraps
from inspect import signature
from hashlib import sha256
import json

from sqlalchemy import delete, select, text, update, func
from sqlalchemy.dialects.postgresql import insert

from .database import engine
from .models import OutboundAttempt, OutboundHold, OutboundQuota, Message


class DeferredDelivery(str):
    """External worker owns the action; keep pending until its authenticated result."""


class RejectedDelivery(str):
    """Provider explicitly rejected before acceptance; safe to try another provider."""


_active = ContextVar("outbound_active", default=None)


class _Busy(Exception):
    pass


def digest(*parts) -> str:
    return sha256(json.dumps(parts, ensure_ascii=False, separators=(",", ":"),
                             sort_keys=True).encode()).hexdigest()


def recipient_scope(channel, recipient):
    value = (recipient or "").strip().lower()
    if channel in ("sms", "whatsapp", "auto-call", "call"):
        from .integrations.sms import _e164
        value = _e164(value.removeprefix("whatsapp:"))
    family = "sms" if channel == "whatsapp" else "call" if channel == "auto-call" else channel
    return digest(family, value)


def quota_limit(channel):
    from .config import settings
    if channel == "email":
        from .outreach import daily_send_cap
        return daily_send_cap()
    if channel in ("sms", "whatsapp"):
        return settings.sms_daily_send_cap
    if channel in ("auto-call", "call"):
        return min(settings.call_daily_cap, settings.auto_dial_daily_cap)
    return None


def provider(channel, *, result="tuple", recipient="to", ready=None, validate=None):
    """Guard public transport entry points, sharing a caller's matching reservation.

    Optional operation_key/replay_accepted keywords are consumed by this wrapper.
    Direct legacy calls use permanent content identity and do not replay success.
    """
    def decorate(fn):
        sig = signature(fn)
        @wraps(fn)
        def wrapped(*args, **kwargs):
            operation = kwargs.pop("operation_key", None)
            replay = kwargs.pop("replay_accepted", False)
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            values = bound.arguments
            target = recipient(values) if callable(recipient) else values.get(recipient)
            def refused(reason):
                return (None, reason) if result == "tuple" else False if result == "bool" else None
            if validate:
                reason = validate(values)
                if reason:
                    return refused(reason)
            if not target:
                return refused("No recipient configured")
            if channel in ("sms", "whatsapp", "call", "auto-call"):
                from .integrations.sms import _e164
                if not _e164(target.removeprefix("whatsapp:")):
                    return refused("Invalid recipient number; no provider call made")
            if ready and not ready(values):
                return refused("Provider not connected; no provider call made")
            scope = recipient_scope(channel, target)
            if _active.get() == scope:
                return fn(*args, **kwargs)
            account = values.get("account", "direct")
            payload = {k: v for k, v in values.items() if k != recipient}
            if channel == "call":
                payload["purpose"] = fn.__name__
                operation = operation or digest(str(datetime.now(timezone.utc).date()), payload)
            if channel == "auto-call":
                from .integrations.sms import _e164
                account = "voice"
                operation = str(datetime.now(timezone.utc).date())
                payload = [_e164(target).lstrip("+")]
            def send():
                value = fn(*args, **kwargs)
                if result == "tuple":
                    return value
                # SMTP exposes acceptance without a provider receipt; store a local
                # acceptance reference, not a fabricated carrier receipt.
                return ("local-acceptance:" + digest(scope, payload) if result == "bool" and value else value or None), None
            receipt, error = invoke(channel, target, account,
                                    operation or digest(payload), payload, send,
                                    replay_accepted=replay)
            if result == "tuple":
                return receipt, error
            return bool(receipt) if result == "bool" else receipt
        return wrapped
    return decorate


def invoke(channel, recipient, account, operation, payload, send, *, replay_accepted=True, budget=None):
    """Return (provider_id, error). A replay never invokes `send` again.

    The callback must not retry or fail over after an ambiguous outcome. We store
    recipient/account for reconciliation and payload hashes, never bodies or raw
    provider errors. No caller transaction is committed here. DB errors before/after sending fail closed.
    """
    scope = recipient_scope(channel, recipient)
    key = digest(scope, account, operation)
    fingerprint = digest(payload)
    try:
        with engine.begin() as conn:
            inserted = conn.execute(insert(OutboundAttempt).values(
                key=key, scope=scope, payload_hash=fingerprint, channel=channel,
                state="pending", recipient=(recipient or "").strip(), account=account,
                operation_ref=operation if str(operation).startswith("message:") else None
            ).on_conflict_do_nothing().returning(OutboundAttempt.key)).scalar()
            if not inserted:
                row = conn.execute(select(OutboundAttempt.__table__).where(
                    OutboundAttempt.key == key)).mappings().one()
                if row["payload_hash"] != fingerprint:
                    return None, f"Delivery held: operation payload changed ({key})."
                if row["state"] == "accepted" and replay_accepted:
                    return row["provider_id"], None
                return None, f"Delivery held: {row['state']}; reconcile attempt {key} before retrying."
            claimed = conn.execute(insert(OutboundHold).values(scope=scope, attempt_key=key)
                                   .on_conflict_do_nothing().returning(OutboundHold.scope)).scalar()
            if not claimed:
                raise _Busy()
            limit = quota_limit(channel) if budget is None else budget
            if limit is not None:
                # Messaging and all calls share their channel family budget across
                # accounts/providers/processes. Count attempts, not reported success.
                family = "sms" if channel == "whatsapp" else "call" if channel == "auto-call" else channel
                quota_key = digest(family, str(datetime.now(timezone.utc).date()))
                start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
                channels = ["sms", "whatsapp"] if family == "sms" else [family]
                historical = conn.execute(select(func.count()).select_from(Message).where(
                    Message.direction == "outbound", Message.channel.in_(channels),
                    Message.sent_at >= start)).scalar() or 0
                conn.execute(insert(OutboundQuota).values(key=quota_key, used=historical,
                             capacity=max(0, limit)).on_conflict_do_nothing())
                # Never let a stale worker raise a lower cap already observed today.
                conn.execute(update(OutboundQuota).where(OutboundQuota.key == quota_key).values(
                    capacity=func.least(OutboundQuota.capacity, max(0, limit))))
                reserved = conn.execute(update(OutboundQuota).where(
                    OutboundQuota.key == quota_key, OutboundQuota.used < OutboundQuota.capacity
                ).values(used=OutboundQuota.used + 1).returning(OutboundQuota.key)).scalar()
                if not reserved:
                    # Commit the observed lower capacity even when this request is
                    # denied; roll back only its unused intent and recipient claim.
                    conn.execute(delete(OutboundHold).where(OutboundHold.scope == scope,
                                                            OutboundHold.attempt_key == key))
                    conn.execute(delete(OutboundAttempt).where(OutboundAttempt.key == key))
                    return None, "Delivery held: shared daily attempt budget exhausted; no provider call made."
    except _Busy:
        return None, "Delivery held: another pending/unknown action exists for this recipient."
    except Exception:
        return None, "Delivery held: reservation database unavailable; no provider call made."

    token = _active.set(scope)
    try:
        provider_id, error = send()
        if provider_id:
            state = "accepted"
        elif isinstance(error, DeferredDelivery):
            state = "pending"
        elif isinstance(error, RejectedDelivery):
            state = "rejected"
        else:
            state = "unknown"
    except Exception:
        provider_id, state = None, "unknown"
    finally:
        _active.reset(token)
    try:
        with engine.begin() as conn:
            conn.execute(update(OutboundAttempt).where(OutboundAttempt.key == key).values(
                state=state, provider_id=provider_id, updated_at=func.now()))
            if state in ("accepted", "rejected"):
                conn.execute(delete(OutboundHold).where(OutboundHold.scope == scope,
                                                        OutboundHold.attempt_key == key))
    except Exception:
        # The provider may have accepted. Keep the committed pending reservation;
        # never return an ordinary retryable failure or attempt a second provider.
        return None, f"Delivery held: provider result could not be recorded; reconcile attempt {key}."
    if provider_id:
        return provider_id, None
    return None, f"Delivery held: {state}; reconcile attempt {key} before retrying."


@contextmanager
def scheduler_slot():
    """Serialize scheduled work across instances on a dedicated PG connection.

    Not a fencing guarantee after connection loss; provider reservations are the
    second line of protection. No lease expiry can steal a still-running job.
    """
    with engine.connect() as conn:
        acquired = conn.execute(text("SELECT pg_try_advisory_lock(741920316)")).scalar()
        conn.commit()
        try:
            yield bool(acquired)
        finally:
            if acquired:
                try:
                    conn.execute(text("SELECT pg_advisory_unlock(741920316)"))
                    conn.commit()
                except Exception:
                    conn.invalidate()  # never return a locked connection to the pool
