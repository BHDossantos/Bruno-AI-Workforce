"""Free real-lead sourcing via OpenStreetMap (Overpass API) + website email lookup.

Finds real local businesses by category and city from OpenStreetMap — no API key,
no cost — preferring each business's published email tag and falling back to
extracting a contact email from its website. Produces real leads with real,
deliverable emails at $0. Set LEAD_CITIES to control the search areas.
"""
from __future__ import annotations

import logging
import re

import httpx

from ..config import settings

log = logging.getLogger("bruno.osm")
OVERPASS = "https://overpass-api.de/api/interpreter"
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_BAD = ("example.", "@2x", ".png", ".jpg", ".gif", "sentry", "wixpress", "your@",
        "email@", "domain.com", "@sentry", "godaddy", "u003e")

# Commercial-insurance prospect categories → OpenStreetMap selectors.
COMMERCIAL_OSM = {
    "Restaurant": ['node["amenity"="restaurant"]', 'node["amenity"="cafe"]'],
    "Contractor": ['node["craft"~"plumber|electrician|carpenter|hvac|roofer"]'],
    "Retail store": ['node["shop"~"convenience|clothes|hardware|florist|gift|bakery"]'],
    "Real estate agency": ['node["office"="estate_agent"]'],
    "Medical office": ['node["amenity"~"clinic|doctors|dentist"]'],
    "Landscaper": ['node["craft"="gardener"]', 'node["shop"="garden_centre"]'],
}
RESTAURANT_OSM = ['node["amenity"="restaurant"]', 'node["amenity"="cafe"]', 'node["amenity"="bar"]']

# Bound website scraping per run so the agent doesn't hang.
_SCRAPE_BUDGET = 50


def is_enabled() -> bool:
    return bool(settings.lead_cities)


def _cities() -> list[str]:
    return [c.strip() for c in settings.lead_cities.split(",") if c.strip()]


def _clean_email(e: str | None) -> str | None:
    if not e:
        return None
    e = e.strip().lower().strip(".,;:)(<>\"'")
    if "@" not in e or any(b in e for b in _BAD):
        return None
    domain = e.split("@")[-1]
    return e if "." in domain else None


def _query(selectors: list[str], city: str) -> list[dict]:
    parts = []
    for s in selectors:
        for tag in ('["contact:email"]', '["email"]', '["website"]', '["contact:website"]'):
            parts.append(f"{s}{tag}(area.a);")
    body = f'[out:json][timeout:25];area["name"="{city}"]->.a;(' + "".join(parts) + ");out tags 80;"
    try:
        r = httpx.post(OVERPASS, data={"data": body}, timeout=45)
        r.raise_for_status()
        return r.json().get("elements", [])
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("Overpass query failed (%s): %s", city, exc)
        return []


def _email_from_website(url: str, budget: list[int]) -> str | None:
    if not url or budget[0] <= 0:
        return None
    if not url.startswith("http"):
        url = "https://" + url
    budget[0] -= 1
    for path in ("", "/contact", "/contact-us", "/about"):
        try:
            r = httpx.get(url.rstrip("/") + path, timeout=8, follow_redirects=True,
                          headers={"User-Agent": "Mozilla/5.0 (compatible; BrunoAI/1.0)"})
            for m in _EMAIL_RE.findall(r.text):
                e = _clean_email(m)
                if e:
                    return e
        except Exception:
            continue
    return None


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
                email = _email_from_website(website, budget)
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
    # Map to the restaurant dict shape used by the SavoryMind agent.
    return [{
        "kind": "prospect", "name": r["company_name"], "owner_manager": None,
        "website": r["website"], "menu_url": None, "instagram": None,
        "email": r["email"], "phone": r["phone"], "cuisine": None, "city": r["city"],
        "pain_points": "Research before outreach",
    } for r in rows]
