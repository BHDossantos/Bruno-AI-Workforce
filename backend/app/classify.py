"""AI classification of inbound replies (email + SMS).

Maps a free-text reply to an intent and a suggested lead status, so the dashboard
can surface the hottest conversations first. Degrades to "neutral" with no AI key.
"""
from __future__ import annotations

from .ai import client
from .ai.prompts import CLASSIFY_REPLY

# intent -> lead/restaurant status to apply
_STATUS = {
    "interested": "Interested",
    "question": "Interested",
    "objection": "Follow-up Needed",
    "not_interested": "Closed Lost",
    "unsubscribe": "Closed Lost",
    "neutral": "Replied",
}


def classify_reply(text: str) -> dict:
    """Return {intent, summary, suggested_reply, status}. Safe without an API key."""
    if not text:
        return {"intent": "neutral", "summary": "", "suggested_reply": "", "status": "Replied"}
    out = client.complete_json(CLASSIFY_REPLY.format(text=text[:1500]))
    intent = (out.get("intent") if isinstance(out, dict) else None) or "neutral"
    intent = intent if intent in _STATUS else "neutral"
    return {
        "intent": intent,
        "summary": (out.get("summary") if isinstance(out, dict) else "") or "",
        "suggested_reply": (out.get("suggested_reply") if isinstance(out, dict) else "") or "",
        "status": _STATUS[intent],
    }
