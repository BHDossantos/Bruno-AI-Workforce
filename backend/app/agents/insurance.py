"""Agent 2: Insurance Lead Generator — runs daily at 6 AM."""
from __future__ import annotations

from ..ai import client, skills
from ..ai.prompts import INSURANCE_OUTREACH
from ..integrations import crm, providers
from ..models import Lead
from .base import BaseAgent

COMMERCIAL_TARGET = 100
PERSONAL_TARGET = 100
QUALIFY_SCORE = 60


class InsuranceAgent(BaseAgent):
    key = "insurance"
    name = "Insurance Lead Generator"
    description = "Sources 200 commercial + personal insurance prospects daily and drafts outreach."
    schedule_cron = "0 6 * * *"  # 6 AM

    @staticmethod
    def score_lead(lead: dict) -> int:
        score = 40
        if lead.get("email"):
            score += 20
        if lead.get("phone"):
            score += 15
        if lead.get("website"):
            score += 15
        if lead.get("segment") == "commercial":
            score += 10
        return min(score, 100)

    def execute(self) -> dict:
        prospects = (
            providers.fetch_insurance_leads("commercial", COMMERCIAL_TARGET)
            + providers.fetch_insurance_leads("personal", PERSONAL_TARGET)
        )
        saved, pushed, sent = 0, 0, 0
        for p in prospects:
            reason = f"{p['category']} businesses typically need liability, property and " \
                     f"professional coverage." if p["segment"] == "commercial" else \
                     f"{p['category']} prospects often need home/auto/life coverage."
            p["reason"] = reason
            score = self.score_lead(p)

            artifacts = client.complete_json(INSURANCE_OUTREACH.format(
                company_name=p["company_name"], category=p["category"], segment=p["segment"],
                industry=p.get("industry"), city=p.get("city"), reason=reason,
            ), system=skills.system_prompt("cold-email", "marketing-psychology"))
            subject = artifacts.get("cold_email_subject") or f"Insurance options for {p['company_name']}"
            body = artifacts.get("cold_email_body")
            row = Lead(
                segment=p["segment"], category=p["category"], company_name=p["company_name"],
                owner_name=p["owner_name"], email=p["email"], phone=p["phone"],
                website=p.get("website"), linkedin=p.get("linkedin"), industry=p.get("industry"),
                reason=reason, score=score, status="Drafted",
                cold_email=body,
                call_script=_as_text(artifacts.get("call_script")),
                linkedin_msg=artifacts.get("linkedin_msg"),
            )
            # Push qualified leads to HubSpot (no-op without API key).
            if score >= QUALIFY_SCORE:
                result = crm.push_lead(p)
                row.pushed_to_crm = bool(result.get("ok"))
                if row.pushed_to_crm:
                    pushed += 1
            self.db.add(row)
            self.db.flush()
            self.schedule_follow_ups("lead", row.id)

            # Route the cold email through the Thrust Insurance mailbox.
            msg = self.dispatch_email(entity_type="lead", entity_id=row.id, to_email=p.get("email"),
                                      subject=subject, body=body, account="insurance")
            if msg.status == "Sent":
                row.status = "Sent"
                sent += 1
            saved += 1

        self.log_action("leads_saved", entity="leads",
                        detail={"count": saved, "pushed": pushed, "emailed": sent})
        return {
            "summary": f"Generated {saved} insurance leads ({pushed} to CRM, {sent} emailed).",
            "saved": saved,
            "pushed_to_crm": pushed,
            "emailed": sent,
        }


def _as_text(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, dict)):
        import json
        return json.dumps(value, indent=2)
    return str(value)
