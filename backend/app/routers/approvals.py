"""Unified Approval Queue — one place to approve/reject everything the AI prepared.

Aggregates the items waiting on Bruno across businesses: content pieces awaiting
approval, drafted insurance/consulting leads, and drafted SavoryMind restaurant
pitches. Approve → it goes out (or gets scheduled); Reject → it's skipped. Keeps
the human in the loop without hunting through five different pages.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import outreach
from ..database import get_db
from ..models import ContentItem, Lead, Restaurant
from ..security import require_role

router = APIRouter(prefix="/approvals", tags=["approvals"])
_read = require_role("admin", "operator", "viewer")
_write = require_role("admin", "operator")


def _preview(text: str | None, n: int = 220) -> str:
    t = (text or "").strip().replace("\n", " ")
    return t[:n] + ("…" if len(t) > n else "")


@router.get("")
def list_approvals(limit: int = 100, db: Session = Depends(get_db), _=Depends(_read)):
    """Everything awaiting your approval, newest first, with a preview + risk."""
    items: list[dict] = []

    for c in (db.query(ContentItem).filter(ContentItem.status == "needs_approval")
              .order_by(ContentItem.created_at.desc()).limit(limit).all()):
        items.append({
            "type": "content", "id": str(c.id), "risk": "low",
            "title": f"{c.channel} post — {c.title or c.topic}",
            "business": c.business, "preview": _preview(c.body),
            "created_at": c.created_at.isoformat() if c.created_at else None,
        })

    for l in (db.query(Lead).filter(Lead.status == "Drafted", Lead.email.isnot(None))
              .order_by(Lead.created_at.desc()).limit(limit).all()):
        seg = "BnB Global" if l.segment == "consulting" else "Insurance"
        items.append({
            "type": "lead", "id": str(l.id), "risk": "medium",
            "title": f"{seg} email — {l.company_name or l.owner_name}",
            "business": l.segment, "preview": _preview(l.cold_email),
            "to": l.email, "created_at": l.created_at.isoformat() if l.created_at else None,
        })

    for r in (db.query(Restaurant).filter(Restaurant.kind == "prospect",
              Restaurant.status == "Drafted", Restaurant.email.isnot(None))
              .order_by(Restaurant.created_at.desc()).limit(limit).all()):
        items.append({
            "type": "restaurant", "id": str(r.id), "risk": "medium",
            "title": f"SavoryMind pitch — {r.name}",
            "business": "savorymind", "preview": _preview(r.pitch_email),
            "to": r.email, "created_at": r.created_at.isoformat() if r.created_at else None,
        })

    items.sort(key=lambda i: i.get("created_at") or "", reverse=True)
    return {"count": len(items), "items": items}


@router.get("/count")
def count(db: Session = Depends(get_db), _=Depends(_read)):
    from sqlalchemy import func
    n = (db.query(func.count()).select_from(ContentItem)
         .filter(ContentItem.status == "needs_approval").scalar() or 0)
    n += (db.query(func.count()).select_from(Lead)
          .filter(Lead.status == "Drafted", Lead.email.isnot(None)).scalar() or 0)
    n += (db.query(func.count()).select_from(Restaurant)
          .filter(Restaurant.kind == "prospect", Restaurant.status == "Drafted",
                  Restaurant.email.isnot(None)).scalar() or 0)
    return {"pending": int(n)}


@router.post("/{item_type}/{item_id}/{action}")
def act(item_type: str, item_id: str, action: str,
        db: Session = Depends(get_db), _=Depends(_write)):
    """Approve (send/schedule) or reject (skip) one queued item."""
    if action not in ("approve", "reject"):
        raise HTTPException(400, "action must be approve or reject")

    if item_type == "content":
        c = db.query(ContentItem).filter(ContentItem.id == item_id).first()
        if not c:
            raise HTTPException(404, "content not found")
        c.status = "scheduled" if action == "approve" else "dismissed"
        if action == "approve":
            c.scheduled_for = datetime.now(timezone.utc)
        db.commit()
        return {"ok": True, "type": "content", "status": c.status}

    if item_type in ("lead", "restaurant"):
        if item_type == "lead":
            row = db.query(Lead).filter(Lead.id == item_id).first()
            if not row:
                raise HTTPException(404, "lead not found")
            account = "insurance" if row.segment in ("commercial", "personal") else "personal"
            subject = f"A quick idea for {row.company_name or row.owner_name}"
            body, etype = row.cold_email, "lead"
        else:
            row = db.query(Restaurant).filter(Restaurant.id == item_id).first()
            if not row:
                raise HTTPException(404, "restaurant not found")
            account, subject, body, etype = "personal", f"Growing revenue at {row.name} with SavoryMind", row.pitch_email, "restaurant"
        if action == "reject":
            row.status = "Skipped"
            db.commit()
            return {"ok": True, "type": item_type, "status": "Skipped"}
        msg = outreach.dispatch_email(db, entity_type=etype, entity_id=row.id,
                                      to_email=row.email, subject=subject, body=body,
                                      account=account, actor="approval")
        if msg.status == "Sent" and row.status in (None, "New", "Drafted"):
            row.status = "Sent"
        db.commit()
        return {"ok": True, "type": item_type, "status": msg.status}

    raise HTTPException(400, f"unknown item type '{item_type}'")
