"""Commercial Lead Finder — the priority insurance engine.

Sources new commercial businesses in the licensed states (NH/MA/FL), prioritizing
small/mid businesses (5–200 employees), with owner/email/phone/website/LinkedIn,
then drafts + sends outreach from the Thrust mailbox. Commercial is prioritized
because it produces higher commissions, stickier clients and more referrals.
Runs in capped batches so a single run never times out; schedule it several times
a day to reach the daily target.
"""
from __future__ import annotations

from ..ai.prompts import INSURANCE_OUTREACH
from ..config import settings
from ..integrations import providers
from . import leadgen
from .base import BaseAgent

_PER_RUN_CAP = 50  # keep one run well under the request timeout


class CommercialLeadFinderAgent(BaseAgent):
    key = "commercial_finder"
    name = "Commercial Lead Finder"
    description = ("Finds new commercial businesses in NH/MA/FL (5–200 employees) with "
                   "owner, email, phone, website & LinkedIn, then drafts + sends outreach.")
    schedule_cron = "30 7,11,15,19 * * *"  # 4x/day — the priority engine

    def execute(self) -> dict:
        target = min(settings.commercial_lead_daily_target, _PER_RUN_CAP)
        prospects = providers.fetch_insurance_leads(
            "commercial", target, scope=settings.insurance_lead_scope)
        for p in prospects:
            p["segment"] = "commercial"
            p["reason"] = (f"{p.get('category', 'Commercial')} businesses typically need "
                           "liability, property and professional coverage.")

        def build_prompt(p):
            return INSURANCE_OUTREACH.format(
                company_name=p["company_name"], category=p.get("category") or "Commercial",
                segment="commercial", industry=p.get("industry"), city=p.get("city"),
                reason=p["reason"])

        res = leadgen.run_batch(
            self, prospects, account="insurance", build_prompt=build_prompt,
            default_segment="commercial",
            subject_for=lambda p, a: a.get("cold_email_subject") or f"Insurance options for {p['company_name']}")
        self.log_action("commercial_leads", entity="leads", detail=res)
        return {"summary": f"Commercial Lead Finder: {res['saved']} found, "
                f"{res['enriched']} drafted, {res['emailed']} emailed.", **res}
