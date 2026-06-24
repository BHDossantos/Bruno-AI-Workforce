"""Agent 5: Instagram Growth — runs daily at 9 AM."""
from __future__ import annotations

import logging
from datetime import date

from .. import brand, media
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

        # ── Automatic mode: act on the CONNECTED account ──────────────────────
        connected = instagram_api.is_connected(self.db)
        published = None
        if connected and settings.instagram_auto_publish:
            published = self._auto_publish(calendar)

        acct = instagram_api.get_account(self.db) if connected else None
        followers = acct.get("followers") if acct else None

        self.log_action("instagram_targets_saved", entity="instagram_targets",
                        detail={"count": saved, "connected": connected, "published": bool(published)})
        summary = "Refreshed the brand-tailored 7-day content calendar"
        summary += f" and saved {saved} target accounts to engage." if saved else "."
        if connected:
            summary += f" Account connected ({followers:,} followers)." if followers else " Account connected."
        if published and published.get("ok"):
            summary += " Auto-published today's post."
        return {"summary": summary, "targets": saved, "calendar": bool(calendar),
                "connected": connected, "followers": followers, "published": published}

    def _auto_publish(self, calendar) -> dict | None:
        """Publish today's planned post IF it carries an image_url. (Instagram's
        API requires media — text-only posts aren't allowed — so a post needs an
        image source before this does anything.)"""
        items = (calendar or {}).get("calendar") if isinstance(calendar, dict) else None
        if not items:
            return None
        today = items[0]
        caption = today.get("caption") or today.get("idea") or ""
        image_url = today.get("image_url")
        if not image_url:
            # No image on the plan — generate one and host it publicly (IG needs media).
            image_url = media.generate_and_host(today.get("idea") or caption, f"{date.today()}-post")
        if not image_url:
            log.info("IG auto-publish skipped: no image (set GCS_BUCKET + OpenAI key to auto-generate)")
            return {"ok": False, "reason": "no image to post"}
        return instagram_api.publish_post(self.db, image_url, caption)
