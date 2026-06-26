"""Scoring engine — turns the current state of the business into a single,
ranked list of actions, so the Daily Brief can show only the highest-leverage
few. One formula across every domain makes a VP role and an insurance lead
comparable:

    priority = (value * probability / effort) * objective_weight * urgency
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from . import objectives
from .models import (ActionState, Application, Contact, ContentItem,
                     InstagramTarget, Job, Lead, Message, Opportunity, Restaurant)

# Expected-value assumptions (tune freely; these are sensible defaults).
_COMMERCIAL_VALUE = 5_000      # avg commercial insurance commission
_PERSONAL_VALUE = 1_500
_CONSULTING_VALUE = 20_000     # avg BnB Global tech-consulting engagement
_RESTAURANT_ARR = 12_000       # SavoryMind annual contract
_DEFAULT_SALARY = 275_000      # when a job posting hides salary
_WARM_PROB = {"Interested": 0.5, "Replied": 0.35, "Follow-up Needed": 0.3}
_DONE = {"Closed Won", "Closed Lost"}


def _score(value: float, prob: float, effort: int, weight: float, urgency: float) -> float:
    return round((value * prob / max(1, effort)) * weight * urgency, 1)


def build_actions(db: Session) -> list[dict]:
    """All open, scored actions, highest priority first."""
    w = objectives.weights(db)
    actions: list[dict] = []

    # ── Wealth · executive job applications (apply queue) ─────────────────────
    handled = {a.job_id for a in db.query(Application)
               .filter(Application.status.in_(["Applied", "Skipped", "Sent"])).all()}
    for j in db.query(Job).order_by(Job.score.desc()).limit(40):
        if j.id in handled:
            continue
        value = float(j.salary_min or _DEFAULT_SALARY)
        prob = min(0.9, (j.score or 60) / 100)
        actions.append({
            "key": f"apply:{j.id}",
            "title": f"Apply: {j.title} @ {j.company}",
            "command_center": "wealth", "objective": "exec_role", "action_type": "apply",
            "value": value, "probability": round(prob, 2), "effort": 2,
            "priority": _score(value, prob, 2, w.get("exec_role", 1.0), 1.0),
            "link": j.url or "/apply", "why": f"${round(value/1000)}k role · fit {j.score}",
        })

    # ── Warm leads to follow up — insurance (Wealth) + BnB Global (consulting) ─
    for l in (db.query(Lead).filter(Lead.status.in_(list(_WARM_PROB))).limit(80)):
        prob = _WARM_PROB.get(l.status, 0.3)
        if l.segment == "consulting":
            value = _CONSULTING_VALUE
            actions.append({
                "key": f"follow_up:lead:{l.id}",
                "title": f"BnB Global follow-up: {l.company_name or l.owner_name}",
                "command_center": "business", "objective": "consulting", "action_type": "follow_up",
                "value": float(value), "probability": prob, "effort": 2,
                "priority": _score(value, prob, 2, w.get("consulting", 0.6), 1.3),
                "link": "/bnbglobal", "why": f"{l.status} · ~${value} consulting engagement",
            })
            continue
        value = _COMMERCIAL_VALUE if l.segment == "commercial" else _PERSONAL_VALUE
        actions.append({
            "key": f"follow_up:lead:{l.id}",
            "title": f"Follow up: {l.company_name or l.owner_name}",
            "command_center": "wealth", "objective": "insurance", "action_type": "follow_up",
            "value": float(value), "probability": prob, "effort": 2,
            "priority": _score(value, prob, 2, w.get("insurance", 0.8), 1.2),
            "link": "/insurance", "why": f"{l.status} · ~${value} commission",
        })

    # ── Business · warm SavoryMind restaurants ───────────────────────────────
    for r in (db.query(Restaurant)
              .filter(Restaurant.kind == "prospect",
                      Restaurant.status.in_(["Replied", "Interested"])).limit(40)):
        prob = 0.4 if r.status == "Interested" else 0.3
        actions.append({
            "key": f"follow_up:restaurant:{r.id}",
            "title": f"Advance SavoryMind demo: {r.name}",
            "command_center": "business", "objective": "savorymind", "action_type": "follow_up",
            "value": float(_RESTAURANT_ARR), "probability": prob, "effort": 3,
            "priority": _score(_RESTAURANT_ARR, prob, 3, w.get("savorymind", 0.5), 1.1),
            "link": "/savorymind", "why": f"{r.status} · ~${_RESTAURANT_ARR} ARR",
        })

    # ── Replied-by-text leads waiting on you (fast, high urgency) ─────────────
    for phone in _unanswered_sms(db):
        actions.append({
            "key": f"reply:{phone}",
            "title": f"Reply to text from {phone}",
            "command_center": "wealth", "objective": "insurance", "action_type": "reply",
            "value": 3_000.0, "probability": 0.6, "effort": 1,
            "priority": _score(3_000, 0.6, 1, w.get("insurance", 0.8), 1.6),
            "link": "/texts", "why": "Warm — replied to your text",
        })

    # ── Influence · Instagram engagement + queued music content ───────────────
    for t in (db.query(InstagramTarget)
              .filter(InstagramTarget.status.in_(["New", "Drafted"])).limit(25)):
        actions.append({
            "key": f"engage:ig:{t.id}",
            "title": f"Engage @{t.handle}",
            "command_center": "influence", "objective": "music", "action_type": "engage",
            "value": 300.0, "probability": 0.2, "effort": 1,
            "priority": _score(300, 0.2, 1, w.get("music", 0.25), 1.0),
            "link": "/instagram", "why": f"{t.category or 'target'} · grow audience",
        })
    for it in (db.query(ContentItem)
               .filter(ContentItem.business == "music",
                       ContentItem.status.in_(["scheduled", "needs_approval", "ready", "generated"]))
               .order_by(ContentItem.created_at.desc()).limit(20)):
        actions.append({
            "key": f"music_content:{it.id}",
            "title": f"Music post: {it.title or it.topic}",
            "command_center": "influence", "objective": "music", "action_type": "content",
            "value": 250.0, "probability": 0.3, "effort": 1,
            "priority": _score(250, 0.3, 1, w.get("music", 0.25), 1.1),
            "link": "/calendar", "why": f"{it.channel} · drives streams + audience",
        })

    # ── Universal opportunities — investors, podcasts, collabs, speaking, etc. ─
    for o in db.query(Opportunity).filter(Opportunity.status == "Open").limit(100):
        value = float(o.value or 0)
        prob = float(o.probability if o.probability is not None else 0.3)
        effort = int(o.effort or 2)
        urgency = float(o.urgency if o.urgency is not None else 1.0)
        weight = w.get(o.objective or "", 0.6)
        actions.append({
            "key": f"opportunity:{o.id}",
            "title": f"{(o.kind or 'opportunity').replace('_', ' ').title()}: {o.title}",
            "command_center": o.command_center or "business",
            "objective": o.objective or "opportunity", "action_type": "opportunity",
            "value": value, "probability": round(prob, 2), "effort": effort,
            "priority": _score(value, prob, effort, weight, urgency),
            "link": o.link or "/opportunities",
            "why": f"{o.kind or 'opportunity'} · ~${round(value/1000)}k @ {round(prob*100)}%",
        })

    # Drop actions already executed or dismissed (state overlay).
    inactive = {k for (k,) in db.query(ActionState.key)
                .filter(ActionState.status.in_(["done", "dismissed"])).all()}
    actions = [a for a in actions if a["key"] not in inactive]
    actions.sort(key=lambda a: a["priority"], reverse=True)
    return actions


def _unanswered_sms(db: Session) -> list[str]:
    """Phones whose most-recent SMS is inbound (i.e., waiting on a reply)."""
    phones = [p for (p,) in db.query(Message.to_email)
              .filter(Message.channel == "sms", Message.to_email.isnot(None)).distinct().all()]
    out = []
    for phone in phones:
        last = (db.query(Message).filter(Message.channel == "sms", Message.to_email == phone)
                .order_by(Message.created_at.desc()).first())
        if last and last.direction == "inbound":
            out.append(phone)
    return out


def recap(db: Session, hours: int = 24) -> list[dict]:
    """What your digital team accomplished in the last `hours` — the "Yesterday"
    line on the home screen. Pulled from real activity, so it's never theater."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    out: list[dict] = []

    def add(icon: str, label: str, count) -> None:
        if count:
            out.append({"icon": icon, "label": label, "count": int(count)})

    def c(model, *filters) -> int:
        return int(db.query(func.count()).select_from(model).filter(*filters).scalar() or 0)

    add("💼", "jobs sourced", c(Job, Job.found_at >= since))
    add("✅", "applications submitted", c(Application, Application.applied_at >= since))
    add("📧", "outreach emails sent", c(Message, Message.channel == "email",
        Message.direction == "outbound", Message.created_at >= since))
    add("💬", "texts sent", c(Message, Message.channel == "sms",
        Message.direction == "outbound", Message.created_at >= since))
    add("📥", "replies received", c(Message, Message.direction == "inbound",
        Message.created_at >= since))
    add("📣", "posts published", c(ContentItem, ContentItem.published_at >= since))
    add("📝", "content pieces created", c(ContentItem, ContentItem.created_at >= since,
        ContentItem.status.in_(["ready", "needs_approval", "generated", "scheduled"])))
    add("👥", "CRM contacts added", c(Contact, Contact.created_at >= since))
    return out


def brief(db: Session, top_n: int = 3) -> dict:
    """The morning Chief-of-Staff brief: top N actions, value, focus score."""
    actions = build_actions(db)
    top = actions[:top_n]
    expected = round(sum(a["value"] * a["probability"] for a in top))
    focus = min(100, round(expected / 50)) if expected else (20 if not actions else 50)

    # Human-readable summary counts by type.
    def n(t):
        return sum(1 for a in actions if a["action_type"] == t)
    summary = []
    if n("apply"):
        summary.append(f"{n('apply')} executive roles ready to apply")
    if n("follow_up"):
        summary.append(f"{n('follow_up')} warm leads to follow up")
    if n("reply"):
        summary.append(f"{n('reply')} texts awaiting your reply")
    if not summary:
        summary.append("No open actions — run the agents to source opportunities.")

    hour = datetime.now(timezone.utc).hour
    part = "morning" if hour < 12 else "afternoon" if hour < 18 else "evening"
    return {
        "greeting": f"Good {part}, Bruno",
        "focus_score": focus,
        "estimated_value_today": expected,
        "top_actions": top,
        "summary": summary,
        "total_actions": len(actions),
        "hidden_count": max(0, len(actions) - len(top)),
        "recap": recap(db),
    }
