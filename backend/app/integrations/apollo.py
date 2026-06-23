"""Apollo.io B2B sourcing + enrichment.

Implements live people/organization search against the Apollo REST API. Used to
source commercial insurance prospects and restaurant decision-makers. Returns
``[]`` (so callers fall back to synthetic data) when ``APOLLO_API_KEY`` is unset
or the API errors.

Docs: https://docs.apollo.io/reference/people-search
"""
from __future__ import annotations

import logging

import httpx

from ..config import settings

log = logging.getLogger("bruno.apollo")
_BASE = "https://api.apollo.io/api/v1"

# Owner/decision-maker titles worth targeting for SMB outreach.
OWNER_TITLES = ["Owner", "Founder", "President", "CEO", "Managing Partner", "Principal"]


def is_configured() -> bool:
    return bool(settings.apollo_api_key)


def _post(path: str, payload: dict) -> dict:
    headers = {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        "X-Api-Key": settings.apollo_api_key,
    }
    resp = httpx.post(f"{_BASE}{path}", json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def search_people(*, titles: list[str], keywords: str = "", locations: list[str] | None = None,
                  per_page: int = 25, page: int = 1) -> list[dict]:
    """Search Apollo for people and map them to a flat contact dict."""
    if not is_configured():
        return []
    payload = {
        "person_titles": titles,
        "q_keywords": keywords,
        "page": page,
        "per_page": min(per_page, 100),
    }
    if locations:
        payload["person_locations"] = locations
    try:
        data = _post("/mixed_people/search", payload)
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("Apollo people search failed: %s", exc)
        return []

    out = []
    for p in data.get("people", []):
        org = p.get("organization") or {}
        out.append({
            "owner_name": p.get("name") or " ".join(filter(None, [p.get("first_name"), p.get("last_name")])),
            "title": p.get("title"),
            "company_name": org.get("name"),
            "email": p.get("email"),  # may be locked until enriched
            "phone": (p.get("phone_numbers") or [{}])[0].get("sanitized_number") if p.get("phone_numbers") else None,
            "website": org.get("website_url"),
            "linkedin": p.get("linkedin_url"),
            "industry": org.get("industry"),
            "city": p.get("city") or org.get("city"),
        })
    return out


def fetch_commercial_leads(count: int) -> list[dict]:
    """Source ~``count`` commercial insurance prospects (business owners)."""
    if not is_configured():
        return []
    leads: list[dict] = []
    page = 1
    # Bias toward SMBs that commonly need commercial insurance.
    keywords = "contractor OR restaurant OR medical OR real estate OR landscaping OR retail OR construction"
    while len(leads) < count and page <= 8:
        batch = search_people(titles=OWNER_TITLES, keywords=keywords, per_page=50, page=page)
        if not batch:
            break
        for b in batch:
            b["segment"] = "commercial"
            b["category"] = (b.get("industry") or "Commercial")
            leads.append(b)
        page += 1
    return leads[:count]


HIRING_TITLES = ["Technical Recruiter", "Recruiter", "Talent Acquisition", "Head of Talent",
                 "VP Engineering", "CTO", "Head of Engineering", "Engineering Manager"]


def find_hiring_contact(company: str) -> dict | None:
    """Best-effort: find a recruiter / hiring manager at ``company`` with an email."""
    if not is_configured() or not company:
        return None
    people = search_people(titles=HIRING_TITLES, keywords=company, per_page=10, page=1)
    for p in people:
        if p.get("email"):
            return p
    return people[0] if people else None


def fetch_restaurant_contacts(count: int) -> list[dict]:
    """Source ~``count`` restaurant owners/managers for SavoryMind outreach."""
    if not is_configured():
        return []
    contacts: list[dict] = []
    page = 1
    while len(contacts) < count and page <= 8:
        batch = search_people(
            titles=["Owner", "General Manager", "Manager", "Founder"],
            keywords="restaurant OR cafe OR bar OR hospitality OR dining",
            per_page=50, page=page,
        )
        if not batch:
            break
        contacts.extend(batch)
        page += 1
    return contacts[:count]
