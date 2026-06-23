"""Agent 5: Instagram Growth — runs daily at 9 AM."""
from __future__ import annotations

from datetime import date

from ..ai import client
from ..ai.prompts import INSTAGRAM_CALENDAR, INSTAGRAM_ENGAGEMENT
from ..integrations import providers
from ..models import Campaign, InstagramTarget
from .base import BaseAgent

TARGET_COUNT = 100


class InstagramAgent(BaseAgent):
    key = "instagram"
    name = "Instagram Growth Agent"
    description = "Finds 100 target accounts daily, categorizes them, and builds a weekly content calendar."
    schedule_cron = "0 9 * * *"  # 9 AM

    def execute(self) -> dict:
        targets = providers.fetch_instagram_targets(TARGET_COUNT)
        for t in targets:
            eng = client.complete_json(INSTAGRAM_ENGAGEMENT.format(
                handle=t["handle"], niche=t["niche"], category=t["category"]))
            self.db.add(InstagramTarget(
                handle=t["handle"], niche=t["niche"], category=t["category"], followers=t["followers"],
                comment_idea=eng.get("comment_idea") if isinstance(eng, dict) else None,
                dm_opener=eng.get("dm_opener") if isinstance(eng, dict) else None,
                story_reply=eng.get("story_reply") if isinstance(eng, dict) else None,
                status="New",
            ))

        # Weekly content calendar (refreshed daily).
        calendar = client.complete_json(INSTAGRAM_CALENDAR)
        self.db.add(Campaign(channel="instagram", title=f"IG calendar {date.today()}",
                             content=calendar if isinstance(calendar, dict) else {}, scheduled_for=date.today()))

        self.log_action("instagram_targets_saved", entity="instagram_targets",
                        detail={"count": len(targets)})
        return {
            "summary": f"Saved {len(targets)} Instagram targets and refreshed the weekly content calendar.",
            "targets": len(targets),
        }
