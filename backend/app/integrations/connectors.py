"""Runtime access to user-connected accounts (the Connections platform).

Lets the agents and engines act THROUGH a connected account: find an active
connection by provider, decrypt its stored credentials, and use them. Falls back
to environment settings where no connection exists, so the platform works whether
the user connects an account in the UI or sets an env var.
"""
from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

from ..models import Connection
from ..security import decrypt_secret

log = logging.getLogger("bruno.connectors")


def get_connection(db: Session | None, provider: str) -> Connection | None:
    """The most recent active, funnel-enabled connection for a provider."""
    if db is None:
        return None
    try:
        return (
            db.query(Connection)
            .filter(
                Connection.provider == provider,
                Connection.status == "connected",
                Connection.funnel_enabled.is_(True),
            )
            .order_by(Connection.created_at.desc())
            .first()
        )
    except Exception:  # pragma: no cover - defensive (e.g. table missing)
        return None


def get_credentials(db: Session | None, provider: str) -> dict | None:
    """Decrypted credential dict for a connected provider, or None."""
    conn = get_connection(db, provider)
    if not conn or not conn.credentials_enc:
        return None
    try:
        return json.loads(decrypt_secret(conn.credentials_enc))
    except Exception as exc:  # pragma: no cover - corrupted/rotated key
        log.warning("Could not decrypt credentials for %s: %s", provider, exc)
        return None


def is_connected(db: Session | None, provider: str) -> bool:
    return get_connection(db, provider) is not None


def update_credentials(db: Session, provider: str, creds: dict) -> bool:
    """Persist refreshed credentials (re-encrypted) for a provider's connection."""
    from ..security import encrypt_secret
    conn = get_connection(db, provider)
    if not conn:
        return False
    try:
        conn.credentials_enc = encrypt_secret(json.dumps(creds))
        db.commit()
        return True
    except Exception as exc:  # pragma: no cover
        log.warning("Could not update credentials for %s: %s", provider, exc)
        db.rollback()
        return False
