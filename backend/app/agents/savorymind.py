"""Agent 3: SavoryMind Growth — runs daily at 7 AM."""
from __future__ import annotations

import logging

from ..ai import client, skills
from ..ai.prompts import MENU_ANALYSIS, SAVORYMIND_PITCH
from ..config import settings
from ..integrations import providers
from ..models import Restaurant
from .base import BaseAgent

log = logging.getLogger("bruno.agents.savorymind")


class SavoryMindAgent(BaseAgent):
    key = "savorymind"
    name = "SavoryMind Growth Agent"
    description = "Sources restaurant prospects, analyzes menus with AI, and builds a consumer growth list."
    schedule_cron = "0 7 * * *"  # 7 AM

    def execute(self) -> dict:
        batch = max(1, settings.lead_batch_size)
        restaurants = providers.fetch_restaurants(batch)
        consumers = providers.fetch_food_consumers(batch)

        # Don't duplicate restaurants we already have (keep contact history).
        existing = {e for (e,) in self.db.query(Restaurant.email)
                    .filter(Restaurant.email.isnot(None)).all()}

        # ── Phase 1: save NEW prospects + consumers FAST (no AI) and commit. ─────
        pairs: list[tuple[Restaurant, dict]] = []
        seen_now: set[str] = set()
        for r in restaurants:
            email = (r.get("email") or "").lower()
            if email and (email in existing or email in seen_now):
                continue
            if email:
                seen_now.add(email)
            row = Restaurant(
                kind="prospect", name=r["name"], owner_manager=r.get("owner_manager"),
                website=r.get("website"), menu_url=r.get("menu_url"), instagram=r.get("instagram"),
                email=r.get("email"), phone=r.get("phone"), cuisine=r.get("cuisine"), city=r.get("city"),
                pain_points=r.get("pain_points"), status="New",
            )
            self.db.add(row)
            pairs.append((row, r))

        consumers_saved = 0
        for c in consumers:
            self.db.add(Restaurant(
                kind="consumer", name=c["name"], instagram=c["instagram"],
                city=c["city"], cuisine=c["cuisine"], status="New",
            ))
            consumers_saved += 1
        self.db.commit()  # prospects + consumers now guaranteed saved
        saved = len(pairs)

        # ── Phase 2: AI menu analysis, pitch + outreach, resilient per-prospect. ─
        sent = enriched = 0
        for row, r in pairs:
            try:
                analysis = client.complete_json(MENU_ANALYSIS.format(
                    name=r["name"], cuisine=r.get("cuisine"), city=r.get("city"),
                    website=r.get("website"), pain_points=r.get("pain_points"),
                ))
                insight = ""
                if isinstance(analysis, dict) and analysis.get("upsell"):
                    up = analysis["upsell"]
                    insight = up[0] if isinstance(up, list) and up else str(up)
                pitch = client.complete_json(SAVORYMIND_PITCH.format(
                    name=r["name"], cuisine=r.get("cuisine"), city=r.get("city"),
                    owner=r.get("owner_manager"), insight=insight or r.get("pain_points"),
                ), system=skills.system_prompt("copywriting", "cold-email"))
                pitch = pitch if isinstance(pitch, dict) else {}
                subject = pitch.get("pitch_subject") or f"Growing revenue at {r['name']} with SavoryMind"
                body = pitch.get("pitch_body")
                row.menu_analysis = analysis if isinstance(analysis, dict) else None
                row.pitch_email = body
                row.linkedin_msg = pitch.get("linkedin_msg")
                row.follow_up = pitch.get("demo_invite")
                row.status = "Drafted"
                self.schedule_follow_ups("restaurant", row.id)

                msg = self.dispatch_email(entity_type="restaurant", entity_id=row.id,
                                          to_email=r.get("email"), subject=subject, body=body)
                if msg.status == "Sent":
                    row.status = "Sent"
                    sent += 1
                enriched += 1
                self.db.commit()
            except Exception:
                log.exception("Enrichment failed for restaurant %s — keeping prospect", r.get("name"))
                self.db.rollback()

        self.log_action("restaurants_saved", entity="restaurants",
                        detail={"prospects": saved, "enriched": enriched, "emailed": sent,
                                "consumers": consumers_saved})
        return {
            "summary": f"Saved {saved} restaurant prospects ({enriched} enriched, {sent} emailed) "
                       f"and {consumers_saved} consumer growth targets.",
            "prospects": saved,
            "enriched": enriched,
            "emailed": sent,
            "consumers": consumers_saved,
        }
