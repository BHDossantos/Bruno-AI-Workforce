"""Evergreen idea library — reusable content seeds the Content Factory draws from
so there's always a fresh topic to produce, across every business line."""
from __future__ import annotations

CATEGORIES: dict[str, list[str]] = {
    "cloud": ["cutting cloud spend without downtime", "multi-cloud vs single-cloud tradeoffs",
              "FinOps habits that save 30%", "Kubernetes cost traps"],
    "sre": ["the anatomy of a good postmortem", "SLOs vs SLAs explained", "killing 2am pages",
            "error budgets in practice", "incident command for small teams"],
    "ai": ["shipping your first production GenAI use case", "RAG vs fine-tuning",
           "AI guardrails that matter", "MLOps for non-ML teams"],
    "security": ["SOC 2 readiness in 90 days", "IAM mistakes that get you breached",
                 "vulnerability triage that scales", "secure-by-default cloud"],
    "leadership": ["leading SRE teams across timezones", "hiring your first platform engineer",
                   "fractional CTO: when it makes sense", "engineering operating models"],
    "insurance": ["why growing businesses underinsure", "cyber liability 101 for SMBs",
                  "key-person coverage explained"],
    "savorymind": ["menu engineering that lifts margin", "restaurant data you're ignoring",
                   "turning reviews into revenue"],
    # Fan-facing, story-first promo angles for the Bruno D universe (NOT music-
    # industry thought leadership). Kept in sync with music_brand.CONTENT_ANGLES.
    "music": ["the true story behind this lyric", "the girl who inspired this song",
              "a song I wrote walking through Rome", "sax-only version of the hook",
              "studio at 2 AM building this song", "the one line everyone repeats",
              "the city that inspired this song", "behind the song: who she was"],
    "fitness": ["training around a founder's schedule", "recovery as a performance lever"],
    "italy": ["lessons from Italian craftsmanship", "la dolce vita as an operating principle"],
    "travel": ["working remotely across continents", "systems for a location-independent life"],
}

# Which categories feed which business line by default.
BUSINESS_CATEGORIES: dict[str, list[str]] = {
    "executive": ["sre", "cloud", "leadership", "ai"],
    "bnbglobal": ["cloud", "sre", "security", "ai", "leadership"],
    "insurance": ["insurance", "leadership"],
    "savorymind": ["savorymind", "ai"],
    "music": ["music"],
    "personal": ["fitness", "italy", "travel", "leadership"],
}


def pick_topic(business: str, seed: int) -> str:
    """Deterministically pick a topic for a business line (seed = day-of-year etc.)."""
    cats = BUSINESS_CATEGORIES.get(business) or list(CATEGORIES)
    ideas = [i for c in cats for i in CATEGORIES.get(c, [])]
    if not ideas:
        ideas = [i for v in CATEGORIES.values() for i in v]
    return ideas[seed % len(ideas)]
