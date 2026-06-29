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
    """Everything awaiting your approval, highest-priority first, with a preview + risk."""
    from ..lead_fit import score as _lead_fit
    from ..lead_temperature import classify as _temp
    from ..restaurant_fit import score as _rest_fit
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
            "to": l.email, "temperature": _temp(l.status), "fit": _lead_fit(l),
            "created_at": l.created_at.isoformat() if l.created_at else None,
        })

    for r in (db.query(Restaurant).filter(Restaurant.kind == "prospect",
              Restaurant.status == "Drafted", Restaurant.email.isnot(None))
              .order_by(Restaurant.created_at.desc()).limit(limit).all()):
        items.append({
            "type": "restaurant", "id": str(r.id), "risk": "medium",
            "title": f"SavoryMind pitch — {r.name}",
            "business": "savorymind", "preview": _preview(r.pitch_email),
            "to": r.email, "temperature": _temp(r.status), "fit": _rest_fit(r),
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })

    # AI-drafted replies to inbound messages — approve to send.
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
    n += (db.query(func.count()).select_from(Message)
          .filter(Message.entity_type == "reply", Message.direction == "outbound",
                  Message.status == "Drafted", Message.to_email.isnot(None)).scalar() or 0)
    return {"pending": int(n)}


# ── Shared approve actions (reused by single-item act + bulk approve-all) ──────
def _send_reply(db: Session, m: Message) -> tuple[bool, str | None]:
    """Send a drafted reply in place. Never raises — returns (sent, note)."""
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
    return sent, note


def _outreach_fields(item_type: str, row) -> tuple[str, str, str | None, str]:
    """(account, subject, body, entity_type) for a lead/restaurant outreach send."""
    if item_type == "lead":
        account = "insurance" if row.segment in ("commercial", "personal") else "personal"
        return account, f"A quick idea for {row.company_name or row.owner_name}", row.cold_email, "lead"
    return "personal", f"Growing revenue at {row.name} with SavoryMind", row.pitch_email, "restaurant"


def _send_outreach(db: Session, item_type: str, row) -> tuple[bool, str | None]:
    """Send a drafted lead/restaurant email now. Never raises — returns (sent, note)."""
    account, subject, body, etype = _outreach_fields(item_type, row)
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
    # Only mark done when it actually sent — otherwise leave it Drafted so the
    # daily auto-outreach keeps pushing it out (deliverability cap pacing).
    if sent:
        row.status = "Sent"
    return sent, note


@router.post("/approve-all")
def approve_all(db: Session = Depends(get_db), _=Depends(_write)):
    """One-click: approve EVERYTHING in the queue and push it through.

    Content is scheduled, replies are sent, and outreach is sent up to today's
    deliverability cap — the rest stays queued and the daily auto-outreach drains
    it over the next days, so a big batch never gets the mailbox flagged as spam.
    Outreach Autopilot is switched on so that pacing happens automatically."""
    from .. import control
    now = datetime.now(timezone.utc)
    content_n = replies_sent = sent_now = queued = failed = 0

    # 1. Content → scheduled (publishes on its normal cadence).
    for c in db.query(ContentItem).filter(ContentItem.status == "needs_approval").all():
        c.status = "scheduled"
        c.scheduled_for = c.scheduled_for or now
        content_n += 1

    # 2. Replies to real humans → send now (small volume, highest priority).
    for m in db.query(Message).filter(
            Message.entity_type == "reply", Message.direction == "outbound",
            Message.status == "Drafted", Message.to_email.isnot(None)).all():
        ok, _note = _send_reply(db, m)
        replies_sent += 1 if ok else 0

    # 3. Outreach → send up to each mailbox's remaining daily cap; leave the rest
    #    Drafted for the daily auto-outreach to pace out (no mass Gmail drafts).
    control.set_outreach_autopilot(db, True)  # ensure the remainder keeps flowing
    cap_left: dict[str, int] = {}

    def _room(account: str) -> int:
        if account not in cap_left:
            cap_left[account] = max(0, outreach.effective_cap(db, account)
                                    - outreach.sent_today_count(db, account))
        return cap_left[account]

    leads = (db.query(Lead).filter(Lead.status == "Drafted", Lead.email.isnot(None))
             .order_by(Lead.score.desc()).all())
    rests = (db.query(Restaurant).filter(Restaurant.kind == "prospect",
             Restaurant.status == "Drafted", Restaurant.email.isnot(None)).all())
    for item_type, row in ([("lead", l) for l in leads] + [("restaurant", r) for r in rests]):
        account = _outreach_fields(item_type, row)[0]
        if _room(account) <= 0:
            queued += 1  # over today's cap — stays Drafted, auto-outreach sends it later
            continue
        ok, _note = _send_outreach(db, item_type, row)
        if ok:
            sent_now += 1
            cap_left[account] -= 1
        else:
            queued += 1  # not sent (kept Drafted) — will retry automatically

    db.commit()
    approved = content_n + replies_sent + sent_now + queued
    return {"ok": True, "approved": approved, "content_scheduled": content_n,
            "replies_sent": replies_sent, "outreach_sent_now": sent_now,
            "outreach_queued": queued, "failed": failed,
            "note": (f"Sent {sent_now + replies_sent} now; {queued} will send automatically "
                     "over the next days to protect deliverability." if queued else
                     "All approved items sent.")}


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
        sent, note = _send_reply(db, m)
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
        model = Lead if item_type == "lead" else Restaurant
        row = db.query(model).filter(model.id == item_id).first()
        if not row:
            raise HTTPException(404, f"{item_type} not found")
        if action == "reject":
            row.status = "Skipped"
            db.commit()
            return {"ok": True, "type": item_type, "status": "Skipped"}
        sent, note = _send_outreach(db, item_type, row)
        # Always leave the queue: "Sent" if it actually went, else "Approved".
        if not sent:
            row.status = "Approved"
        db.commit()
        return {"ok": True, "type": item_type, "status": row.status, "sent": sent, "note": note}

    raise HTTPException(400, f"unknown item type '{item_type}'")
