"""Per-funnel newsletters.

Only WARM repliers are subscribed (CAN-SPAM friendly). Each funnel
(insurance / BnB Global / SavoryMind / music) has its own audience and its own
AI-written issue, sent 3×/week. Every send goes through outreach.dispatch_email
(daily cap + mailbox warmup) and carries a one-click unsubscribe link.
"""
from __future__ import annotations

import logging
import secrets

from sqlalchemy.orm import Session

from . import outreach
from .ai import client
from .config import settings
from .models import NewsletterSend, NewsletterSubscriber

log = logging.getLogger("bruno.newsletters")

FUNNELS = ["insurance", "bnbglobal", "savorymind", "music"]

# How each funnel's newsletter reads + which mailbox it sends from.
_FUNNEL = {
    "insurance": {"label": "Thrust Insurance", "account": "insurance",
                  "topic": "insurance tips, coverage gaps, and money-saving ideas for "
                           "homeowners and small businesses in NH/MA/FL"},
    "bnbglobal": {"label": "BnB Global", "account": "personal",
                  "topic": "practical cloud, reliability, security and AI wins for "
                           "growing tech teams"},
    "savorymind": {"label": "SavoryMind", "account": "personal",
                   "topic": "restaurant revenue, menu intelligence and review-to-revenue ideas"},
    "music": {"label": "Bruno D", "account": "personal",
              "topic": "new music, the stories behind the songs, shows, and where to listen"},
}


def funnel_for_segment(segment: str | None) -> str | None:
    if segment in ("commercial", "personal"):
        return "insurance"
    if segment == "consulting":
        return "bnbglobal"
    return None


def subscribe(db: Session, funnel: str, email: str | None, name: str | None = None) -> bool:
    """Add a warm reply to a funnel list (idempotent). Returns True if newly added."""
    if funnel not in _FUNNEL or not email:
        return False
    email = email.strip().lower()
    exists = (db.query(NewsletterSubscriber)
              .filter(NewsletterSubscriber.funnel == funnel,
                      NewsletterSubscriber.email == email).first())
    if exists:
        return False
    db.add(NewsletterSubscriber(funnel=funnel, email=email, name=name,
                                token=secrets.token_urlsafe(16)))
    db.flush()  # make this add visible to the next dedupe check in the same batch
    return True


def unsubscribe(db: Session, token: str) -> bool:
    row = db.query(NewsletterSubscriber).filter(NewsletterSubscriber.token == token).first()
    if not row:
        return False
    row.unsubscribed = True
    db.commit()
    return True


def _unsub_url(token: str) -> str:
    base = (settings.frontend_url or "").rstrip("/")
    return f"{base}/newsletters/unsubscribe?token={token}" if base \
        else f"/newsletters/unsubscribe?token={token}"


def _issue(funnel: str) -> tuple[str, str]:
    """AI-write this funnel's issue; fall back to a simple template offline."""
    cfg = _FUNNEL[funnel]
    if client.is_live():
        out = client.complete_json(
            f"Write this week's short email newsletter from {cfg['label']} about "
            f"{cfg['topic']}. Warm, useful, 120-180 words, one clear takeaway and a "
            f"soft CTA. No placeholders/signature. Return JSON {{\"subject\",\"body\"}}.",
            system="You output only valid JSON.")
        if isinstance(out, dict) and out.get("body"):
            return out.get("subject") or f"{cfg['label']} — this week", out["body"]
    return (f"{cfg['label']} — this week",
            f"Hi! A quick note from {cfg['label']} with the latest on {cfg['topic']}. "
            "Reply anytime — I read every message.")


def send_funnel(db: Session, funnel: str) -> dict:
    if funnel not in _FUNNEL:
        return {"funnel": funnel, "ok": False, "reason": "unknown funnel"}
    subs = (db.query(NewsletterSubscriber)
            .filter(NewsletterSubscriber.funnel == funnel,
                    NewsletterSubscriber.unsubscribed.is_(False)).all())
    if not subs:
        return {"funnel": funnel, "sent": 0, "subscribers": 0}
    subject, body = _issue(funnel)
    account = _FUNNEL[funnel]["account"]
    sent = 0
    for s in subs:
        full = f"{body}\n\n—\nUnsubscribe: {_unsub_url(s.token)}"
        try:
            msg = outreach.dispatch_email(db, entity_type="newsletter", entity_id=s.id,
                                          to_email=s.email, subject=subject, body=full,
                                          account=account, actor="newsletter")
            if msg.status in ("Sent", "Drafted"):
                sent += 1
        except Exception:
            log.debug("newsletter send failed for %s", s.email, exc_info=True)
    db.add(NewsletterSend(funnel=funnel, subject=subject, sent_count=sent))
    db.commit()
    return {"funnel": funnel, "sent": sent, "subscribers": len(subs)}


def run(db: Session) -> dict:
    """Send every funnel's newsletter (the 3×/week cron)."""
    return {"funnels": [send_funnel(db, f) for f in FUNNELS]}


def overview(db: Session) -> dict:
    from sqlalchemy import func
    out = []
    for f in FUNNELS:
        total = db.query(func.count()).select_from(NewsletterSubscriber).filter(
            NewsletterSubscriber.funnel == f).scalar() or 0
        active = db.query(func.count()).select_from(NewsletterSubscriber).filter(
            NewsletterSubscriber.funnel == f,
            NewsletterSubscriber.unsubscribed.is_(False)).scalar() or 0
        last = (db.query(NewsletterSend).filter(NewsletterSend.funnel == f)
                .order_by(NewsletterSend.created_at.desc()).first())
        out.append({"funnel": f, "label": _FUNNEL[f]["label"],
                    "subscribers": int(active), "total": int(total),
                    "unsubscribed": int(total) - int(active),
                    "last_sent": last.created_at.isoformat() if last else None,
                    "last_subject": last.subject if last else None})
    sends = (db.query(NewsletterSend).order_by(NewsletterSend.created_at.desc()).limit(20).all())
    history = [{"funnel": s.funnel, "subject": s.subject, "sent_count": s.sent_count,
                "created_at": s.created_at.isoformat() if s.created_at else None} for s in sends]
    return {"funnels": out, "history": history}
