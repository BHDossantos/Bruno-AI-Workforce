"""Referral Partner Agent — builds a two-way referral network.

Finds mortgage brokers, real-estate agents, lenders, CPAs and attorneys in the
licensed states and sends partnership outreach (their clients need insurance; you
send them business back). Partner leads are stored with segment="referral_partner".
When a calendar link is configured it's woven into the CTA to book a quick intro.
"""
from __future__ import annotations

from ..ai.prompts import REFERRAL_PARTNER_OUTREACH
from ..config import settings
from ..integrations import providers
from . import leadgen
from .base import BaseAgent

_PER_RUN_CAP = 30


class ReferralPartnerAgent(BaseAgent):
    key = "referral_partner"
    name = "Referral Partner Agent"
    description = ("Finds mortgage brokers, realtors, lenders, CPAs & attorneys and runs "
                   "two-way referral outreach (their clients need insurance).")
    schedule_cron = "15 10 * * 1-5"  # weekday mornings

    def execute(self) -> dict:
        target = min(settings.referral_partner_daily_target, _PER_RUN_CAP)
        prospects = providers.fetch_referral_partners(target, scope=settings.insurance_lead_scope)
        cal = settings.calendar_link
        for p in prospects:
            p["reason"] = (f"{p.get('category', 'Your')} clients routinely need insurance "
                           "(a new mortgage needs home coverage) — a natural two-way referral.")

        def build_prompt(p):
            base = REFERRAL_PARTNER_OUTREACH.format(
                company_name=p.get("company_name") or p.get("owner_name") or "there",
                category=p.get("category") or "partner", city=p.get("city") or "")
            if cal:
                base += f"\nIf helpful, offer this booking link in the CTA: {cal}"
            return base

        res = leadgen.run_batch(
            self, prospects, account="insurance", build_prompt=build_prompt,
            default_segment="referral_partner",
            subject_for=lambda p, a: a.get("cold_email_subject") or f"A quick partnership idea for {p['company_name']}")
        self.log_action("referral_partners", entity="leads", detail=res)
        return {"summary": f"Referral Partner Agent: {res['saved']} partners found, "
                f"{res['enriched']} drafted, {res['emailed']} emailed.", **res}
