"""New Connection Setup — self-service, user-defined connections.

Generic CRUD over the ``custom_connections`` table so the owner can add an app by
NAMING it and defining its fields (no code change per provider). Organized by
category (social media, email, CRM, advertising, …). Secret field values are
encrypted at rest (Fernet) and never returned to the client — only whether a value
is set — so the page can show/edit a connection without ever re-exposing a token.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import CustomConnection
from ..security import decrypt_secret, encrypt_secret, require_role

router = APIRouter(tags=["custom-connections"])
_read = require_role("admin", "operator", "viewer")
_write = require_role("admin", "operator")

# The category tiles the UI groups connections under. Free-form on the backend
# (any string is accepted) but this is the canonical set the front end renders.
CATEGORIES = [
    {"key": "social_media", "label": "Social Media"},
    {"key": "content_blog", "label": "Content & Blog"},
    {"key": "email", "label": "Email"},
    {"key": "crm", "label": "CRM"},
    {"key": "advertising", "label": "Advertising"},
    {"key": "stores_payments", "label": "Stores & Payments"},
    {"key": "messaging", "label": "Messaging"},
    {"key": "scheduling", "label": "Scheduling"},
    {"key": "other", "label": "Other Apps"},
]


class FieldIn(BaseModel):
    label: str
    value: str | None = None
    secret: bool = False


class ConnectionIn(BaseModel):
    category: str
    name: str
    notes: str | None = None
    fields: list[FieldIn] = []


def _load_values(row: CustomConnection) -> dict:
    if not row.values_enc:
        return {}
    try:
        return json.loads(decrypt_secret(row.values_enc))
    except Exception:  # pragma: no cover - corrupt/rotated key
        return {}


def _serialize(row: CustomConnection) -> dict:
    """Public shape — secret values are NEVER returned, only whether they're set."""
    values = _load_values(row)
    fields = []
    for f in (row.fields or []):
        label, secret = f.get("label"), bool(f.get("secret"))
        val = values.get(label, "")
        fields.append({
            "label": label,
            "secret": secret,
            "value": "" if secret else val,   # never echo a secret back
            "has_value": bool(val),
        })
    return {
        "id": str(row.id),
        "category": row.category,
        "name": row.name,
        "notes": row.notes,
        "status": row.status,
        "fields": fields,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _apply(row: CustomConnection, body: ConnectionIn, existing: dict | None = None) -> None:
    """Write name/category/notes + field metadata, and (re)encrypt the values. On an
    EDIT, a blank secret value keeps the previously-stored secret (the client never
    receives it to re-submit), so renaming a connection can't wipe its token."""
    row.category = (body.category or "other").strip() or "other"
    row.name = (body.name or "").strip() or "Untitled"
    row.notes = (body.notes or None)
    prior = existing or {}
    meta, values = [], {}
    for f in body.fields:
        label = (f.label or "").strip()
        if not label:
            continue
        meta.append({"label": label, "secret": bool(f.secret)})
        val = f.value if f.value is not None else ""
        if f.secret and val == "" and label in prior:
            val = prior[label]          # keep the existing secret on edit
        values[label] = val
    row.fields = meta
    row.values_enc = encrypt_secret(json.dumps(values)) if values else None


@router.get("/custom-connections")
def list_connections(db: Session = Depends(get_db), _=Depends(_read)):
    rows = db.query(CustomConnection).order_by(CustomConnection.created_at.asc()).all()
    return {"categories": CATEGORIES, "connections": [_serialize(r) for r in rows]}


@router.post("/custom-connections")
def create_connection(body: ConnectionIn, db: Session = Depends(get_db), _=Depends(_write)):
    row = CustomConnection(category="other", name="Untitled", status="configured")
    _apply(row, body)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _serialize(row)


@router.put("/custom-connections/{conn_id}")
def update_connection(conn_id: str, body: ConnectionIn,
                      db: Session = Depends(get_db), _=Depends(_write)):
    row = db.get(CustomConnection, conn_id)
    if row is None:
        raise HTTPException(status_code=404, detail="connection not found")
    _apply(row, body, existing=_load_values(row))
    db.commit()
    db.refresh(row)
    return _serialize(row)


@router.delete("/custom-connections/{conn_id}")
def delete_connection(conn_id: str, db: Session = Depends(get_db), _=Depends(_write)):
    row = db.get(CustomConnection, conn_id)
    if row is not None:
        db.delete(row)
        db.commit()
    return {"ok": True}
