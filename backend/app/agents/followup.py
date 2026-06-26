"""Follow-Up Agent — keeps every lead engaged until they buy or opt out.

Delegates to the shared follow-up engine, which sends the due multi-step email
sequence (Day 3/6/9/12/15/29/43) to anyone who hasn't replied, routed through the
right mailbox with the daily cap + dedupe. Opt-outs and won/lost leads are skipped
automatically.
"""
from __future__ import annotations

from .. import followups
from .base import BaseAgent


class FollowUpAgent(BaseAgent):
    key = "follow_up_agent"
    name = "Follow-Up Agent"
    description = ("Automatically sends due email/SMS follow-ups and reminders, keeping "
                   "leads engaged until they buy or opt out.")
    schedule_cron = "0 11 * * *"  # daily, after the morning sourcing runs

    def execute(self) -> dict:
        res = followups.process_due_followups(self.db)
        res = res if isinstance(res, dict) else {"result": res}
        self.log_action("followups", entity="follow_ups", detail=res)
        sent = res.get("sent", 0)
        return {"summary": f"Follow-Up Agent: sent {sent} due follow-up(s).", **res}
