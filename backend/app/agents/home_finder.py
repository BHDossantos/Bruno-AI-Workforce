"""Home Lead Finder — the free, compliant home-insurance engine.

You can't buy your way off EverQuote by scraping homeowners (cold-contacting
consumers who never opted in is a TCPA problem). What you CAN do is find the
businesses whose customers all need home insurance the moment they close —
realtors, mortgage/finance offices, property managers, title/closing attorneys
and builders — and build two-way referral partnerships. Every closing they
touch is a home policy (usually bundled with auto).

Sources real businesses from OpenStreetMap (free, no API key) in the licensed
states and drafts warm B2B partnership outreach. Runs in capped batches so a
single run never times out; the scheduler runs it several times a day.
"""
from __future__ import annotations

from ..ai.prompts import REFERRAL_PARTNER_OUTREACH
from ..config import settings
from ..integrations import providers
from . import leadgen
from .base import BaseAgent

_PER_RUN_CAP = 40  # keep one run well under the request timeout


class HomeLeadFinderAgent(BaseAgent):
    key = "home_finder"
    name = "Home Lead Finder"
    description = ("Finds real realtors, mortgage/finance offices, property managers, title "
                   "attorneys & builders in NH/MA/FL — every closing needs home (+ bundled auto).")
    schedule_cron = "40 8,13,18 * * *"  # 3x/day

    def execute(self, *, scope: str | None = None, campaign_id: str | None = None) -> dict:
        target = min(settings.home_lead_daily_target, _PER_RUN_CAP)
        prospects = providers.fetch_home_feeders(
            target, scope=scope or settings.insurance_lead_scope)
        for p in prospects:
            p["segment"] = "referral_partner"
            p["reason"] = (f"{p.get('category', 'Your')} clients need home insurance at every "
                           "closing — and most bundle auto for a bigger discount. A two-way "
                           "referral means you send them buyers and I quote every one.")

        cal = settings.calendar_link_insurance or settings.calendar_link

        def build_prompt(p):
            base = REFERRAL_PARTNER_OUTREACH.format(
                company_name=p.get("company_name") or p.get("owner_name") or "there",
                category=p.get("category") or "partner", city=p.get("city") or "")
            if cal:
                base += f"\nIf helpful, offer this booking link in the CTA: {cal}"
            return base

        res = leadgen.run_batch(
            self, prospects, account="insurance", build_prompt=build_prompt,
            default_segment="referral_partner", campaign_id=campaign_id,
            subject_for=lambda p, a: a.get("cold_email_subject") or f"Home + auto referrals for {p['company_name']}")
        self.log_action("home_leads", entity="leads", detail=res)
        return {"summary": f"Home Lead Finder: {res['saved']} home feeders found, "
                f"{res['enriched']} drafted, {res['emailed']} emailed.", **res}
