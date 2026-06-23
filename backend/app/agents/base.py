"""Shared agent infrastructure: run lifecycle, logging, follow-up scheduling."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..models import ActionLog, Agent, FollowUp, Task

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
