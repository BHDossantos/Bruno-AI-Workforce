"""Prospect/job data providers.

Real sourcing (LinkedIn, Indeed, Apollo.io, Google Maps, Spotify, etc.) requires
per-platform credentials and, in some cases, manual export/import. To keep the
whole system runnable today, each provider yields realistic *synthetic* records
and is structured so you can drop in a live API call where marked ``TODO``.

The Indeed and Windsor (HubSpot/Apollo) MCP servers configured for this project
are the recommended live sources — wire them into these functions.
"""
from __future__ import annotations

import random

from ..config import settings
from . import apollo, jobs_api, osm_leads

# Deterministic-ish but varied output per run.
_rng = random.Random()

_CITIES = ["Boston", "New York", "Miami", "Austin", "Rome", "San Francisco", "Chicago", "Denver"]
_FIRST = ["Alex", "Maria", "John", "Sofia", "Marco", "Lucia", "David", "Elena", "Bruno", "Ana"]
_LAST = ["Silva", "Rossi", "Smith", "Garcia", "Johnson", "Ferrari", "Costa", "Bianchi", "Lopez", "Reed"]


def _person() -> str:
    return f"{_rng.choice(_FIRST)} {_rng.choice(_LAST)}"


def _slug(name: str) -> str:
    return name.lower().replace(" ", "").replace(",", "").replace(".", "")[:20]


# ── Agent 1: jobs ────────────────────────────────────────────────────────────
JOB_TITLES = [
    "Director SRE", "Head of SRE", "Director Cloud Engineering",
    "Head of Platform Engineering", "Director Infrastructure", "VP Engineering",
    "Director AI Infrastructure", "Director Data Platform", "CTO", "Fractional CTO",
]
JOB_SOURCES = ["linkedin", "indeed", "wellfound", "builtin", "dice", "company-careers"]
_COMPANIES = ["NorthStar Cloud", "Vellum AI", "Harbor Data", "Apex Platform", "Lumen Systems",
              "Cobalt Infra", "Riverstone Tech", "Helix Compute", "Quanta Labs", "Beacon AI"]


def fetch_jobs(limit: int = 60) -> list[dict]:
    """Live jobs via the JSearch/Indeed aggregator when configured, else synthetic."""
    live = jobs_api.fetch_jobs(JOB_TITLES, limit=limit)
    if live:
        return live
    if not settings.allow_synthetic_fallback:
        return []
    out = []
    for _ in range(limit):
        title = _rng.choice(JOB_TITLES)
        company = _rng.choice(_COMPANIES)
        remote = _rng.random() < 0.6
        smin = _rng.choice([160, 180, 200, 220, 240]) * 1000
        out.append({
            "title": title,
            "company": company,
            "location": "Remote" if remote else _rng.choice(_CITIES),
            "remote": remote,
            "salary_min": smin,
            "salary_max": smin + _rng.choice([40, 60, 80]) * 1000,
            "source": _rng.choice(JOB_SOURCES),
            "url": f"https://example.com/jobs/{_slug(company)}-{_slug(title)}",
            "description": f"{title} role at {company}. Lead cloud/SRE/platform teams, "
                           f"own reliability, scale AI/data infrastructure.",
        })
    return out


# ── Agent 2: insurance prospects ─────────────────────────────────────────────
COMMERCIAL_CATEGORIES = ["Contractor", "Restaurant", "Medical office", "Real estate agency",
                         "Property manager", "Landscaper", "Retail store", "Construction company"]
PERSONAL_CATEGORIES = ["Homeowner", "New mover", "Auto owner", "Mortgage lead"]


def fetch_insurance_leads(segment: str, count: int) -> list[dict]:
    """Real commercial leads from OpenStreetMap (free) + Apollo (if configured).

    The lead-finder agents call this. Commercial prospects come from real local
    businesses (OSM) with real emails, then Apollo, then synthetic top-up (only
    if ALLOW_SYNTHETIC_FALLBACK). Personal leads have no free real source.
    """
    out: list[dict] = []
    if segment == "commercial":
        out.extend(osm_leads.fetch_commercial_leads(count))                 # free, real
        if apollo.is_configured() and len(out) < count:
            for lead in apollo.fetch_commercial_leads(count - len(out)):    # paid, real
                lead.setdefault("category", lead.get("industry") or "Commercial")
                out.append(lead)
        if len(out) >= count:
            return out[:count]

    if not settings.allow_synthetic_fallback:
        return out[:count]  # live-sourced data only
    cats = COMMERCIAL_CATEGORIES if segment == "commercial" else PERSONAL_CATEGORIES
    need = count - len(out)
    for _ in range(need):
        cat = _rng.choice(cats)
        owner = _person()
        company = f"{owner.split()[1]} {cat}" if segment == "commercial" else owner
        out.append({
            "segment": segment,
            "category": cat,
            "company_name": company,
            "owner_name": owner,
            "email": f"{_slug(owner)}@example.com",
            "phone": f"+1{_rng.randint(2000000000, 9999999999)}",
            "website": f"https://{_slug(company)}.com" if segment == "commercial" else None,
            "linkedin": f"https://linkedin.com/in/{_slug(owner)}",
            "industry": cat,
            "city": _rng.choice(_CITIES),
        })
    return out[:count]


