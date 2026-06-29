"""Unified Approval Queue — one place to approve/reject everything the AI prepared.

Aggregates the items waiting on Bruno across businesses: content pieces awaiting
approval, drafted insurance/consulting leads, and drafted SavoryMind restaurant
pitches. Approve → it goes out (or gets scheduled); Reject → it's skipped. Keeps
the human in the loop without hunting through five different pages.
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import outreach
from ..database import get_db
from ..models import ContentItem, Lead, Message, Restaurant
from ..security import require_role

router = APIRouter(prefix="/approvals", tags=["approvals"])
log = logging.getLogger("bruno.approvals")
_read = require_role("admin", "operator", "viewer")
_write = require_role("admin", "operator")


def _preview(text: str | None, n: int = 220) -> str:
    t = (text or "").strip().replace("\n", " ")
    return t[:n] + ("…" if len(t) > n else "")


_TEMP_WEIGHT = {"hot": 3000, "warm": 2000, "cold": 0, "dead": -1000}


def _priority(item: dict) -> int:
    """Rank what to 'hit send' on first: an engaged human waiting on a reply,
    then hot/warm prospects, then strongest cold ones; content sits below outreach."""
    if item["type"] == "reply":
        return 4000  # someone replied — answer them first
    return _TEMP_WEIGHT.get(item.get("temperature") or "cold", 0) + int(item.get("fit") or 0)


@router.get("")
def list_approvals(limit: int = 100, db: Session = Depends(get_db), _=Depends(_read)):
    """Everything awaiting YOUR approval, highest-priority first, with a preview + risk.

    When Outreach Autopilot is ON, cold lead/restaurant emails auto-send on their
    own (paced by the daily deliverability cap) — they are NOT shown here, because
    they don't need you. The queue then holds only what truly needs a human:
    content posts and replies. Synthetic/placeholder addresses that can never send
    are also filtered out so they don't clog the queue."""
    from .. import control
    from ..lead_fit import score as _lead_fit
    from ..lead_temperature import classify as _temp
    from ..restaurant_fit import score as _rest_fit
    auto = control.outreach_autopilot(db)
    items: list[dict] = []

    for c in (db.query(ContentItem).filter(ContentItem.status == "needs_approval")
              .order_by(ContentItem.created_at.desc()).limit(limit).all()):
        items.append({
            "type": "content", "id": str(c.id), "risk": "low",
            "title": f"{c.channel} post — {c.title or c.topic}",
            "business": c.business, "preview": _preview(c.body),
            "created_at": c.created_at.isoformat() if c.created_at else None,
        })

    if not auto:  # cold outreach only needs approval when autopilot is OFF
        for l in (db.query(Lead).filter(Lead.status == "Drafted", Lead.email.isnot(None))
                  .order_by(Lead.created_at.desc()).limit(limit * 3).all()):
            if not outreach.is_real_email(l.email):
                continue
            seg = "BnB Global" if l.segment == "consulting" else "Insurance"
            items.append({
                "type": "lead", "id": str(l.id), "risk": "medium",
                "title": f"{seg} email — {l.company_name or l.owner_name}",
                "business": l.segment, "preview": _preview(l.cold_email),
                "to": l.email, "temperature": _temp(l.status), "fit": _lead_fit(l),
                "created_at": l.created_at.isoformat() if l.created_at else None,
            })

        for r in (db.query(Restaurant).filter(Restaurant.kind == "prospect",
                  Restaurant.status == "Drafted", Restaurant.email.isnot(None))
                  .order_by(Restaurant.created_at.desc()).limit(limit * 3).all()):
            if not outreach.is_real_email(r.email):
                continue
            items.append({
                "type": "restaurant", "id": str(r.id), "risk": "medium",
                "title": f"SavoryMind pitch — {r.name}",
                "business": "savorymind", "preview": _preview(r.pitch_email),
                "to": r.email, "temperature": _temp(r.status), "fit": _rest_fit(r),
                "created_at": r.created_at.isoformat() if r.created_at else None,
            })

    # AI-drafted replies to inbound messages — always need you (approve to send).
    for m in (db.query(Message).filter(
            Message.entity_type == "reply", Message.direction == "outbound",
            Message.status == "Drafted", Message.to_email.isnot(None))
            .order_by(Message.created_at.desc()).limit(limit).all()):
        items.append({
            "type": "reply", "id": str(m.id), "risk": "low",
            "title": f"Reply to {m.to_email}", "business": None,
            "preview": _preview(m.body), "to": m.to_email,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        })

    # Highest-priority first (engaged replies → hot/warm → strongest cold), then newest.
    items.sort(key=lambda i: (_priority(i), i.get("created_at") or ""), reverse=True)
    return {"count": len(items), "items": items[:limit],
            "auto_sending": _auto_send_backlog(db) if auto else 0}


