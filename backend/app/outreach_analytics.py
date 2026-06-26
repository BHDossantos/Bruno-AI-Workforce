"""Outreach learn-and-act — learn which subject-line styles earn replies and
feed the winners back into future outreach so the system improves itself.

A reply is attributed when an inbound message exists for the same entity as a sent
outbound email. We classify each subject into a STYLE and compute reply rate per
style; `whats_working()` returns a prompt hint the outreach agents inject so new
emails favor the styles that actually get responses.
"""
from __future__ import annotations

import re

from sqlalchemy.orm import Session

from .models import Message

_MIN_SAMPLE = 8  # need at least this many sends in a style before trusting its rate


def subject_style(subject: str | None) -> str:
    """Coarse, deterministic style bucket for a subject line."""
    s = (subject or "").strip()
    if not s:
        return "none"
    if s.endswith("?") or s.lower().startswith(("how ", "what ", "why ", "can ", "is ")):
        return "question"
    if re.search(r"\d", s) or "%" in s:
        return "number/result"
    if len(s) <= 35:
        return "short/punchy"
    if any(w in s.lower() for w in ("idea", "quick", "thought")):
        return "curiosity"
    return "statement"


def reply_rates(db: Session) -> dict[str, dict]:
    """Per-style {sent, replied, rate}. A send 'replied' if its entity later
    produced an inbound message."""
    sent = (db.query(Message).filter(
        Message.channel == "email", Message.direction == "outbound",
        Message.status == "Sent", Message.subject.isnot(None)).all())
    # Entities that have replied (any inbound message).
    replied_entities = {e for (e,) in db.query(Message.entity_id).filter(
        Message.direction == "inbound", Message.entity_id.isnot(None)).all()}
    agg: dict[str, dict] = {}
    for m in sent:
        style = subject_style(m.subject)
        a = agg.setdefault(style, {"sent": 0, "replied": 0})
        a["sent"] += 1
        if m.entity_id in replied_entities:
            a["replied"] += 1
    for a in agg.values():
        a["rate"] = round(a["replied"] / a["sent"], 3) if a["sent"] else 0.0
    return agg


def whats_working(db: Session, top_n: int = 2) -> str:
    """Prompt hint naming the best-replying subject styles (with enough data)."""
    try:
        rates = reply_rates(db)
    except Exception:  # pragma: no cover - best-effort learning
        return ""
    ranked = sorted(
        [(st, a) for st, a in rates.items() if a["sent"] >= _MIN_SAMPLE and st != "none"],
        key=lambda x: x[1]["rate"], reverse=True)
    if not ranked:
        return ""
    winners = [f"{st} ({int(a['rate'] * 100)}% reply)" for st, a in ranked[:top_n] if a["rate"] > 0]
    if not winners:
        return ""
    return ("WHAT'S WORKING IN OUTREACH — these subject-line styles get the most "
            "replies; favor them: " + "; ".join(winners) + ".")
