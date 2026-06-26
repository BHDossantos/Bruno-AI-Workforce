"""Grant Research Agent — finds funding that fits the foundation's mission.

Pulls posted opportunities (Grants.gov first), scores each by how well it matches
the foundation's pillars (education, music/arts, technology, community, leadership),
de-dupes against grants already tracked, and saves them for review in priority
order. No outreach — discovery + scoring only.
"""
from __future__ import annotations

import logging
from datetime import date, datetime

from ..config import settings
from ..integrations import grants
from ..models import Grant
from .base import BaseAgent

log = logging.getLogger("bruno.agents.grant_research")

# Pillar → keywords that signal a fit (weighted by mission centrality).
_PILLAR_KEYWORDS = {
    "Music & Arts": ["music", "arts", "orchestra", "choir", "instrument", "cultural", "performance"],
    "Education & Scholarships": ["education", "scholarship", "student", "school", "learning", "literacy"],
    "Technology & Innovation": ["technology", "stem", "coding", "digital", "ai", "innovation", "computer"],
    "Opportunity & Leadership": ["leadership", "mentor", "career", "workforce", "entrepreneur"],
    "Community Development": ["community", "youth", "nonprofit", "social", "development"],
}


def score_fit(text: str) -> tuple[int, str | None]:
    """Mission-fit score (0–100) + best-matching pillar from a grant's text."""
    t = (text or "").lower()
    best_pillar, best_hits = None, 0
    total = 0
    for pillar, kws in _PILLAR_KEYWORDS.items():
        hits = sum(1 for k in kws if k in t)
        total += hits
        if hits > best_hits:
            best_hits, best_pillar = hits, pillar
    if total == 0:
        return 30, None  # unknown fit — keep low but visible
    return min(100, 45 + total * 12), best_pillar


def _parse_deadline(raw) -> date | None:
    if not raw:
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y"):
        try:
            return datetime.strptime(str(raw).strip(), fmt).date()
        except ValueError:
            continue
    return None


class GrantResearchAgent(BaseAgent):
    key = "grant_research"
    name = "Grant Research Agent"
    description = ("Finds funding worldwide that fits the foundation's mission, scores by "
                   "pillar fit, and tracks deadlines (Grants.gov first).")
    schedule_cron = "0 7 * * *"  # daily morning

    def execute(self) -> dict:
        target = max(1, min(settings.grant_daily_target, 60))
        found = grants.fetch_grants(target)
        existing = {e for (e,) in self.db.query(Grant.external_id)
                    .filter(Grant.external_id.isnot(None)).all()}
        saved = 0
        for g in found:
            ext = g.get("external_id")
            if ext and ext in existing:
                continue
            fit_text = " ".join(filter(None, [g.get("title"), g.get("category"),
                                              g.get("keyword"), g.get("summary")]))
            score, pillar = score_fit(fit_text)
            self.db.add(Grant(
                title=g.get("title") or "Untitled opportunity",
                funder=g.get("funder"), source=g.get("source"), external_id=ext,
                url=g.get("url"), deadline=_parse_deadline(g.get("deadline")),
                eligibility=g.get("eligibility"), summary=g.get("summary"),
                category=g.get("category") or pillar, match_score=score, status="New"))
            if ext:
                existing.add(ext)
            saved += 1
        self.db.commit()
        self.log_action("grants_found", entity="grants", detail={"count": saved})
        return {"summary": f"Grant Research: {saved} new opportunities scored by mission fit.",
                "saved": saved}
