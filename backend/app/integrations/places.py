"""Real-lead sourcing via Google Places API (Text Search).

Google gives a recurring free credit that covers this volume. Places returns the
business's real website, from which we extract a contact email via email_finder.
Key-gated: active only when GOOGLE_PLACES_API_KEY is set.
"""
from __future__ import annotations

import logging

import httpx

from ..config import settings
from . import email_finder

log = logging.getLogger("bruno.places")
_SEARCH = "https://places.googleapis.com/v1/places:searchText"
_FIELDS = "places.displayName,places.websiteUri,places.nationalPhoneNumber,places.formattedAddress"

COMMERCIAL_QUERIES = [
    "restaurants", "contractors", "plumbers", "electricians", "retail stores",
    "real estate agencies", "medical offices", "dentists", "landscapers",
    "auto repair shops", "law firms", "accounting firms", "gyms", "salons",
]
_SCRAPE_BUDGET = 60


def is_configured() -> bool:
    return bool(settings.google_places_api_key)


def _cities() -> list[str]:
    return [c.strip() for c in settings.lead_cities.split(",") if c.strip()]


def _search(query: str, max_results: int = 20) -> list[dict]:
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": settings.google_places_api_key,
        "X-Goog-FieldMask": _FIELDS,
    }
    try:
        r = httpx.post(_SEARCH, json={"textQuery": query, "maxResultCount": max_results},
                       headers=headers, timeout=30)
        r.raise_for_status()
        return r.json().get("places", [])
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("Places search failed (%s): %s", query, exc)
        return []


def _collect(queries: list[str], category_of, segment: str, count: int,
             budget: list[int], seen: set) -> list[dict]:
    out: list[dict] = []
    for city in _cities():
        for q in queries:
            if len(out) >= count:
                return out
            for p in _search(f"{q} in {city}"):
                website = p.get("websiteUri")
                if not website:
                    continue
                email = email_finder.extract_email(website, budget)
                if not email or email in seen:
                    continue
                seen.add(email)
                out.append({
                    "segment": segment, "category": category_of(q),
                    "company_name": (p.get("displayName") or {}).get("text"),
                    "owner_name": None, "email": email,
                    "phone": p.get("nationalPhoneNumber"), "website": website,
                    "linkedin": None, "industry": category_of(q), "city": city,
                })
                if len(out) >= count:
                    return out
    return out


def fetch_commercial_leads(count: int) -> list[dict]:
    if not is_configured() or not _cities():
        return []
    return _collect(COMMERCIAL_QUERIES, lambda q: q.title(), "commercial", count,
                    [_SCRAPE_BUDGET], set())


def fetch_restaurants(count: int) -> list[dict]:
    if not is_configured() or not _cities():
        return []
    rows = _collect(["restaurants", "cafes", "wine bars"], lambda q: "Restaurant",
                    "commercial", count, [_SCRAPE_BUDGET], set())
    return [{
        "kind": "prospect", "name": r["company_name"], "owner_manager": None,
        "website": r["website"], "menu_url": None, "instagram": None,
        "email": r["email"], "phone": r["phone"], "cuisine": None, "city": r["city"],
        "pain_points": "Research before outreach",
    } for r in rows]
