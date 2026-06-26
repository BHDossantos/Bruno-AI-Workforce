"""Voice command interface — speak an order, the workforce acts.

The browser does speech-to-text (Web Speech API) and POSTs the transcript here.
We interpret the natural-language order into a SAFE, whitelisted action (run an
agent, source leads/grants, generate content, set mode, pause/resume, report
status, or navigate), execute it, and return a short spoken reply. Sending/posting
still respects semi-auto + Emergency Stop — voice runs agents (which DRAFT in semi
mode); it never blasts emails on its own.

Note: this recognizes SPEECH (what you say), not biometric voice identity; it's
behind your normal login.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import control
from ..agents import AGENTS
from ..ai import client
from ..database import get_db
from ..security import require_role

router = APIRouter(prefix="/voice", tags=["voice"])
log = logging.getLogger("bruno.voice")

# Spoken business/topic → agent key.
_AGENT_ALIASES = {
    "insurance": "insurance", "commercial": "commercial_finder", "business insurance": "commercial_finder",
    "homeowner": "homeowner", "home": "homeowner", "auto": "homeowner",
    "referral": "referral_partner", "partner": "referral_partner",
    "consulting": "bnbglobal", "bnb": "bnbglobal", "b and b": "bnbglobal", "b&b": "bnbglobal",
    "savorymind": "savorymind", "savory": "savorymind", "restaurant": "savorymind", "restaurants": "savorymind",
    "grant": "grant_research", "grants": "grant_research", "funding": "grant_research",
    "foundation": "foundation_outreach", "donor": "foundation_outreach", "sponsor": "foundation_outreach",
    "school": "school_partner", "schools": "school_partner",
    "music": "music", "instagram": "instagram", "job": "job_hunter", "jobs": "job_hunter",
    "follow up": "follow_up_agent", "followup": "follow_up_agent", "follow-up": "follow_up_agent",
    "review": "review_referral",
}
_NAV = {
    "mission": "/", "home": "/", "approvals": "/approvals", "approval": "/approvals",
    "calendar": "/calendar", "content": "/calendar", "leads": "/insurance",
    "insurance": "/insurance", "foundation": "/foundation", "grants": "/foundation",
    "music": "/music", "savorymind": "/savorymind", "consulting": "/bnbglobal",
    "money": "/money", "pipeline": "/pipeline", "connections": "/connections",
}

_INTENT_PROMPT = """You route a spoken order for an AI marketing/sales workforce to ONE action.
Order: "{text}"

Return JSON {{"intent","target","mode","path","reply"}}:
- intent: one of run_agent | generate_content | run_all | pause | resume | set_mode | status | navigate | unknown
- target: for run_agent, the business/topic (e.g. "commercial", "grants", "music")
- mode: for set_mode, one of "semi" | "auto" | "manual"
- path: for navigate, where to go (e.g. "approvals", "calendar", "foundation")
- reply: a short, friendly spoken confirmation (one sentence)
Map "find/source/get X leads" or "run the X agent" to run_agent. "make/create content"
to generate_content. "run everything / daily cycle" to run_all. "pause/stop everything"
to pause; "resume" to resume. "switch to autopilot/semi/manual" to set_mode. "what's my
status / brief" to status. "open/show/go to X" to navigate. Anything unclear: unknown."""


class VoiceIn(BaseModel):
    text: str


def _match_alias(text: str, table: dict) -> str | None:
    t = (text or "").lower()
    for k, v in table.items():
        if k in t:
            return v
    return None


def _interpret(text: str) -> dict:
    """LLM intent parse with a keyword fallback so it works offline too."""
    if client.is_live():
        out = client.complete_json(_INTENT_PROMPT.format(text=text[:300]),
                                    system="You output only valid JSON.")
        if isinstance(out, dict) and out.get("intent"):
            return out
    t = text.lower()
    if any(w in t for w in ("pause", "stop everything", "emergency")):
        return {"intent": "pause", "reply": "Pausing all agents."}
    if "resume" in t:
        return {"intent": "resume", "reply": "Resuming agents."}
    if "autopilot" in t or "full auto" in t:
        return {"intent": "set_mode", "mode": "auto", "reply": "Switching to autopilot."}
    if "status" in t or "brief" in t:
        return {"intent": "status", "reply": "Here's your status."}
    agent = _match_alias(t, _AGENT_ALIASES)
    if agent:
        return {"intent": "run_agent", "target": text, "reply": "On it."}
    nav = _match_alias(t, _NAV)
    if nav:
        return {"intent": "navigate", "path": nav, "reply": "Opening it."}
    return {"intent": "unknown", "reply": "I didn't catch a clear order."}


@router.post("/command")
def command(body: VoiceIn, db: Session = Depends(get_db),
            _=Depends(require_role("admin", "operator"))):
    """Interpret a spoken order and act on it. Returns a spoken reply + optional nav."""
    text = (body.text or "").strip()
    if not text:
        return {"ok": False, "reply": "I didn't hear anything."}
    spec = _interpret(text)
    intent = spec.get("intent")
    reply = spec.get("reply") or "Done."

    try:
        if intent == "pause":
            control.set_paused(db, True)
            return {"ok": True, "intent": intent, "reply": "All agents paused."}
        if intent == "resume":
            control.set_paused(db, False)
            return {"ok": True, "intent": intent, "reply": "Agents resumed."}
        if intent == "set_mode":
            mode = control.set_mode(db, spec.get("mode") or "semi")
            return {"ok": True, "intent": intent, "reply": f"Automation set to {mode}."}
        if intent == "navigate":
            path = _NAV.get((spec.get("path") or "").lower().strip("/")) or spec.get("path") or "/"
            if not path.startswith("/"):
                path = "/" + path
            return {"ok": True, "intent": intent, "navigate": path, "reply": reply}
        if intent == "status":
            from .. import scoring
            b = scoring.brief(db, top_n=3)
            top = "; ".join(a["title"] for a in b.get("top_actions", [])[:3]) or "no open actions"
            return {"ok": True, "intent": intent,
                    "reply": f"Focus {b.get('focus_score', 0)} of 100. Today's top: {top}."}
        if intent == "generate_content":
            from .. import platform_loops
            res = platform_loops.run_all(db)
            return {"ok": True, "intent": intent,
                    "reply": f"Generated {res.get('made_total', 0)} pieces into the queue.", "navigate": "/calendar"}
        if intent == "run_all":
            from .. import commanders
            commanders.run_ceo(db)
            return {"ok": True, "intent": intent, "reply": "Ran the full daily cycle."}
        if intent == "run_agent":
            key = _match_alias((spec.get("target") or text), _AGENT_ALIASES)
            cls = AGENTS.get(key) if key else None
            if not cls:
                return {"ok": False, "intent": "unknown",
                        "reply": "I'm not sure which agent you meant."}
            result = cls(db).run()
            summary = result.get("summary") if isinstance(result, dict) else None
            return {"ok": True, "intent": intent, "agent": key,
                    "reply": summary or f"Ran the {key} agent."}
        return {"ok": False, "intent": "unknown",
                "reply": reply or "I didn't catch a clear order. Try 'source commercial leads' or 'find grants'."}
    except Exception as exc:  # pragma: no cover - voice must never 500
        log.exception("voice command failed")
        return {"ok": False, "intent": intent, "reply": f"That failed: {str(exc)[:120]}"}
