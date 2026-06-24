"""Free real-lead sourcing via OpenStreetMap (Overpass API).

Finds real local businesses by category and city from OpenStreetMap — no API key,
no cost — preferring each business's published email tag and falling back to the
shared website email-finder. Produces real leads with real, deliverable emails at
$0. Set LEAD_CITIES to control the search areas.
"""
from __future__ import annotations

import logging

import httpx

from ..config import settings
from . import email_finder

log = logging.getLogger("bruno.osm")

# Several public Overpass mirrors — the main one (overpass-api.de) is frequently
# rate-limited (429) or overloaded (504). We try each in order until one answers,
# so a single busy server never means "zero leads".
OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]

# Commercial-insurance prospect categories → OpenStreetMap selectors.
COMMERCIAL_OSM = {
    "Restaurant": ['node["amenity"~"restaurant|cafe|fast_food|bar|pub"]'],
    "Contractor": ['node["craft"~"plumber|electrician|carpenter|hvac|roofer|painter|builder"]'],
    "Retail store": ['node["shop"~"convenience|clothes|hardware|florist|gift|bakery|butcher|jewelry|shoes|furniture"]'],
    "Real estate agency": ['node["office"="estate_agent"]'],
    "Medical office": ['node["amenity"~"clinic|doctors|dentist|veterinary|pharmacy"]'],
    "Landscaper": ['node["craft"="gardener"]', 'node["shop"="garden_centre"]'],
    "Auto services": ['node["shop"~"car_repair|car|tyres"]', 'node["amenity"="fuel"]'],
    "Beauty & wellness": ['node["shop"~"hairdresser|beauty"]', 'node["leisure"="fitness_centre"]', 'node["amenity"="gym"]'],
    "Professional services": ['node["office"~"lawyer|accountant|insurance|company|it|financial"]'],
    "Hospitality": ['node["tourism"~"hotel|guest_house"]'],
}
RESTAURANT_OSM = ['node["amenity"~"restaurant|cafe|bar|pub|fast_food"]']

# Bound website scraping per run so the agent stays fast (each scrape is a few
# HTTP fetches). Most leads should come from OSM email tags (zero scraping).
_SCRAPE_BUDGET = 15
# Don't scan every configured city — stop once we have enough.
_MAX_CITIES = 4


def is_enabled() -> bool:
    return bool(settings.lead_cities)


def _cities() -> list[str]:
    return [c.strip() for c in settings.lead_cities.split(",") if c.strip()]


def _clean_email(e: str | None) -> str | None:
    return email_finder.clean_email(e)


_TIMEOUT = httpx.Timeout(25.0, connect=5.0)


def _post_overpass(body: str) -> list[dict]:
    """POST a query to Overpass, failing over across mirrors on any error/limit."""
    last = ""
    for url in OVERPASS_MIRRORS:
        try:
            r = httpx.post(url, data={"data": body}, timeout=_TIMEOUT)
            if r.status_code != 200:  # busy/blocked/bad → just try the next mirror
                last = f"{url} -> HTTP {r.status_code}"
                continue
            return r.json().get("elements", [])
        except Exception as exc:  # pragma: no cover - network guard
            last = f"{url} -> {exc}"
            continue
    log.warning("All Overpass mirrors failed: %s", last)
    return []


def _query(selectors: list[str], city: str) -> list[dict]:
    """One bounded Overpass query for a city, newest-area match.

    Constrains the area to municipal level (admin_level 8 = US city) so a bare
    city name can't match a whole state. Cities in LEAD_CITIES are unambiguous
    municipalities, so a single query suffices.
    """
    parts = []
    for s in selectors:
        for tag in ('["contact:email"]', '["email"]', '["website"]', '["contact:website"]'):
            parts.append(f"{s}{tag}(area.a);")
    inner = "".join(parts)
    head = (f'[out:json][timeout:20];'
            f'area["name"="{city}"]["admin_level"="8"]->.a;')
    els = _post_overpass(head + "(" + inner + ");out tags 100;")
    if not els:  # some cities sit at a different admin level — fall back to name
        head = f'[out:json][timeout:20];area["name"="{city}"]["boundary"="administrative"]->.a;'
        els = _post_overpass(head + "(" + inner + ");out tags 100;")
    return els


def _category_for(t: dict, default: str = "Commercial") -> str:
    """Best-effort business category from OSM tags (for the lead record)."""
    if t.get("amenity") in {"restaurant", "cafe", "fast_food", "bar", "pub"}:
        return "Restaurant"
    if t.get("craft"):
        return "Contractor"
    if t.get("office"):
        return "Professional services"
    if t.get("tourism"):
        return "Hospitality"
    if t.get("amenity") in {"clinic", "doctors", "dentist", "veterinary", "pharmacy"}:
        return "Medical office"
    if t.get("shop"):
        return "Retail store"
    return default


def _harvest(selectors: list[str], segment: str, count: int) -> list[dict]:
    """Pull up to ``count`` leads with real emails across a few cities.

    Single Overpass query per city (all selectors at once). Email-tagged
    businesses are taken instantly; website-only ones are scraped within a small
    budget so the run never hangs.
    """
    seen: set[str] = set()
    out: list[dict] = []
    pending: list[tuple[dict, str]] = []  # (tags, city) needing a scrape
    budget = [_SCRAPE_BUDGET]

    for city in _cities()[:_MAX_CITIES]:
        if len(out) >= count:
            break
        for el in _query(selectors, city):
            t = el.get("tags", {})
            name = t.get("name")
            if not name:
                continue
            email = _clean_email(t.get("contact:email") or t.get("email"))
            if email:
                if email in seen:
                    continue
                seen.add(email)
                out.append(_row(t, email, city, segment))
                if len(out) >= count:
                    break
            elif t.get("website") or t.get("contact:website"):
                pending.append((t, city))

    # Fill any shortfall by scraping website-only businesses (bounded).
    for t, city in pending:
        if len(out) >= count or budget[0] <= 0:
            break
        website = t.get("website") or t.get("contact:website")
        email = email_finder.extract_email(website, budget)
        if not email or email in seen:
            continue
        seen.add(email)
        out.append(_row(t, email, city, segment))

    return out[:count]


def _row(t: dict, email: str, city: str, segment: str) -> dict:
    cat = _category_for(t)
    return {
        "segment": segment, "category": cat, "company_name": t.get("name"),
        "owner_name": None, "email": email,
        "phone": t.get("phone") or t.get("contact:phone"),
        "website": t.get("website") or t.get("contact:website"),
        "linkedin": None, "industry": cat, "city": city,
    }


def _all_commercial_selectors() -> list[str]:
    sels: list[str] = []
    for v in COMMERCIAL_OSM.values():
        sels.extend(v)
    return sels


def fetch_commercial_leads(count: int) -> list[dict]:
    if not is_enabled():
        return []
    return _harvest(_all_commercial_selectors(), "commercial", count)


def fetch_restaurants(count: int) -> list[dict]:
    if not is_enabled():
        return []
    rows = _harvest(RESTAURANT_OSM, "commercial", count)
    return [{
        "kind": "prospect", "name": r["company_name"], "owner_manager": None,
        "website": r["website"], "menu_url": None, "instagram": None,
        "email": r["email"], "phone": r["phone"], "cuisine": None, "city": r["city"],
        "pain_points": "Research before outreach",
    } for r in rows]