def _auto_send_backlog(db: Session) -> int:
    """Drafted cold outreach that Outreach Autopilot will send on its own (real
    addresses only) — shown as info, NOT as something awaiting the user."""
    from sqlalchemy import func
    leads = (db.query(func.count()).select_from(Lead)
             .filter(Lead.status == "Drafted", Lead.email.isnot(None)).scalar() or 0)
    rests = (db.query(func.count()).select_from(Restaurant)
             .filter(Restaurant.kind == "prospect", Restaurant.status == "Drafted",
                     Restaurant.email.isnot(None)).scalar() or 0)
    return int(leads + rests)


@router.get("/count")
def count(db: Session = Depends(get_db), _=Depends(_read)):
    from sqlalchemy import func

    from .. import control
    auto = control.outreach_autopilot(db)
    n = (db.query(func.count()).select_from(ContentItem)
         .filter(ContentItem.status == "needs_approval").scalar() or 0)
    n += (db.query(func.count()).select_from(Message)
          .filter(Message.entity_type == "reply", Message.direction == "outbound",
                  Message.status == "Drafted", Message.to_email.isnot(None)).scalar() or 0)
    if not auto:  # cold outreach only counts as "to approve" when autopilot is OFF
        n += (db.query(func.count()).select_from(Lead)
              .filter(Lead.status == "Drafted", Lead.email.isnot(None)).scalar() or 0)
        n += (db.query(func.count()).select_from(Restaurant)
              .filter(Restaurant.kind == "prospect", Restaurant.status == "Drafted",
                      Restaurant.email.isnot(None)).scalar() or 0)
    return {"pending": int(n), "auto_sending": _auto_send_backlog(db) if auto else 0}


@router.post("/{item_type}/{item_id}/{action}")
def act(item_type: str, item_id: str, action: str,
        db: Session = Depends(get_db), _=Depends(_write)):
    """Approve (send/schedule) or reject (skip) one queued item."""
    if action not in ("approve", "reject"):
        raise HTTPException(400, "action must be approve or reject")

    if item_type == "reply":
        m = db.query(Message).filter(Message.id == item_id).first()
        if not m:
            raise HTTPException(404, "reply not found")
        if action == "reject":
            m.status = "Skipped"
            db.commit()
            return {"ok": True, "type": "reply", "status": "Skipped"}
        # Send the drafted reply now (in place, no duplicate record). A send
        # failure must never 500 — mark it approved (kept) with a clear note.
        from .. import email_template
        from ..integrations import gmail
        sent = False
        note = "Marked approved — connect that Gmail mailbox to actually send."
        try:
            if gmail.is_configured(m.from_account):
                html = email_template.render(m.body or "", m.from_account)
                mid = gmail.send_message(m.to_email, m.subject or "", html or "", account=m.from_account)
                if mid:
                    m.provider_id = mid
                    m.sent_at = datetime.now(timezone.utc)
                    sent = True
                    note = None
        except Exception as exc:  # token expired / API error — don't lose the item
            log.warning("reply send failed: %s", exc)
            note = f"Approved, but sending failed ({str(exc)[:80]}). Reconnect Gmail and resend."
        m.status = "Sent" if sent else "Approved"
        m.approved = True
        db.commit()
        return {"ok": True, "type": "reply", "status": m.status, "sent": sent, "note": note}

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
        # Explicit approval → send now (autonomous=False bypasses semi-auto drafting).
        # A send failure must never 500 — mark it approved (kept) with a clear note.
        note = "Marked approved — connect a Gmail mailbox to actually send."
        sent = False
        try:
            msg = outreach.dispatch_email(db, entity_type=etype, entity_id=row.id,
                                          to_email=row.email, subject=subject, body=body,
                                          account=account, actor="approval", autonomous=False)
            sent = msg.status == "Sent"
            if sent:
                note = None
        except Exception as exc:  # token expired / API error — don't lose the item
            log.warning("%s send failed: %s", item_type, exc)
            note = f"Approved, but sending failed ({str(exc)[:80]}). Reconnect Gmail and resend."
        # Always leave the queue: "Sent" if it actually went, else "Approved"
        # so the same item never reappears.
        row.status = "Sent" if sent else "Approved"
        db.commit()
        return {"ok": True, "type": item_type, "status": row.status, "sent": sent, "note": note}

    raise HTTPException(400, f"unknown item type '{item_type}'")
