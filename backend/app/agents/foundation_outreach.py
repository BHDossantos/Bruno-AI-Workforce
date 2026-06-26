"""Foundation Partnership & Donor Outreach Agent.

Sources corporate/CSR partners and donor prospects worldwide and drafts
mission-aligned partnership outreach (sponsor a scholarship, fund a music/STEM
program, employee mentorship). Stored as Lead segment="foundation" so they flow
through the CRM, follow-ups and the Approval Queue (you hit send in semi-auto).
"""
from __future__ import annotations

from ..ai.prompts import FOUNDATION_OUTREACH
from ..config import settings
from ..integrations import providers
from . import leadgen
from .base import BaseAgent

_PER_RUN_CAP = 40


class FoundationOutreachAgent(BaseAgent):
    key = "foundation_outreach"
    name = "Foundation Partnership Agent"
    description = ("Sources corporate/CSR sponsors + donor prospects and drafts "
                   "mission-aligned partnership outreach for the foundation.")
    schedule_cron = "20 9 * * 1-5"  # weekday mornings

    def execute(self) -> dict:
        target = _PER_RUN_CAP
        prospects = providers.fetch_insurance_leads(
            "commercial", target, scope=settings.foundation_lead_scope)
        for p in prospects:
            p["segment"] = "foundation"
            p["reason"] = "Potential corporate/CSR partner for the foundation's mission."

        def build_prompt(p):
            return FOUNDATION_OUTREACH.format(
                foundation=settings.foundation_name, mission=settings.foundation_mission,
                tagline=settings.foundation_tagline, pillars=settings.foundation_pillars,
                company_name=p.get("company_name") or "there",
                category=p.get("category") or "company", city=p.get("city") or "")

        res = leadgen.run_batch(
            self, prospects, account="personal", build_prompt=build_prompt,
            default_segment="foundation",
            subject_for=lambda p, a: a.get("cold_email_subject") or f"Partnering with {settings.foundation_name}")
        self.log_action("foundation_partners", entity="leads", detail=res)
        return {"summary": f"Foundation Partnership Agent: {res['saved']} prospects, "
                f"{res['enriched']} drafted, {res['emailed']} emailed.", **res}
