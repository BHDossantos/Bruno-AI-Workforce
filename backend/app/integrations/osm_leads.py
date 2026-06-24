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

# Several public Overpass mirrors — tried in order until one answers, so a single
# busy/blocking server never means "zero leads". kumi.systems is fast and lenient,
# so it's first; the slow maps.mail.ru mirror is the last resort.
OVERPASS_MIRRORS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
# A descriptive User-Agent is REQUIRED by Overpass servers — overpass-api.de
# returns HTTP 406 to requests sent with a default script User-Agent.
_OVERPASS_HEADERS = {
    "User-Agent": "BrunoAIWorkforce/1.0 (lead sourcing; contact brunodossantos707@gmail.com)",
    "Accept": "application/json",
}

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


def is_enabled() -> bool:
    return bool(settings.lead_states or settings.lead_cities)


def _states() -> list[str]:
    return [s.strip() for s in (settings.lead_states or "").split(",") if s.strip()]


def _cities() -> list[str]:
    return [c.strip() for c in (settings.lead_cities or "").split(",") if c.strip()]


def _areas() -> list[tuple[str, str]]:
    """(label, Overpass area-clause) to search. States (admin_level 4) take
    precedence and give a wide pool; otherwise fall back to cities (level 8)."""
    if _states():
        return [(s, f'area["name"="{s}"]["admin_level"="4"]->.a;') for s in _states()]
    return [(c, f'area["name"="{c}"]["admin_level"="8"]->.a;') for c in _cities()]


def _clean_email(e: str | None) -> str | None:
    return email_finder.clean_email(e)


_TIMEOUT = httpx.Timeout(30.0, connect=5.0)
# Email tags are selective, so an email-only query is fast even statewide.
_EMAIL_TAGS = ('["email"]', '["contact:email"]')
_SITE_TAGS = ('["website"]', '["contact:website"]')


def _post_overpass(body: str) -> list[dict]:
    """POST a query to Overpass, failing over across mirrors on any error/limit."""
    last = ""
    for url in OVERPASS_MIRRORS:
        try:
            r = httpx.post(url, data={"data": body}, headers=_OVERPASS_HEADERS, timeout=_TIMEOUT)
            if r.status_code != 200:  # busy/blocked/bad → just try the next mirror
                last = f"{url} -> HTTP {r.status_code}"
                continue
            return r.json().get("elements", [])
        except Exception as exc:  # pragma: no cover - network guard
            last = f"{url} -> {exc}"
            continue
    log.warning("All Overpass mirrors failed: %s", last)
    return []


def _build(area_head: str, selectors: list[str], tags: tuple, cap: int) -> str:
    parts = "".join(f"{s}{tag}(area.a);" for s in selectors for tag in tags)
    return f'[out:json][timeout:25];{area_head}(' + parts + f');out tags {cap};'


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
    """Pull up to ``count`` leads with real emails across the configured areas.

    Pass 1 grabs email-tagged businesses (instant, and selective enough to be
    fast even statewide). Pass 2 fills any shortfall by scraping website-only
    businesses within a small budget, so the run never hangs.
    """
    seen: set[str] = set()
    out: list[dict] = []
    areas = _areas()

    # Pass 1 — email-tagged businesses across each area (no scraping needed).
    for label, head in areas:
        if len(out) >= count:
            break
        for el in _post_overpass(_build(head, selectors, _EMAIL_TAGS, 200)):
            t = el.get("tags", {})
            if not t.get("name"):
                continue
            email = _clean_email(t.get("contact:email") or t.get("email"))
            if not email or email in seen:
                continue
            seen.add(email)
            out.append(_row(t, email, label, segment))
            if len(out) >= count:
                break

    # Pass 2 — website-only businesses, scraped to fill the shortfall (bounded).
    if len(out) < count:
        budget = [_SCRAPE_BUDGET]
        for label, head in areas:
            if len(out) >= count or budget[0] <= 0:
                break
            for el in _post_overpass(_build(head, selectors, _SITE_TAGS, 120)):
                if len(out) >= count or budget[0] <= 0:
                    break
                t = el.get("tags", {})
                website = t.get("website") or t.get("contact:website")
                if not t.get("name") or not website:
                    continue
                email = email_finder.extract_email(website, budget)
                if not email or email in seen:
                    continue
                seen.add(email)
                out.append(_row(t, email, label, segment))

    return out[:count]


def _row(t: dict, email: str, area_label: str, segment: str) -> dict:
    cat = _category_for(t)
    # Prefer the business's own city tag; fall back to the searched area label.
    city = t.get("addr:city") or area_label
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
