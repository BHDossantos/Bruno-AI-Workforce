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


# A/B exploration — the subject styles we deliberately rotate through so every
# style gets a fair sample and the learn-and-act loop converges fast (instead of
# only ever seeing whatever the model happened to write). Keys match subject_style.
_STYLE_DESC = {
    "question": "a curiosity-driven question (ends with ?)",
    "number/result": "led by a specific number, %, or concrete result",
    "short/punchy": "very short (≤ 35 characters) and punchy",
    "curiosity": "a curiosity teaser using a word like 'idea' or 'quick'",
    "statement": "a confident, specific one-line statement",
}
_STYLE_ORDER = ["question", "number/result", "short/punchy", "curiosity", "statement"]


def experiment_style(i: int) -> str:
    """Round-robin style for the i-th send in a batch → even A/B distribution."""
    return _STYLE_ORDER[i % len(_STYLE_ORDER)]


def experiment_hint(i: int) -> str:
    """Prompt hint assigning THIS email's subject style, for balanced exploration."""
    st = experiment_style(i)
    return (f"A/B TEST — for THIS email only, write the subject line as {_STYLE_DESC[st]}. "
            "Keep it specific and relevant, never generic. (We rotate styles to learn "
            "which earns the most replies.)")


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


def styles_report(db: Session) -> dict:
    """Full A/B view for the dashboard: every rotated subject style with its
    sent/replied/reply-rate, which styles have enough data to trust, and the
    current winner — so the self-optimizing outreach loop is visible, not a
    black box. Pure read; safe to call anywhere."""
    try:
        rates = reply_rates(db)
    except Exception:  # pragma: no cover - best-effort
        rates = {}
    styles = []
    for st in _STYLE_ORDER:
        a = rates.get(st) or {"sent": 0, "replied": 0, "rate": 0.0}
        styles.append({
            "style": st, "description": _STYLE_DESC[st],
            "sent": a["sent"], "replied": a["replied"], "rate": a["rate"],
            "enough_data": a["sent"] >= _MIN_SAMPLE,
        })
    ranked = sorted([s for s in styles if s["enough_data"] and s["rate"] > 0],
                    key=lambda s: s["rate"], reverse=True)
    return {
        "styles": styles, "min_sample": _MIN_SAMPLE,
        "best": ranked[0]["style"] if ranked else None,
        "total_sent": sum(s["sent"] for s in styles),
        "total_replied": sum(s["replied"] for s in styles),
    }


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
