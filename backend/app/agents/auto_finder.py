"""Auto Lead Finder — the free, compliant auto-insurance engine.

Mirror of the Home Lead Finder for personal auto. Rather than cold-contacting
drivers (a TCPA problem), it finds the businesses whose customers all need auto
coverage — car dealerships, auto-repair & tire shops, motorcycle dealers and
rental/fleet operators — and drafts warm B2B partnership outreach. Every car
sold or serviced is an auto policy (often bundled with home).

Sources real businesses from OpenStreetMap (free, no API key) in the licensed
states. Runs in capped batches; the scheduler runs it several times a day.
"""
from __future__ import annotations

from ..ai.prompts import REFERRAL_PARTNER_OUTREACH
from ..config import settings
from ..integrations import providers
from . import leadgen
from .base import BaseAgent

_PER_RUN_CAP = 40  # keep one run well under the request timeout


class AutoLeadFinderAgent(BaseAgent):
    key = "auto_finder"
    name = "Auto Lead Finder"
    description = ("Finds real car dealerships, auto-repair & tire shops, motorcycle dealers & "
                   "rental/fleet operators in NH/MA/FL — their customers all need auto coverage.")
    schedule_cron = "50 9,14,19 * * *"  # 3x/day

    def execute(self, *, scope: str | None = None, campaign_id: str | None = None) -> dict:
        target = min(settings.auto_lead_daily_target, _PER_RUN_CAP)
        prospects = providers.fetch_auto_feeders(
            target, scope=scope or settings.insurance_lead_scope)
        for p in prospects:
            p["segment"] = "referral_partner"
            p["reason"] = (f"{p.get('category', 'Your')} customers all need auto insurance — "
                           "a sale, a lease or a repair is the moment they shop coverage. A "
                           "two-way referral means you send them to me and I quote every one.")

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
            subject_for=lambda p, a: a.get("cold_email_subject") or f"Auto referrals for {p['company_name']}")
        self.log_action("auto_leads", entity="leads", detail=res)
        return {"summary": f"Auto Lead Finder: {res['saved']} auto feeders found, "
                f"{res['enriched']} drafted, {res['emailed']} emailed.", **res}
