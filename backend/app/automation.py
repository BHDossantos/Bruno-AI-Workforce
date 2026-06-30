"""Automation rules — event-driven branching on prospect behavior.

When a prospect replies, the engine branches automatically (Instantly/Smartlead
"automatic branching"): interested → create a task + stop the drip; unsubscribe →
suppress forever; not-interested → nurture; question/objection → task to respond.
Each rule is individually toggleable (stored in Setting, default ON) and every
action is logged. Built on data we already have (reply intent), so it's reliable.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from .models import ActionLog, Contact, FollowUp, Lead, Message, Restaurant, Setting, Task

log = logging.getLogger("bruno.automation")

# Built-in rules. key → metadata. Triggers fire from on_reply()/on_followup_exhausted().
RULES = [
    {"key": "interested_to_task", "trigger": "reply: interested",
     "action": "Create a high-priority task to respond + stop the drip sequence",
     "label": "Interested reply → task + stop drip"},
    {"key": "unsubscribe_suppress", "trigger": "reply: unsubscribe",
     "action": "Suppress the contact forever (never email again) + stop the drip",
     "label": "Unsubscribe → suppress forever"},
    {"key": "not_interested_nurture", "trigger": "reply: not interested",
     "action": "Move to Nurture + stop the drip (re-engage later)",
     "label": "Not interested → nurture"},
    {"key": "question_to_task", "trigger": "reply: question / objection",
     "action": "Create a task to answer + keep the conversation warm",
     "label": "Question/objection → task"},
    {"key": "exhausted_to_nurture", "trigger": "no reply after the full sequence",
     "action": "Move to Nurture so the queue stays clean",
     "label": "Sequence finished, no reply → nurture"},
]
_KEYS = {r["key"] for r in RULES}


def _setting_key(key: str) -> str:
    return f"automation:{key}"


def enabled(db: Session, key: str) -> bool:
    if key not in _KEYS:
        return False
    row = db.get(Setting, _setting_key(key))
    if row is None or row.value is None:
        return True  # default ON
    return (row.value or "").lower() in ("1", "true", "yes", "on")


def set_enabled(db: Session, key: str, on: bool) -> bool:
    if key not in _KEYS:
        return False
    row = db.get(Setting, _setting_key(key))
    if row is None:
        row = Setting(key=_setting_key(key))
        db.add(row)
    row.value = "true" if on else "false"
    db.commit()
    return True  # success (not the on/off value)


def list_rules(db: Session) -> list[dict]:
    return [{**r, "enabled": enabled(db, r["key"])} for r in RULES]


# ── helpers ───────────────────────────────────────────────────────────────────
def _stop_followups(db: Session, entity_type: str | None, entity_id) -> int:
    if not entity_id:
        return 0
    n = 0
    for fu in db.query(FollowUp).filter(FollowUp.entity_type == entity_type,
                                        FollowUp.entity_id == entity_id,
                                        FollowUp.completed.is_(False)).all():
        fu.completed = True
        n += 1
    return n


def _task(db: Session, summary: str, payload: dict | None = None) -> None:
    db.add(Task(status="pending", summary=summary, payload=payload or {}))


def _suppress(db: Session, sender: str) -> None:
    """Mark every record for this address do_not_contact — never email again."""
    for lead in db.query(Lead).filter(Lead.email == sender).all():
        lead.status = "do_not_contact"
    for rest in db.query(Restaurant).filter(Restaurant.email == sender).all():
        rest.status = "do_not_contact"
    for c in db.query(Contact).filter(Contact.email == sender).all():
        c.status = "do_not_contact"
    for m in db.query(Message).filter(Message.to_email == sender,
                                      Message.status == "Drafted").all():
        m.status = "Suppressed"  # don't let a queued draft go out


def _log(db: Session, rule: str, sender: str, detail: str) -> None:
    db.add(ActionLog(actor="automation", action=rule, entity="email",
                     entity_id=sender, detail={"detail": detail}))


# ── event handlers ────────────────────────────────────────────────────────────
def on_reply(db: Session, *, intent: str, sender: str,
             entity_type: str | None = None, entity_id=None, summary: str | None = None) -> list[str]:
    """Apply enabled rules for a classified reply. Returns the actions taken."""
    done: list[str] = []
    intent = (intent or "").lower()
    s = summary or ""

    if intent == "interested" and enabled(db, "interested_to_task"):
        _task(db, f"🔥 Respond NOW — {sender} is interested: {s}"[:300],
              {"sender": sender, "intent": intent})
        _stop_followups(db, entity_type, entity_id)
        _log(db, "interested_to_task", sender, "task created, drip stopped")
        done.append("created task + stopped drip")

    elif intent == "unsubscribe" and enabled(db, "unsubscribe_suppress"):
        _suppress(db, sender)
        _stop_followups(db, entity_type, entity_id)
        _log(db, "unsubscribe_suppress", sender, "suppressed forever")
        done.append("suppressed forever")

    elif intent == "not_interested" and enabled(db, "not_interested_nurture"):
        if entity_type == "lead" and entity_id:
            lead = db.query(Lead).filter(Lead.id == entity_id).first()
            if lead:
                lead.status = "Nurture"
        _stop_followups(db, entity_type, entity_id)
        _log(db, "not_interested_nurture", sender, "moved to nurture")
        done.append("moved to nurture")

    elif intent in ("question", "objection") and enabled(db, "question_to_task"):
        _task(db, f"Answer {sender} ({intent}): {s}"[:300], {"sender": sender, "intent": intent})
        _log(db, "question_to_task", sender, "task created")
        done.append("created task")

    return done


def on_followup_exhausted(db: Session, entity_type: str | None, entity_id) -> bool:
    """When the full sequence ran with no reply, move the lead to Nurture."""
    if not enabled(db, "exhausted_to_nurture") or entity_type != "lead" or not entity_id:
        return False
    lead = db.query(Lead).filter(Lead.id == entity_id).first()
    if lead and lead.status in (None, "New", "Sent", "Drafted", "Contacted"):
        lead.status = "Nurture"
        return True
    return False
