"""Agent 5: Instagram Growth — runs daily at 9 AM."""
from __future__ import annotations

import logging
from datetime import date

from .. import brand, social
from ..ai import client
from ..ai.prompts import INSTAGRAM_CALENDAR, INSTAGRAM_ENGAGEMENT
from ..config import settings
from ..integrations import instagram_api, providers
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

        # ── Automatic mode: post today's content to EVERY connected platform ──
        platforms = social.connected_platforms(self.db)
        social.snapshot(self.db)  # record follower counts for growth charts
        published = None
        if platforms and (settings.social_auto_publish or settings.instagram_auto_publish):
            published = social.publish_daily(self.db, self._todays_caption(calendar))

        self.log_action("instagram_targets_saved", entity="instagram_targets",
                        detail={"count": saved, "connected": platforms, "published": bool(published)})
        summary = "Refreshed the brand-tailored 7-day content calendar"
        summary += f" and saved {saved} target accounts to engage." if saved else "."
        if platforms:
            summary += f" Connected: {', '.join(platforms)}."
        if published:
            ok = [p for p, r in published.get("published", {}).items() if r.get("ok")]
            if ok:
                summary += f" Auto-posted to {', '.join(ok)}."
        return {"summary": summary, "targets": saved, "calendar": bool(calendar),
                "connected": platforms, "published": published}

    @staticmethod
    def _todays_caption(calendar) -> str:
        items = (calendar or {}).get("calendar") if isinstance(calendar, dict) else None
        if not items:
            return "Today's update."
        today = items[0]
        return today.get("caption") or today.get("idea") or "Today's update."
