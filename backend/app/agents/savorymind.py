"""Agent 3: SavoryMind Growth — runs daily at 7 AM."""
from __future__ import annotations

from ..ai import client, skills
from ..ai.prompts import MENU_ANALYSIS, SAVORYMIND_PITCH
from ..integrations import providers
from ..models import Restaurant
from .base import BaseAgent

RESTAURANT_TARGET = 100
CONSUMER_TARGET = 100


class SavoryMindAgent(BaseAgent):
    key = "savorymind"
    name = "SavoryMind Growth Agent"
    description = "Sources restaurant prospects, analyzes menus with AI, and builds a consumer growth list."
    schedule_cron = "0 7 * * *"  # 7 AM

    def execute(self) -> dict:
        restaurants = providers.fetch_restaurants(RESTAURANT_TARGET)
        consumers = providers.fetch_food_consumers(CONSUMER_TARGET)
        saved = 0

        for r in restaurants:
            analysis = client.complete_json(MENU_ANALYSIS.format(
                name=r["name"], cuisine=r["cuisine"], city=r["city"],
                website=r["website"], pain_points=r["pain_points"],
            ))
            insight = ""
            if isinstance(analysis, dict) and analysis.get("upsell"):
                up = analysis["upsell"]
                insight = up[0] if isinstance(up, list) and up else str(up)
            pitch = client.complete_json(SAVORYMIND_PITCH.format(
                name=r["name"], cuisine=r["cuisine"], city=r["city"],
                owner=r["owner_manager"], insight=insight or r["pain_points"],
            ), system=skills.system_prompt("copywriting", "cold-email"))
            pitch = pitch if isinstance(pitch, dict) else {}
            subject = pitch.get("pitch_subject") or f"Growing revenue at {r['name']} with SavoryMind"
            body = pitch.get("pitch_body")
            row = Restaurant(
                kind="prospect", name=r["name"], owner_manager=r["owner_manager"],
                website=r["website"], menu_url=r["menu_url"], instagram=r["instagram"],
                email=r["email"], phone=r["phone"], cuisine=r["cuisine"], city=r["city"],
                pain_points=r["pain_points"], menu_analysis=analysis if isinstance(analysis, dict) else None,
                pitch_email=body,
                linkedin_msg=pitch.get("linkedin_msg"),
                follow_up=pitch.get("demo_invite"),
                status="Drafted",
            )
            self.db.add(row)
            self.db.flush()
            self.schedule_follow_ups("restaurant", row.id)

            msg = self.dispatch_email(entity_type="restaurant", entity_id=row.id,
                                      to_email=r.get("email"), subject=subject, body=body)
            if msg.status == "Sent":
                row.status = "Sent"
                sent += 1
            saved += 1

        consumers_saved = 0
        for c in consumers:
            self.db.add(Restaurant(
                kind="consumer", name=c["name"], instagram=c["instagram"],
                city=c["city"], cuisine=c["cuisine"], status="New",
            ))
            consumers_saved += 1

        self.log_action("restaurants_saved", entity="restaurants",
                        detail={"prospects": saved, "consumers": consumers_saved})
        return {
            "summary": f"Saved {saved} restaurant prospects and {consumers_saved} consumer growth targets.",
            "prospects": saved,
            "consumers": consumers_saved,
        }
