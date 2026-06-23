"""Shared agent infrastructure: run lifecycle, logging, follow-up scheduling."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import settings
from ..integrations import gmail
from ..models import ActionLog, Agent, FollowUp, Message, Task

log = logging.getLogger("bruno.agents")

# Follow-up cadence (days from first contact) per the automation spec.
FOLLOW_UP_DAYS = [0, 2, 5, 10, 20]


class BaseAgent:
    key: str = "base"
    name: str = "Base Agent"
    description: str = ""
    schedule_cron: str = "0 0 * * *"

    def __init__(self, db: Session):
        self.db = db

    # ── helpers ──────────────────────────────────────────────────────────────
    def log_action(self, action: str, entity: str | None = None,
                   entity_id: str | None = None, detail: dict | None = None) -> None:
        self.db.add(ActionLog(actor=self.key, action=action, entity=entity,
                              entity_id=str(entity_id) if entity_id else None, detail=detail))

    def schedule_follow_ups(self, entity_type: str, entity_id) -> None:
        """Create the Day 0/2/5/10/20 follow-up sequence for an entity."""
        today = date.today()
        for step, offset in enumerate(FOLLOW_UP_DAYS):
            self.db.add(FollowUp(
                entity_type=entity_type, entity_id=entity_id,
                step=step, due_date=today + timedelta(days=offset),
            ))

    def dispatch_email(self, *, entity_type: str, entity_id, to_email: str | None,
                       subject: str | None, body: str | None,
                       account: str = "personal") -> Message:
        """Create an outbound email Message and route it through Gmail ``account``.

        ``account`` selects the sending mailbox ("personal" or "insurance").
        Behavior follows ``GMAIL_OUTBOUND_MODE``:
        - ``draft``           — create a Gmail draft, never send.
        - ``send_on_approve`` — draft now; sent later once approved.
        - ``send``            — auto-send now (subject to the per-account daily cap + dedupe).

        Guardrails: requires a recipient; never contacts the same address twice
        in one day; respects ``GMAIL_DAILY_SEND_CAP`` per account.
        """
        msg = Message(channel="email", direction="outbound", entity_type=entity_type,
                      entity_id=entity_id, to_email=to_email, from_account=account,
                      subject=subject, body=body, status="Drafted", approved=False)
        self.db.add(msg)
        self.db.flush()

        if not to_email or not gmail.is_configured(account):
            return msg  # nothing to send to / account not configured — leave as stored draft

        mode = settings.gmail_outbound_mode
        if mode == "send" and self._already_contacted_today(to_email):
            self.log_action("send_skipped_duplicate", entity="message", entity_id=msg.id,
                            detail={"to": to_email})
            return msg
        if mode == "send" and self._sent_today_count(account) >= settings.gmail_daily_send_cap:
            mode = "draft"  # hit the safety cap — degrade to draft

        if mode == "send":
            mid = gmail.send_message(to_email, subject or "", body or "", account=account)
            if mid:
                msg.provider_id = mid
                msg.approved = True
                msg.status = "Sent"
                msg.sent_at = datetime.now(timezone.utc)
                self.log_action("email_sent", entity="message", entity_id=msg.id,
                                detail={"to": to_email, "account": account})
        else:  # draft / send_on_approve
            did = gmail.create_draft(to_email, subject or "", body or "", account=account)
            if did:
                msg.provider_id = did
                self.log_action("email_drafted", entity="message", entity_id=msg.id,
                                detail={"to": to_email, "account": account})
        return msg

    def _sent_today_count(self, account: str) -> int:
        today = date.today()
        return self.db.query(func.count()).select_from(Message).filter(
            Message.from_account == account,
            Message.sent_at >= datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc),
        ).scalar() or 0

    def _already_contacted_today(self, to_email: str) -> bool:
        today = date.today()
        return self.db.query(Message).filter(
            Message.to_email == to_email,
            Message.sent_at >= datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc),
        ).first() is not None

    def _touch_agent_row(self) -> None:
        row = self.db.query(Agent).filter(Agent.key == self.key).first()
        if not row:
            row = Agent(key=self.key, name=self.name, description=self.description,
                       schedule_cron=self.schedule_cron)
            self.db.add(row)
        row.last_run_at = datetime.now(timezone.utc)

    # ── lifecycle ────────────────────────────────────────────────────────────
    def run(self) -> dict:
        """Wrap ``execute`` with a Task record and audit logging."""
        self._touch_agent_row()
        agent_row = self.db.query(Agent).filter(Agent.key == self.key).first()
        task = Task(agent_id=agent_row.id if agent_row else None, status="running",
                    started_at=datetime.now(timezone.utc))
        self.db.add(task)
        self.db.flush()
        try:
            result = self.execute()
            task.status = "success"
            task.summary = result.get("summary") if isinstance(result, dict) else None
            task.payload = result if isinstance(result, dict) else {"result": result}
            self.log_action("run_complete", entity="agent", entity_id=self.key, detail={"summary": task.summary})
        except Exception as exc:  # pragma: no cover - defensive
            task.status = "error"
            task.error = str(exc)
            self.log_action("run_error", entity="agent", entity_id=self.key, detail={"error": str(exc)})
            log.exception("Agent %s failed", self.key)
            self.db.commit()
            raise
        finally:
            task.finished_at = datetime.now(timezone.utc)
        self.db.commit()
        return task.payload or {}

    def execute(self) -> dict:  # pragma: no cover - interface
        raise NotImplementedError
