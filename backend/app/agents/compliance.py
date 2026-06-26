"""Compliance & Deadline Agent — never miss a grant report or filing.

Auto-creates deadline entries from tracked grants (so each grant you're pursuing
gets its due date on the board), and seeds a one-time reminder to confirm the
foundation's annual filing dates with an accountant. It ALERTS — it does not file
anything. Surfaces upcoming deadlines for the board report / Mission Control.
"""
from __future__ import annotations

from datetime import date, timedelta

from ..models import FoundationDeadline, Grant
from .base import BaseAgent

_ACTIVE_GRANT = ("New", "Reviewing", "Applying", "Submitted")


class ComplianceAgent(BaseAgent):
    key = "compliance"
    name = "Compliance & Deadline Agent"
    description = ("Tracks grant + filing deadlines and alerts before they're due "
                   "(tracking only — it never files anything).")
    schedule_cron = "0 6 * * *"  # daily early

    def execute(self) -> dict:
        existing = {e for (e,) in self.db.query(FoundationDeadline.external_id)
                    .filter(FoundationDeadline.external_id.isnot(None)).all()}
        created = 0
        # Grant deadlines → a tracked deadline each.
        for g in (self.db.query(Grant)
                  .filter(Grant.deadline.isnot(None), Grant.status.in_(_ACTIVE_GRANT)).all()):
            ext = f"grant:{g.id}"
            if ext in existing:
                continue
            self.db.add(FoundationDeadline(
                title=f"Grant deadline — {g.title}", kind="grant_report",
                due_date=g.deadline, status="Open", source="auto", external_id=ext,
                notes=f"Funder: {g.funder or '—'}. Apply/submit before this date."))
            existing.add(ext)
            created += 1
        # One-time nudge to set up the annual compliance calendar.
        if "setup:annual" not in existing:
            self.db.add(FoundationDeadline(
                title="Confirm annual filing dates with your accountant",
                kind="filing", due_date=None, status="Open", source="auto",
                external_id="setup:annual",
                notes="Set exact dates for the annual report / 990 (or local equivalent), "
                      "state/registration renewals, and board meeting cadence."))
            created += 1
        self.db.commit()

        soon = date.today() + timedelta(days=30)
        upcoming = (self.db.query(FoundationDeadline)
                    .filter(FoundationDeadline.status == "Open",
                            FoundationDeadline.due_date.isnot(None),
                            FoundationDeadline.due_date <= soon).count())
        self.log_action("compliance_deadlines", entity="deadlines",
                        detail={"created": created, "due_30d": upcoming})
        return {"summary": f"Compliance: tracked {created} new deadline(s); {upcoming} due in 30 days.",
                "created": created, "due_30d": upcoming}
