"""Agent 5: Instagram Growth — runs daily at 9 AM."""
from __future__ import annotations

import logging
from datetime import date

from .. import brand
from ..ai import client
from ..ai.prompts import INSTAGRAM_CALENDAR, INSTAGRAM_ENGAGEMENT
from ..integrations import providers
from ..models import Campaign, InstagramTarget
from .base import BaseAgent

log = logging.getLogger("bruno.agents.instagram")
TARGET_COUNT = 100


class InstagramAgent(BaseAgent):
    key = "instagram"
    name = "Instagram Growth Agent"
    description = "Builds a brand-tailored content calendar and categorizes target accounts to engage."
    schedule_cron = "0 9 * * *"  # 9 AM

    def execute(self) -> dict:
        brand_ctx = brand.context(self.db)

        # The content calendar is the core deliverable — always build it, tailored
        # to the user's own brand profile, even when there are no target accounts.
        calendar = client.complete_json(INSTAGRAM_CALENDAR.format(brand=brand_ctx))
        self.db.add(Campaign(channel="instagram", title=f"IG calendar {date.today()}",
                             content=calendar if isinstance(calendar, dict) else {},
                             scheduled_for=date.today()))
        self.db.commit()

        # Optional: per-target engagement plans (when a target source is available).
        targets = providers.fetch_instagram_targets(TARGET_COUNT)
        saved = 0
        for t in targets:
            try:
                eng = client.complete_json(INSTAGRAM_ENGAGEMENT.format(
                    brand=brand_ctx, handle=t["handle"], niche=t["niche"], category=t["category"]))
                eng = eng if isinstance(eng, dict) else {}
                self.db.add(InstagramTarget(
                    handle=t["handle"], niche=t["niche"], category=t["category"], followers=t["followers"],
                    comment_idea=eng.get("comment_idea"), dm_opener=eng.get("dm_opener"),
                    story_reply=eng.get("story_reply"), status="New"))
                saved += 1
                self.db.commit()
            except Exception:
                log.exception("IG target enrichment failed for %s", t.get("handle"))
                self.db.rollback()

        self.log_action("instagram_targets_saved", entity="instagram_targets", detail={"count": saved})
        return {
            "summary": "Refreshed the brand-tailored 7-day content calendar"
                       + (f" and saved {saved} target accounts to engage." if saved else "."),
            "targets": saved,
            "calendar": bool(calendar),
        }
