"""Consulting value wedge — map a prospect's industry to the single highest-ROI
BnB Global angle, so consulting outreach leads with a concrete, relevant outcome
(a clinic → HIPAA/security readiness; a retailer → cut cloud spend + stop checkout
downtime; a SaaS startup → fractional-CTO + ship GenAI) instead of "we do IT".

Pure + offline. Keyed by substring against the prospect's category/industry.
"""
from __future__ import annotations

_WEDGES: list[tuple[tuple[str, ...], str]] = [
    (("health", "medical", "clinic", "dental", "hospital", "care", "pharma"),
     "HIPAA/security & compliance readiness plus reliable, always-on systems"),
    (("bank", "financ", "insurance", "account", "fintech", "invest", "capital"),
     "SOC 2 / security-compliance readiness, reliability, and data/AI for operations"),
    (("law", "legal", "attorney", "advocate"),
     "security hardening and GenAI document/case automation that saves billable hours"),
    (("retail", "ecommerce", "e-commerce", "shop", "store", "commerce"),
     "cutting cloud/hosting spend 20–40% and stopping checkout downtime at peak traffic"),
    (("restaurant", "hospitality", "hotel", "food", "travel"),
     "reliable online ordering/booking and POS uptime, plus lower SaaS/cloud costs"),
    (("manufactur", "logistic", "supply", "industrial", "construction", "transport"),
     "data/analytics for operations, cloud cost control, and reliability/observability"),
    (("software", "saas", "startup", "tech", "app", "platform", "ai", "data"),
     "fractional-CTO guidance, shipping a first production GenAI use case, and cloud cost optimization"),
    (("education", "school", "university", "college", "learning", "edtech"),
     "secure, reliable learning platforms and data/AI to improve student outcomes"),
    (("market", "agency", "media", "advertis", "creative", "design"),
     "shipping GenAI-powered features fast while cutting cloud spend"),
    (("real estate", "property", "construction", "estate"),
     "reliable systems, security, and data/AI to streamline operations"),
]
_DEFAULT = ("cutting cloud spend 20–40%, raising uptime/reliability, or shipping a first "
            "production GenAI use case")


def wedge_for(category: str | None = None, industry: str | None = None) -> str:
    t = f"{category or ''} {industry or ''}".lower()
    for keys, wedge in _WEDGES:
        if any(k in t for k in keys):
            return wedge
    return _DEFAULT


def hint_for(category: str | None = None, industry: str | None = None) -> str:
    """Prompt hint nudging the writer toward the most relevant wedge for this prospect."""
    return ("BEST WEDGE FOR THIS PROSPECT — lead with " + wedge_for(category, industry)
            + ". Make it a specific pain + measurable outcome, not a service list.")
