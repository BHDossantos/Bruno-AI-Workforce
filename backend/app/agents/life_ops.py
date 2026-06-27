"""Life Commander agent — Personal Network.

The Life Commander's job is relationship-building: nurture the user's own personal
network (imported contacts) with warm, value-first outreach. It reuses the proven
warm-contacts engine, so it respects exclusions (family/opt-out), semi-auto drafting,
and never double-contacts. This gives the Life center a real, in-scope function
(relationship marketing) instead of being an empty placeholder.
"""
from __future__ import annotations

from .. import contacts_outreach
from .base import BaseAgent


class LifeOpsAgent(BaseAgent):
    key = "life_ops"
    name = "Personal Network Agent"
    description = "Nurtures your personal network with warm, value-first outreach (relationship-building)."
    schedule_cron = "30 10 * * 1-5"  # weekday mornings

    def execute(self) -> dict:
        res = contacts_outreach.run(self.db)
        res = res if isinstance(res, dict) else {}
        n = res.get("emailed", 0)
        self.log_action("life_ops", entity="contacts", detail=res)
        return {"summary": f"Life: reached out to {n} personal-network contact(s) "
                "with a warm intro (drafted for your approval in semi-auto mode).", **res}
