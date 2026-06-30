"""Insurance line-of-business classifier — Home / Auto / Life / Commercial.

Personal-lines consumers (homeowners, drivers, families) can't be cold-sourced
legally or for free, so home/auto/life clients come through REFERRAL PARTNERS:
realtors and mortgage brokers refer home (and bundled auto), auto dealers/mechanics
refer auto, and CPAs, financial advisors and estate attorneys refer life.

This maps every lead — a direct personal prospect OR a referral partner — to the
personal line it represents or feeds, so the insurance pipeline can be viewed and
filtered by Home / Auto / Life / Commercial. Pure + offline; keyed by substring so
it's robust to category naming across OSM, Apollo and the synthetic fallback.
"""
from __future__ import annotations

HOME, AUTO, LIFE, COMMERCIAL = "home", "auto", "life", "commercial"
LINES = [HOME, AUTO, LIFE, COMMERCIAL]
LABELS = {HOME: "Home", AUTO: "Auto", LIFE: "Life", COMMERCIAL: "Commercial"}

# Referral-partner category keywords → the personal line that partner feeds.
# Order matters: most specific signal first.
_PARTNER_LINES: list[tuple[tuple[str, ...], str]] = [
    (("auto deal", "car deal", "dealership", "mechanic", "car repair", "auto repair", "tire", "garage"), AUTO),
    (("financial advis", "wealth", "cpa", "account", "attorney", "law", "estate plan", "tax", "advisor"), LIFE),
    (("mortgage", "lender", "title", "realtor", "real estate", "property manag", "home", "broker"), HOME),
]
# Direct personal-prospect category keywords → their line.
_PERSONAL_LINES: list[tuple[tuple[str, ...], str]] = [
    (("life", "term life", "whole life", "new parent", "family", "beneficiary", "estate"), LIFE),
    (("auto", "car", "vehicle", "driver"), AUTO),
    (("home", "homeowner", "mover", "purchase", "mortgage", "renter", "condo", "property", "house"), HOME),
]


def line_for(category: str | None, segment: str | None, industry: str | None = None) -> str:
    """The insurance line a lead represents or feeds. Commercial stays commercial;
    everything else resolves to home / auto / life (default home)."""
    seg = (segment or "").strip().lower()
    if seg == "commercial":
        return COMMERCIAL
    text = f"{category or ''} {industry or ''}".lower()
    table = _PARTNER_LINES if seg == "referral_partner" else _PERSONAL_LINES
    for keys, line in table:
        if any(k in text for k in keys):
            return line
    return HOME  # personal default — a partner/prospect with no clear signal feeds home
