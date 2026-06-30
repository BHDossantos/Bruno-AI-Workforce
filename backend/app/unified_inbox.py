"""Unified inbox — every prospect reply across all businesses in one feed.

Replies are captured by inbound.sync_replies (logged as ``reply_classified`` with
the AI intent + summary) and an AI reply is drafted for one-click send. This builds
the surface for them: each item has the sender, the business it belongs to, an
AI label (Interested / Question / Objection / Not interested / Unsubscribe), the
AI summary, and the drafted reply id so the user can approve/send in one click.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from .models import ActionLog, Lead, Message, Restaurant

# intent → human label.
LABELS = {
    "interested": "Interested", "question": "Question", "objection": "Objection",
    "not_interested": "Not interested", "unsubscribe": "Unsubscribe", "neutral": "Neutral",
}
_SEG_BIZ = {
    "commercial": "Insurance", "personal": "Insurance", "consulting": "BnB Global",
}


def _business_for(db: Session, sender: str) -> str:
    lead = db.query(Lead).filter(Lead.email == sender).first()
    if lead:
        return _SEG_BIZ.get(lead.segment or "", "Insurance")
    if db.query(Restaurant).filter(Restaurant.email == sender).first():
        return "SavoryMind"
    return "Other"


def feed(db: Session, business: str | None = None, label: str | None = None,
         limit: int = 100) -> dict:
    rows = (db.query(ActionLog)
            .filter(ActionLog.action == "reply_classified")
            .order_by(ActionLog.created_at.desc()).limit(400).all())
    items: list[dict] = []
    by_business: dict[str, int] = {}
    by_label: dict[str, int] = {}
    seen: set[str] = set()
    for r in rows:
        sender = r.entity_id
        if not sender or sender in seen:
            continue  # newest reply per sender only
        seen.add(sender)
        d = r.detail or {}
        intent = (d.get("intent") or "neutral").lower()
        lbl = LABELS.get(intent, "Neutral")
        biz = _business_for(db, sender)
        by_business[biz] = by_business.get(biz, 0) + 1
        by_label[lbl] = by_label.get(lbl, 0) + 1
        if business and biz != business:
            continue
        if label and lbl != label:
            continue
        draft = (db.query(Message)
                 .filter(Message.to_email == sender, Message.entity_type == "reply",
                         Message.status == "Drafted")
                 .order_by(Message.created_at.desc()).first())
        items.append({
            "sender": sender, "business": biz, "label": lbl, "intent": intent,
            "summary": d.get("summary"), "subject": d.get("subject"),
            "account": d.get("account"),
            "received_at": r.created_at.isoformat() if r.created_at else None,
            "draft_id": str(draft.id) if draft else None,
            "draft_body": draft.body if draft else None,
        })
    return {
        "items": items[:limit],
        "by_business": by_business,
        "by_label": by_label,
        "total": len(seen),
    }
