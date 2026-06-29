"""School Partnership Agent — develops relationships with schools, universities,
conservatories and community centers, proposing workshops, performances,
scholarships and mentorship. Drafts outreach into the Approval Queue (semi-auto).
Stored as Lead segment="school_partner".
"""
from __future__ import annotations

from ..ai.prompts import SCHOOL_PARTNERSHIP
from ..config import settings
from ..integrations import providers
from . import leadgen
from .base import BaseAgent

_PER_RUN_CAP = 30


class SchoolPartnershipAgent(BaseAgent):
    key = "school_partner"
    name = "School Partnership Agent"
    description = ("Builds relationships with schools, universities, conservatories & "
                   "community centers — proposes workshops, performances & scholarships.")
    schedule_cron = "40 9 * * 1-5"

    def execute(self) -> dict:
        # Source REAL education institutions (schools/universities/conservatories/
        # community centers), not generic businesses.
        prospects = providers.fetch_education_partners(
            _PER_RUN_CAP, scope=settings.foundation_lead_scope)
        for p in prospects:
            p["segment"] = "school_partner"
            p.setdefault("category", "Education institution")
            p["reason"] = "Potential education partner for foundation programs."

        def build_prompt(p):
            return SCHOOL_PARTNERSHIP.format(
                foundation=settings.foundation_name, mission=settings.foundation_mission,
                tagline=settings.foundation_tagline, pillars=settings.foundation_pillars,
                company_name=p.get("company_name") or "there",
                category=p.get("category") or "institution", city=p.get("city") or "")

        res = leadgen.run_batch(
            self, prospects, account="personal", build_prompt=build_prompt,
            default_segment="school_partner",
            subject_for=lambda p, a: a.get("cold_email_subject") or "A partnership idea for your students")
        self.log_action("school_partners", entity="leads", detail=res)
        return {"summary": f"School Partnership Agent: {res['saved']} institutions, "
                f"{res['enriched']} drafted, {res['emailed']} emailed.", **res}
