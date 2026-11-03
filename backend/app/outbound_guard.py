"""Fail-closed provider reservations; independent transactions survive caller rollback.

Pending/unknown outcomes hold the recipient indefinitely, including across a restart
or a new operation key. They require provider reconciliation, never a timeout retry.
This provides at-most-one invocation per key, NOT exactly-once external delivery.
"""
from contextlib import contextmanager
from hashlib import sha256
import json

from sqlalchemy import delete, select, text, update, func
from sqlalchemy.dialects.postgresql import insert

from .database import engine
from .models import OutboundAttempt, OutboundHold


class RejectedDelivery(str):
    """Provider explicitly rejected before acceptance; safe to try another provider."""


class _Busy(Exception):
    pass


def digest(*parts) -> str:
    return sha256(json.dumps(parts, ensure_ascii=False, separators=(",", ":"),
                             sort_keys=True).encode()).hexdigest()


def invoke(channel, recipient, account, operation, payload, send, *, replay_accepted=True):
    """Return (provider_id, error). A replay never invokes `send` again.

    The callback must not retry or fail over after an ambiguous outcome. We store
    hashes, not recipients/bodies or raw provider errors. No caller transaction is
    committed here. DB errors before/after sending fail closed.
    """
    scope = digest(channel, (recipient or "").strip().lower(), account)
    key = digest(scope, operation)
    fingerprint = digest(payload)
    try:
        with engine.begin() as conn:
            inserted = conn.execute(insert(OutboundAttempt).values(
                key=key, scope=scope, payload_hash=fingerprint, channel=channel,
                state="pending").on_conflict_do_nothing().returning(OutboundAttempt.key)).scalar()
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
    except _Busy:
        return None, "Delivery held: another pending/unknown action exists for this recipient."
    except Exception:
        return None, "Delivery held: reservation database unavailable; no provider call made."

    try:
        provider_id, error = send()
        state = "accepted" if provider_id else ("rejected" if isinstance(error, RejectedDelivery) else "unknown")
    except Exception:
        provider_id, state = None, "unknown"
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
