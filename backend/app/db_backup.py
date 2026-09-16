"""Portable database backup — a gzipped JSON snapshot of every table.

Host-independent (pure Python, no ``pg_dump`` binary or matching client version),
so a full copy of the data can be pulled on demand from ``GET /export/backup``
wherever the app runs. This is the manual / portable copy you keep yourself;
automatic daily snapshots come from the managed Postgres plan (see
docs/RENDER_DEPLOY.md). The snapshot includes EVERY table — encrypted credentials
included (they stay Fernet-encrypted), so a restore is complete — which is why the
download endpoint is admin-only.
"""
from __future__ import annotations

import base64
import datetime as _dt
import decimal
import gzip
import json
import uuid

from .database import Base, engine


def _default(o):
    """JSON-serialize the types SQLAlchemy hands back that json can't (UUID, dates,
    Decimal, bytes). JSONB columns already arrive as dict/list, so they pass through."""
    if isinstance(o, (_dt.datetime, _dt.date, _dt.time)):
        return o.isoformat()
    if isinstance(o, uuid.UUID):
        return str(o)
    if isinstance(o, decimal.Decimal):
        return float(o)
    if isinstance(o, (bytes, bytearray, memoryview)):
        return base64.b64encode(bytes(o)).decode()
    return str(o)


def snapshot() -> dict:
    """Every table -> list of row dicts, in FK-dependency order (safe to restore in
    sequence). Read over a single connection so it's a consistent point-in-time view."""
    tables: dict[str, list] = {}
    with engine.connect() as conn:
        for table in Base.metadata.sorted_tables:
            rows = conn.execute(table.select()).mappings().all()
            tables[table.name] = [dict(r) for r in rows]
    return {
        "version": 1,
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "tables": tables,
    }


def dump_gz() -> bytes:
    """Gzipped JSON of the whole database — the downloadable backup payload."""
    raw = json.dumps(snapshot(), default=_default).encode()
    return gzip.compress(raw)


def summary() -> dict[str, int]:
    """table -> row count, for a quick 'what's in the backup' view without downloading."""
    from sqlalchemy import func, select

    out: dict[str, int] = {}
    with engine.connect() as conn:
        for table in Base.metadata.sorted_tables:
            out[table.name] = conn.execute(
                select(func.count()).select_from(table)).scalar() or 0
    return out
