"""Agent: BnB Global — tech-consulting growth engine.

Sources B2B prospects, writes founder-led, outcome-based outreach (cloud cost,
reliability, security/compliance, AI enablement, managed IT), auto-sends from the
personal mailbox, and schedules the full follow-up sequence. Reuses the Lead
model with segment='consulting' so it flows through the CRM, Daily Brief and
follow-up engine. Feeds the 'consulting' objective under the Wealth Commander.
"""
from __future__ import annotations

import logging

from .. import memory
from ..ai import client, skills
from ..ai.prompts import CANDIDATE_PROFILE, CONSULTING_OUTREACH
from ..config import settings
from ..integrations import providers
from ..models import Lead
from .base import BaseAgent

log = logging.getLogger("bruno.agents.bnbglobal")


class BnbGlobalAgent(BaseAgent):
    key = "bnbglobal"
    name = "BnB Global Consulting"
    description = "Sources B2B prospects and runs founder-led tech-consulting outreach + follow-ups."
    schedule_cron = "0 7 * * *"  # 7 AM

    @staticmethod
    def score_lead(p: dict) -> int:
        score = 50
        if p.get("email"):
            score += 25
        if p.get("website"):
            score += 15
        if p.get("phone"):
            score += 10
        return min(score, 100)

    def execute(self, *, scope: str | None = None, keywords: list[str] | None = None,
               industry: str | None = None, campaign_id: str | None = None) -> dict:
        """`scope`/`keywords`/`industry`/`campaign_id` let Campaign Builder launch a
        one-off targeted run; the daily scheduler calls this with no args and gets
        the normal worldwide sweep."""
        # Source a capped batch toward the daily target (worldwide), timeout-safe;
        # the agent runs several times a day to build outbound volume.
        batch = max(1, min(settings.consulting_lead_daily_target, 50))
        # Real businesses with deliverable emails (same proven source as commercial
        # insurance) — valid prospects for managed IT / cloud / security consulting.
        # Consulting sells worldwide → sweep the global scope (rotating by day).
        prospects = providers.fetch_insurance_leads(
            "commercial", batch, scope=scope or settings.consulting_lead_scope)
        if industry or keywords:
            from . import leadgen
            prospects = [p for p in prospects
                        if leadgen.matches_filters(p, industry=industry, keywords=keywords)]

        existing = {e for (e,) in self.db.query(Lead.email).filter(Lead.email.isnot(None)).all()}

        # Work the highest-fit prospects first so outreach focuses on quality,
        # boosting categories that have actually been converting (reply data).
        from .. import lead_fit, lead_intel
        boosts = lead_intel.category_boosts(self.db)
        prospects = sorted(
            prospects, key=lambda p: lead_fit.score(p) + boosts.get(p.get("category"), 0),
            reverse=True)

        pairs: list[tuple[Lead, dict]] = []
        seen: set[str] = set()
        for p in prospects:
            email = (p.get("email") or "").lower()
            if not email or email in existing or email in seen:
                continue
            seen.add(email)
            row = Lead(
                segment="consulting", category=p.get("category") or "Business",
                company_name=p["company_name"], owner_name=p.get("owner_name"),
                email=p.get("email"), phone=p.get("phone"), website=p.get("website"),
                linkedin=p.get("linkedin"), industry=p.get("industry"),
                reason="Tech consulting: cloud/SRE/security/AI/managed-IT opportunity.",
                score=self.score_lead(p), status="New", campaign_id=campaign_id)
            self.db.add(row)
            pairs.append((row, p))
        self.db.commit()
        saved = len(pairs)

        from .. import consulting_value, lead_intel, outreach_analytics
        # Explore vs exploit: use a proven subject style once one exists; until
        # then rotate styles (A/B) so the learning loop converges fast.
        working = outreach_analytics.whats_working(self.db)
        cat_hint = lead_intel.whats_working(self.db)

        sent = enriched = 0
        for i, (row, p) in enumerate(pairs):
            try:
                sysp = skills.system_prompt("cold-email", "marketing-psychology", "offers")
                subject_hint = working or outreach_analytics.experiment_hint(i)
                wedge_hint = consulting_value.hint_for(p.get("category"), p.get("industry"))
                for hint in (subject_hint, cat_hint, wedge_hint):
                    if hint:
                        sysp = f"{sysp}\n\n{hint}"
                mem_ctx = memory.context_block(self.db, p.get("company_name") or "")
                if mem_ctx:
                    sysp = f"{sysp}\n\n{mem_ctx}"
                art = client.complete_json(CONSULTING_OUTREACH.format(
                    profile=CANDIDATE_PROFILE, company_name=p["company_name"],
                    category=p.get("category") or "", industry=p.get("industry") or "",
                    city=p.get("city") or ""), system=sysp)
                art = art if isinstance(art, dict) else {}
                subject = art.get("cold_email_subject") or f"A quick idea for {p['company_name']}"
                body = art.get("cold_email_body")
                row.cold_email = body
                row.call_script = _as_text(art.get("call_script"))
                row.linkedin_msg = art.get("linkedin_msg")
                row.status = "Drafted"
                self.schedule_follow_ups("lead", row.id)
                from ..integrations import gmail
                msg = self.dispatch_email(entity_type="lead", entity_id=row.id,
                                          to_email=p.get("email"), subject=subject,
                                          body=body, account=gmail.account_for_segment("consulting"))
                if msg.status == "Sent":
                    row.status = "Sent"
                    sent += 1
                enriched += 1
                self.db.commit()
            except Exception:  # one bad lead must not drop the rest
                log.exception("BnB Global enrichment failed for %s", p.get("company_name"))
                self.db.rollback()

        self.log_action("bnbglobal_leads", entity="leads",
                        detail={"count": saved, "enriched": enriched, "emailed": sent})
        return {"summary": f"BnB Global: {saved} prospects, {enriched} drafted, {sent} emailed.",
                "saved": saved, "enriched": enriched, "emailed": sent}


def _as_text(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, dict)):
        import json
        return json.dumps(value, indent=2)
    return str(value)
