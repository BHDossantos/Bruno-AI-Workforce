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

# Bound website scraping per run so the agent doesn't hang.
_SCRAPE_BUDGET = 120


def is_enabled() -> bool:
    return bool(settings.lead_cities)


def _cities() -> list[str]:
    return [c.strip() for c in settings.lead_cities.split(",") if c.strip()]


def _clean_email(e: str | None) -> str | None:
    return email_finder.clean_email(e)


def _post_overpass(body: str) -> list[dict]:
    """POST a query to Overpass, failing over across mirrors on error/limit."""
    last = ""
    for url in OVERPASS_MIRRORS:
        try:
            r = httpx.post(url, data={"data": body}, timeout=60)
            if r.status_code in (429, 502, 503, 504):  # busy → try next mirror
                last = f"{url} -> HTTP {r.status_code}"
                continue
            r.raise_for_status()
            return r.json().get("elements", [])
        except Exception as exc:  # pragma: no cover - network guard
            last = f"{url} -> {exc}"
            continue
    log.warning("All Overpass mirrors failed: %s", last)
    return []


def _query(selectors: list[str], city: str) -> list[dict]:
    parts = []
    for s in selectors:
        for tag in ('["contact:email"]', '["email"]', '["website"]', '["contact:website"]'):
            parts.append(f"{s}{tag}(area.a);")
    inner = "".join(parts)
    # Constrain the area to municipal levels (city/borough/county) so we never
    # accidentally match a whole STATE area named the same (e.g. "New York"),
    # which would time out. Fall back to an unconstrained name match if needed.
    head_admin = (f'[out:json][timeout:25];'
                  f'area["name"="{city}"]["boundary"="administrative"]["admin_level"~"6|7|8|9|10"]->.a;')
    head_plain = f'[out:json][timeout:25];area["name"="{city}"]->.a;'
    els = _post_overpass(head_admin + "(" + inner + ");out tags 80;")
    if not els:
        els = _post_overpass(head_plain + "(" + inner + ");out tags 80;")
    return els


def _collect(selectors: list[str], category: str, segment: str, count: int,
             budget: list[int], seen: set) -> list[dict]:
    out: list[dict] = []
    for city in _cities():
        if len(out) >= count:
            break
        for el in _query(selectors, city):
            if len(out) >= count:
                break
            t = el.get("tags", {})
            name = t.get("name")
            if not name:
                continue
            email = _clean_email(t.get("contact:email") or t.get("email"))
            website = t.get("website") or t.get("contact:website")
            if not email and website:
                email = email_finder.extract_email(website, budget)
            if not email or email in seen:
                continue
            seen.add(email)
            out.append({
                "segment": segment, "category": category, "company_name": name,
                "owner_name": None, "email": email,
                "phone": t.get("phone") or t.get("contact:phone"),
                "website": website, "linkedin": None, "industry": category, "city": city,
            })
    return out


def fetch_commercial_leads(count: int) -> list[dict]:
    if not is_enabled():
        return []
    budget, seen, out = [_SCRAPE_BUDGET], set(), []
    per = max(5, count // max(1, len(COMMERCIAL_OSM)))
    for cat, sels in COMMERCIAL_OSM.items():
        if len(out) >= count:
            break
        out.extend(_collect(sels, cat, "commercial", per, budget, seen))
    return out[:count]


def fetch_restaurants(count: int) -> list[dict]:
    if not is_enabled():
        return []
    rows = _collect(RESTAURANT_OSM, "Restaurant", "commercial", count, [_SCRAPE_BUDGET], set())
    return [{
        "kind": "prospect", "name": r["company_name"], "owner_manager": None,
        "website": r["website"], "menu_url": None, "instagram": None,
        "email": r["email"], "phone": r["phone"], "cuisine": None, "city": r["city"],
        "pain_points": "Research before outreach",
    } for r in rows]
