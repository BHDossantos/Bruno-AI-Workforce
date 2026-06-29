"""Homeowner Lead Agent — steady home/auto inflow alongside commercial.

Builds a daily list of personal-lines prospects (new movers, new homeowners,
recent home purchases) in NH/MA/FL and drafts warm home/auto outreach. (New-mover
data needs a paid source like Apollo/USPS NCOA; without it this degrades to the
personal-lines synthetic list so the pipeline still flows.)
"""
from __future__ import annotations

from ..ai.prompts import INSURANCE_OUTREACH
from ..config import settings
from ..integrations import providers
from . import leadgen
from .base import BaseAgent

_PER_RUN_CAP = 50


class HomeownerLeadAgent(BaseAgent):
    key = "homeowner"
    name = "Homeowner Lead Agent"
    description = ("Builds daily home/auto lists — new movers, new homeowners and recent "
                   "purchases in NH/MA/FL — and drafts warm personal-lines outreach.")
    schedule_cron = "45 8,14 * * *"  # 2x/day

    def execute(self) -> dict:
        target = min(settings.homeowner_lead_daily_target, _PER_RUN_CAP)
        prospects = providers.fetch_insurance_leads(
            "personal", target, scope=settings.insurance_lead_scope)
        from .. import insurance_needs
        for p in prospects:
            p["segment"] = "personal"
            p.setdefault("category", "New homeowner")
            # Tailor the rate-review pitch to the personal-lines category.
            p["reason"] = insurance_needs.reason_for(p.get("category"), "personal")

        def build_prompt(p):
            return INSURANCE_OUTREACH.format(
                company_name=p.get("owner_name") or p.get("company_name") or "there",
                category=p.get("category") or "Homeowner", segment="personal",
                industry=p.get("industry"), city=p.get("city"), reason=p["reason"])

        res = leadgen.run_batch(
            self, prospects, account="insurance", build_prompt=build_prompt,
            default_segment="personal",
            subject_for=lambda p, a: a.get("cold_email_subject") or "A quick home & auto rate review")
        self.log_action("homeowner_leads", entity="leads", detail=res)
        return {"summary": f"Homeowner Lead Agent: {res['saved']} found, "
                f"{res['enriched']} drafted, {res['emailed']} emailed.", **res}
