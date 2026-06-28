"""Real-lead sourcing via Google Places API (Text Search).

Google gives a recurring free credit that covers this volume. Places returns the
business's real website, from which we extract a contact email via email_finder.
Key-gated: active only when GOOGLE_PLACES_API_KEY is set.
"""
from __future__ import annotations

import logging

import httpx

from ..config import settings
from . import email_finder, osm_leads

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


def _areas(scope: str | None = None) -> list[str]:
    """Place names to search, each swept statewide (e.g. "restaurants in
    Massachusetts"). Honors the same geography as OSM: the per-business scope
    first (rotated like OSM so a big scope sweeps over days), then whole states,
    and only finally a narrow city list if one is explicitly configured."""
    if scope:
        names = [label for label, _ in osm_leads.scope_areas(scope)]
        return osm_leads._rotate(names, settings.lead_areas_per_run)
    states = [s.strip() for s in (settings.lead_states or "").split(",") if s.strip()]
    if states:
        return states
    return [c.strip() for c in (settings.lead_cities or "").split(",") if c.strip()]


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
             budget: list[int], seen: set, scope: str | None = None) -> list[dict]:
    out: list[dict] = []
    for area in _areas(scope):
        for q in queries:
            if len(out) >= count:
                return out
            for p in _search(f"{q} in {area}"):
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
                    # Prefer the business's own city; fall back to the searched area.
                    "linkedin": None, "industry": category_of(q),
                    "city": (p.get("formattedAddress") or "").split(",")[1].strip()
                            if (p.get("formattedAddress") or "").count(",") >= 1 else area,
                })
                if len(out) >= count:
                    return out
    return out


def fetch_commercial_leads(count: int, scope: str | None = None) -> list[dict]:
    if not is_configured() or not _areas(scope):
        return []
    return _collect(COMMERCIAL_QUERIES, lambda q: q.title(), "commercial", count,
                    [_SCRAPE_BUDGET], set(), scope=scope)


def fetch_restaurants(count: int, scope: str | None = None) -> list[dict]:
    if not is_configured() or not _areas(scope):
        return []
    rows = _collect(["restaurants", "cafes", "wine bars"], lambda q: "Restaurant",
                    "commercial", count, [_SCRAPE_BUDGET], set(), scope=scope)
    return [{
        "kind": "prospect", "name": r["company_name"], "owner_manager": None,
        "website": r["website"], "menu_url": None, "instagram": None,
        "email": r["email"], "phone": r["phone"], "cuisine": None, "city": r["city"],
        "pain_points": "Research before outreach",
    } for r in rows]
