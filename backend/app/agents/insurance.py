"""Agent 2: Insurance Lead Generator — runs daily at 6 AM."""
from __future__ import annotations

import logging

from ..ai import client, skills
from ..ai.prompts import INSURANCE_OUTREACH
from ..config import settings
from ..integrations import crm, providers
from ..models import Lead
from .base import BaseAgent

log = logging.getLogger("bruno.agents.insurance")

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
        # Run in a small batch (default 20) split across both segments, so each
        # run stays fast; run more often to accumulate more leads.
        batch = max(1, settings.lead_batch_size)
        commercial_target = (batch + 1) // 2
        personal_target = batch // 2
        prospects = (
            providers.fetch_insurance_leads("commercial", commercial_target)
            + providers.fetch_insurance_leads("personal", personal_target)
        )

        # ── Phase 1: persist every lead FAST (no AI/network) and commit, so leads
        # are never lost if the slower enrichment below times out or errors. ──────
        pairs: list[tuple[Lead, dict]] = []
        for p in prospects:
            reason = f"{p['category']} businesses typically need liability, property and " \
                     f"professional coverage." if p["segment"] == "commercial" else \
                     f"{p['category']} prospects often need home/auto/life coverage."
            p["reason"] = reason
            row = Lead(
                segment=p["segment"], category=p["category"], company_name=p["company_name"],
                owner_name=p.get("owner_name"), email=p.get("email"), phone=p.get("phone"),
                website=p.get("website"), linkedin=p.get("linkedin"), industry=p.get("industry"),
                reason=reason, score=self.score_lead(p), status="New",
            )
            self.db.add(row)
            pairs.append((row, p))
        self.db.commit()  # leads are now guaranteed saved
        saved = len(pairs)

        # ── Phase 2: enrich + outreach, resilient per-lead. A failure on one lead
        # (AI hiccup, send error) never drops the lead or aborts the batch. ───────
        pushed = sent = enriched = 0
        for row, p in pairs:
            try:
                artifacts = client.complete_json(INSURANCE_OUTREACH.format(
                    company_name=p["company_name"], category=p["category"], segment=p["segment"],
                    industry=p.get("industry"), city=p.get("city"), reason=p["reason"],
                ), system=skills.system_prompt("cold-email", "marketing-psychology"))
                artifacts = artifacts if isinstance(artifacts, dict) else {}
                subject = artifacts.get("cold_email_subject") or f"Insurance options for {p['company_name']}"
                body = artifacts.get("cold_email_body")
                row.cold_email = body
                row.call_script = _as_text(artifacts.get("call_script"))
                row.linkedin_msg = artifacts.get("linkedin_msg")
                row.status = "Drafted"
                self.schedule_follow_ups("lead", row.id)

                # Sync qualified leads to HubSpot (connected account or env key).
                if row.score >= QUALIFY_SCORE:
                    result = crm.push_lead(p, db=self.db)
                    row.pushed_to_crm = bool(result.get("ok"))
                    if row.pushed_to_crm:
                        pushed += 1

                # Route the cold email through the Thrust Insurance mailbox.
                msg = self.dispatch_email(entity_type="lead", entity_id=row.id, to_email=p.get("email"),
                                          subject=subject, body=body, account="insurance")
                if msg.status == "Sent":
                    row.status = "Sent"
                    sent += 1
                enriched += 1
                self.db.commit()
            except Exception:  # one bad lead must not lose the rest
                log.exception("Enrichment failed for lead %s — keeping the lead, skipping outreach",
                              p.get("company_name"))
                self.db.rollback()

        self.log_action("leads_saved", entity="leads",
                        detail={"count": saved, "enriched": enriched, "pushed": pushed, "emailed": sent})
        return {
            "summary": f"Generated {saved} insurance leads ({enriched} enriched, {pushed} to CRM, {sent} emailed).",
            "saved": saved,
            "enriched": enriched,
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