# ── Agent 3: SavoryMind restaurants + consumers ──────────────────────────────
RESTAURANT_TYPES = ["Fine dining", "Wine bar", "Cafe", "Family restaurant",
                    "Hospitality group", "Food truck", "Hotel restaurant"]
CUISINES = ["Italian", "Brazilian", "American", "French", "Japanese", "Mexican", "Mediterranean"]


def fetch_restaurants(count: int) -> list[dict]:
    """Real restaurants from OpenStreetMap (free) + Apollo, topped up with synthetic."""
    out: list[dict] = list(osm_leads.fetch_restaurants(count))  # free, real
    if len(out) >= count:
        return out[:count]
    if apollo.is_configured():
        for c in apollo.fetch_restaurant_contacts(count):
            name = c.get("company_name") or "Restaurant"
            out.append({
                "kind": "prospect",
                "name": name,
                "owner_manager": c.get("owner_name"),
                "website": c.get("website"),
                "menu_url": None,
                "instagram": None,
                "email": c.get("email"),
                "phone": c.get("phone"),
                "cuisine": _rng.choice(CUISINES),
                "city": c.get("city") or _rng.choice(_CITIES),
                "pain_points": "Unknown — research before outreach",
            })
        if len(out) >= count:
            return out[:count]

    if not settings.allow_synthetic_fallback:
        return out[:count]  # live-sourced data only
    for _ in range(count - len(out)):
        rtype = _rng.choice(RESTAURANT_TYPES)
        city = _rng.choice(_CITIES)
        name = f"{_rng.choice(_LAST)}'s {rtype}"
        out.append({
            "kind": "prospect",
            "name": name,
            "owner_manager": _person(),
            "website": f"https://{_slug(name)}.com",
            "menu_url": f"https://{_slug(name)}.com/menu",
            "instagram": f"@{_slug(name)}",
            "email": f"info@{_slug(name)}.com",
            "phone": f"+1{_rng.randint(2000000000, 9999999999)}",
            "cuisine": _rng.choice(CUISINES),
            "city": city,
            "pain_points": _rng.choice([
                "Low average ticket", "Weak online reviews",
                "No upsell at point of sale", "Outdated menu"]),
        })
    return out[:count]


def fetch_food_consumers(count: int) -> list[dict]:
    """Consumer growth list (foodies / reviewers / travel-food creators)."""
    if not settings.allow_synthetic_fallback:
        return []
    out = []
    niches = ["Foodie", "Restaurant reviewer", "Travel food account", "Rome food creator", "Boston food creator"]
    for _ in range(count):
        handle = f"{_slug(_person())}{_rng.randint(1, 99)}"
        out.append({
            "kind": "consumer",
            "name": handle,
            "instagram": f"@{handle}",
            "city": _rng.choice(["Rome", "Boston"]),
            "cuisine": _rng.choice(niches),
        })
    return out


# ── Agent 4: music playlists + influencers ───────────────────────────────────
MUSIC_GENRES = ["Samba", "Pagode", "Brazilian jazz", "Latin romance", "R&B",
                "Romantic", "Italian", "Spanish", "Portuguese"]
INFLUENCER_NICHES = ["Music reviewer", "Brazilian culture", "Latin music creator",
                     "Dance creator", "Couples/romance"]


def fetch_playlists(count: int) -> list[dict]:
    if not settings.allow_synthetic_fallback:
        return []
    out = []
    for _ in range(count):
        genre = _rng.choice(MUSIC_GENRES)
        name = f"{genre} {_rng.choice(['Vibes', 'Nights', 'Essentials', 'Hits', 'Lounge'])}"
        out.append({
            "name": name,
            "curator_name": _person(),
            "genre": genre,
            "submission_link": f"https://submithub.com/{_slug(name)}",
            "email": f"{_slug(name)}@example.com",
            "instagram": f"@{_slug(name)}",
            "followers": _rng.randint(2000, 250000),
        })
    return out


def fetch_influencers(count: int) -> list[dict]:
    if not settings.allow_synthetic_fallback:
        return []
    out = []
    for _ in range(count):
        niche = _rng.choice(INFLUENCER_NICHES)
        name = _person()
        out.append({
            "name": name,
            "niche": niche,
            "platform": "Instagram",
            "handle": _slug(name),
            "followers": _rng.randint(5000, 500000),
            "email": f"{_slug(name)}@example.com",
        })
    return out


# ── Agent 5: instagram targets ───────────────────────────────────────────────
IG_NICHES = ["Rome lifestyle", "Brazilian music", "Jiu-jitsu", "MMA", "Entrepreneurship",
             "Food tech", "AI", "Luxury lifestyle", "Jazz", "Romantic music"]
IG_CATEGORIES = ["Potential follower", "Potential collaborator", "Potential customer",
                 "Potential fan", "Potential business lead"]


def fetch_instagram_targets(count: int) -> list[dict]:
    if not settings.allow_synthetic_fallback:
        return []
    out = []
    for _ in range(count):
        out.append({
            "handle": f"{_slug(_person())}{_rng.randint(1, 999)}",
            "niche": _rng.choice(IG_NICHES),
            "category": _rng.choice(IG_CATEGORIES),
            "followers": _rng.randint(500, 200000),
        })
    return out
