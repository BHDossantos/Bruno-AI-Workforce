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
import re

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

Return JSON {{"intent","target","mode","path","topic","channel","business","company","when","reply"}}:
- intent: one of run_agent | generate_content | write_content | draft_outreach | schedule |
  what_failed | approve_safe | metrics | run_all | pause | resume | set_mode | status |
  navigate | unknown
- company: for draft_outreach, the company/person to reach out to
- when: for schedule, the natural-language time (e.g. "tomorrow at 9", "today 3pm")
- target: for run_agent, the business/topic (e.g. "commercial", "grants", "music")
- mode: for set_mode, one of "semi" | "auto" | "manual"
- path: for navigate, where to go (e.g. "approvals", "calendar", "foundation")
- topic: for write_content, the subject to write about
- channel: for write_content, one of linkedin | instagram | facebook | blog | x (default linkedin)
- business: for write_content, one of executive | bnbglobal | insurance | savorymind | music | foundation
- reply: a short, friendly spoken confirmation (one sentence)
Mapping: "find/source/get X leads" or "run the X agent" -> run_agent. "make/create today's
content" -> generate_content. "write a <channel> post about <topic>" -> write_content.
"approve everything safe / approve all content" -> approve_safe. "draft outreach to <company>"
-> draft_outreach. "schedule this for <time>" -> schedule. "what failed today / any errors"
-> what_failed. "how many leads today / what's the pipeline / numbers" -> metrics.
"run everything / daily cycle" -> run_all.
"pause/stop everything" -> pause; "resume" -> resume. "switch to autopilot/semi/manual"
-> set_mode. "status / brief" -> status. "open/show/go to X" -> navigate. Unclear -> unknown."""


class VoiceIn(BaseModel):
    text: str


def _parse_when(text: str):
    """Best-effort natural-language time → UTC datetime. Defaults to 9am, today
    unless 'tomorrow' is said."""
    from datetime import datetime, time, timedelta, timezone
    t = (text or "").lower()
    day = datetime.now(timezone.utc).date()
    if "tomorrow" in t:
        day = day + timedelta(days=1)
    hour = 9
    m = re.search(r"(\d{1,2})\s*(am|pm)?", t)
    if m:
        hour = int(m.group(1))
        if m.group(2) == "pm" and hour < 12:
            hour += 12
        if m.group(2) == "am" and hour == 12:
            hour = 0
    hour = max(0, min(23, hour))
    return datetime.combine(day, time(hour=hour), tzinfo=timezone.utc)


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
    if "approve" in t and ("safe" in t or "all" in t or "everything" in t):
        return {"intent": "approve_safe", "reply": "Approving the safe items."}
    if any(w in t for w in ("how many", "pipeline", "numbers", "metrics", "how much")):
        return {"intent": "metrics", "reply": "Here are your numbers."}
    if t.startswith("write ") or "write a" in t or "post about" in t:
        return {"intent": "write_content", "topic": text, "reply": "Writing it now."}
    if "draft outreach" in t or "reach out to" in t or "draft an email to" in t:
        m = re.search(r"(?:outreach to|reach out to|email to)\s+(.+)$", text, re.I)
        return {"intent": "draft_outreach", "company": (m.group(1).strip() if m else ""),
                "reply": "Drafting that outreach."}
    if t.startswith("schedule") or "schedule this" in t:
        return {"intent": "schedule", "when": text, "reply": "Scheduling it."}
    if "what failed" in t or "any errors" in t or "what broke" in t:
        return {"intent": "what_failed", "reply": "Checking what failed."}
    if "work the pipeline" in t or "work my pipeline" in t or "fill the pipeline" in t:
        return {"intent": "work_pipeline", "reply": "Working the pipeline now."}
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
        if intent == "write_content":
            from .. import content_factory
            topic = (spec.get("topic") or text).strip()
            for w in ("write", "a ", "post", "about", "linkedin", "instagram", "facebook", "blog", "tweet", "jarvis"):
                topic = re.sub(rf"\b{w}\b", "", topic, flags=re.I)
            topic = topic.strip(" ,.-") or "an update"
            channel = (spec.get("channel") or "linkedin").lower()
            channel = channel if channel in ("linkedin", "instagram", "facebook", "blog", "x") else "linkedin"
            business = (spec.get("business") or "executive").lower()
            res = content_factory.generate_pack(db, topic, business, channels=[channel])
            ok = res.get("ok")
            return {"ok": bool(ok), "intent": intent,
                    "reply": (f"Drafted a {channel} post about {topic}; it's in the queue."
                              if ok else f"Couldn't write it: {res.get('reason', 'try again')}."),
                    "navigate": "/calendar" if ok else None}
        if intent == "approve_safe":
            # Approve low-risk items only: content awaiting approval.
            from datetime import datetime, timezone

            from ..models import ContentItem
            items = db.query(ContentItem).filter(ContentItem.status == "needs_approval").all()
            now = datetime.now(timezone.utc)
            for it in items:
                it.status = "scheduled"
                it.scheduled_for = it.scheduled_for or now
            db.commit()
            return {"ok": True, "intent": intent,
                    "reply": f"Approved {len(items)} content piece(s) — they'll publish on schedule."}
        if intent == "metrics":
            from datetime import date, datetime, timezone

            from .. import scoring
            from ..models import Lead, Message
            start = datetime.combine(date.today(), datetime.min.time(), tzinfo=timezone.utc)
            actions = scoring.build_actions(db)
            pipeline = round(sum(a["value"] * a["probability"] for a in actions))
            leads_today = db.query(Lead).filter(Lead.created_at >= start).count()
            replies = db.query(Message).filter(Message.direction == "inbound",
                                                Message.created_at >= start).count()
            return {"ok": True, "intent": intent,
                    "reply": f"Pipeline is about ${pipeline:,}. {leads_today} new leads today, "
                             f"{replies} replies in."}
        if intent == "draft_outreach":
            company = (spec.get("company") or "").strip(" .,")
            if not company:
                return {"ok": False, "intent": intent, "reply": "Who should I reach out to?"}
            from ..ai import skills
            from ..ai.prompts import CANDIDATE_PROFILE, CONSULTING_OUTREACH
            from ..models import Lead
            lead = Lead(segment="consulting", category="Business", company_name=company,
                        status="New", reason="Voice-requested outreach.")
            db.add(lead)
            db.flush()
            art = client.complete_json(
                CONSULTING_OUTREACH.format(profile=CANDIDATE_PROFILE, company_name=company,
                                           category="", industry="", city=""),
                system=skills.system_prompt("cold-email", "marketing-psychology", "offers")) \
                if client.is_live() else {}
            art = art if isinstance(art, dict) else {}
            lead.cold_email = art.get("cold_email_body")
            lead.linkedin_msg = art.get("linkedin_msg")
            lead.status = "Drafted"
            db.commit()
            return {"ok": True, "intent": intent, "navigate": "/approvals",
                    "reply": f"Drafted outreach to {company}; it's in the Approval Queue to send."}
        if intent == "schedule":
            from ..models import ContentItem
            when = _parse_when(spec.get("when") or text)
            item = (db.query(ContentItem)
                    .filter(ContentItem.status.in_(["needs_approval", "ready", "generated", "scheduled"]))
                    .order_by(ContentItem.created_at.desc()).first())
            if not item:
                return {"ok": False, "intent": intent, "reply": "There's no draft to schedule yet."}
            item.scheduled_for = when
            item.status = "scheduled"
            db.commit()
            return {"ok": True, "intent": intent, "navigate": "/calendar",
                    "reply": f"Scheduled “{item.title or item.topic}” for {when.strftime('%a %b %d, %I %p')}."}
        if intent == "what_failed":
            from datetime import date, datetime, timezone

            from ..models import ActionLog, Task
            start = datetime.combine(date.today(), datetime.min.time(), tzinfo=timezone.utc)
            failed = db.query(Task).filter(Task.status == "error",
                                           Task.started_at >= start).count()
            errs = db.query(ActionLog).filter(ActionLog.action == "run_error",
                                              ActionLog.created_at >= start).count()
            n = max(failed, errs)
            return {"ok": True, "intent": intent,
                    "reply": (f"{n} agent run(s) failed today — check Agent Performance."
                              if n else "Nothing failed today. All clear.")}
        if intent == "run_all":
            from .. import commanders
            commanders.run_ceo(db)
            return {"ok": True, "intent": intent, "reply": "Ran the full daily cycle."}
        if intent == "work_pipeline":
            from .. import pipeline_run
            res = pipeline_run.work_pipeline(db)
            return {"ok": res.get("ok", True), "intent": intent,
                    "reply": res.get("summary", "Worked the pipeline."), "navigate": "/approvals"}
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
