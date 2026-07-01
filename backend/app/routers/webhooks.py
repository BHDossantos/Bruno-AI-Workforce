"""Outbound webhook subscriptions — n8n/Make/Zapier/anything-that-accepts-a-POST
integration. Manage which URLs get notified for which events; secrets are
write-only (never returned), consistent with every other credential in the app.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import webhooks as wh
from ..database import get_db
from ..models import Webhook
from ..security import require_role

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
_read = require_role("admin", "operator", "viewer")
_write = require_role("admin", "operator")


class WebhookIn(BaseModel):
    name: str
    url: str
    secret: str | None = None
    events: list[str] = []
    enabled: bool = True


def _dict(w: Webhook) -> dict:
    return {
        "id": str(w.id), "name": w.name, "url": w.url,
        "has_secret": bool(w.secret), "events": w.events or [],
        "enabled": w.enabled,
        "last_triggered_at": w.last_triggered_at.isoformat() if w.last_triggered_at else None,
        "last_status": w.last_status, "created_at": w.created_at.isoformat() if w.created_at else None,
    }


@router.get("/events")
def list_events(_=Depends(_read)):
    """The curated set of events a webhook can subscribe to."""
    return wh.EVENTS


@router.get("")
def list_webhooks(db: Session = Depends(get_db), _=Depends(_read)):
    return [_dict(w) for w in db.query(Webhook).order_by(Webhook.created_at.desc()).all()]


@router.post("")
def create_webhook(body: WebhookIn, db: Session = Depends(get_db), _=Depends(_write)):
    if not body.name.strip() or not body.url.strip():
        raise HTTPException(status_code=400, detail="Name and URL are required")
    if not body.url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="URL must start with http:// or https://")
    bad = [e for e in body.events if e != "*" and e not in wh.EVENT_KEYS]
    if bad:
        raise HTTPException(status_code=400, detail=f"Unknown event(s): {', '.join(bad)}")
    w = Webhook(name=body.name.strip(), url=body.url.strip(), secret=body.secret or None,
               events=body.events, enabled=body.enabled)
    db.add(w)
    db.commit()
    db.refresh(w)
    return _dict(w)


@router.patch("/{webhook_id}")
def update_webhook(webhook_id: str, body: WebhookIn, db: Session = Depends(get_db), _=Depends(_write)):
    w = db.query(Webhook).filter(Webhook.id == webhook_id).first()
    if not w:
        raise HTTPException(status_code=404, detail="Webhook not found")
    bad = [e for e in body.events if e != "*" and e not in wh.EVENT_KEYS]
    if bad:
        raise HTTPException(status_code=400, detail=f"Unknown event(s): {', '.join(bad)}")
    w.name, w.url, w.events, w.enabled = body.name.strip(), body.url.strip(), body.events, body.enabled
    if body.secret:  # write-only: only update if a new one is actually provided
        w.secret = body.secret
    db.commit()
    db.refresh(w)
    return _dict(w)


@router.delete("/{webhook_id}")
def delete_webhook(webhook_id: str, db: Session = Depends(get_db), _=Depends(_write)):
    w = db.query(Webhook).filter(Webhook.id == webhook_id).first()
    if not w:
        raise HTTPException(status_code=404, detail="Webhook not found")
    db.delete(w)
    db.commit()
    return {"deleted": webhook_id}


@router.post("/{webhook_id}/test")
def test_webhook(webhook_id: str, db: Session = Depends(get_db), _=Depends(_write)):
    """Fire a synthetic test event at this one webhook and report the result."""
    w = db.query(Webhook).filter(Webhook.id == webhook_id).first()
    if not w:
        raise HTTPException(status_code=404, detail="Webhook not found")
    payload = {"event": "webhook.test", "data": {"message": "Test event from Bruno AI Workforce"},
              "sent_at": datetime.now(timezone.utc).isoformat()}
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if w.secret:
        headers["X-Bruno-Signature"] = wh._sign(w.secret, body)
    try:
        r = httpx.post(w.url, content=body, headers=headers, timeout=8.0)
        w.last_status = str(r.status_code)
        ok = 200 <= r.status_code < 300
    except Exception as exc:  # pragma: no cover - network guard
        w.last_status = f"error: {str(exc)[:100]}"
        ok = False
    w.last_triggered_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": ok, "status": w.last_status}
