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
            "first_name": p.get("first_name"), "last_name": p.get("last_name"),
            "title": p.get("title"),
            "company_name": org.get("name"),
            "domain": org.get("primary_domain") or _domain(org.get("website_url")),
            "email": p.get("email"),  # usually locked until enriched
            "phone": (p.get("phone_numbers") or [{}])[0].get("sanitized_number") if p.get("phone_numbers") else None,
            "website": org.get("website_url"),
            "linkedin": p.get("linkedin_url"),
            "industry": org.get("industry"),
            "city": p.get("city") or org.get("city"),
        })
    return out


def _domain(url: str | None) -> str | None:
    if not url:
        return None
    from urllib.parse import urlparse
    host = (urlparse(url if "//" in url else f"//{url}").hostname or "").lower()
    return host[4:] if host.startswith("www.") else (host or None)


def _is_real(email: str | None) -> bool:
    """Apollo returns locked placeholders like 'email_not_unlocked@domain.com' for
    un-enriched contacts — treat those (and blanks) as no email."""
    e = (email or "").strip().lower()
    return bool(e) and "@" in e and "not_unlocked" not in e and "domain.com" not in e


def enrich_email(lead: dict) -> str | None:
    """Reveal a contact's verified email via Apollo People Enrichment (/people/match).
    Costs an Apollo credit per call. Returns the email or None; never raises."""
    if not is_configured():
        return None
    payload = {"first_name": lead.get("first_name"), "last_name": lead.get("last_name"),
               "organization_name": lead.get("company_name"), "domain": lead.get("domain"),
               "reveal_personal_emails": True}
    payload = {k: v for k, v in payload.items() if v}
    if not (payload.get("first_name") and (payload.get("domain") or payload.get("organization_name"))):
        return None
    try:
        person = (_post("/people/match", payload) or {}).get("person") or {}
        email = person.get("email")
        return email if _is_real(email) else None
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("Apollo enrich failed: %s", exc)
        return None


def _with_emails(leads: list[dict], budget: int) -> list[dict]:
    """Keep leads that already have a real email; for the rest, enrich up to
    ``budget`` to reveal one. Drops leads we still can't email."""
    out: list[dict] = []
    spent = 0
    for ld in leads:
        if _is_real(ld.get("email")):
            out.append(ld)
            continue
        if spent < budget:
            spent += 1
            email = enrich_email(ld)
            if email:
                ld["email"] = email
                out.append(ld)
    return out


# Tech decision-makers for BnB Global consulting (cloud/SRE/security/AI/managed-IT).
TECH_TITLES = ["CTO", "Chief Technology Officer", "VP Engineering", "VP Technology",
               "Head of Engineering", "Head of Platform", "Head of Infrastructure",
               "Head of DevOps", "Head of SRE", "Director of Engineering",
               "Director of Infrastructure", "Engineering Manager", "Founder", "CEO", "Co-Founder"]
TECH_KEYWORDS = ('software OR SaaS OR "software development" OR cloud OR fintech OR technology '
                 'OR platform OR "IT services" OR cybersecurity OR "data platform" OR '
                 'AI OR "machine learning" OR ecommerce OR healthtech')


def fetch_tech_leads(count: int, locations: list[str] | None = None) -> list[dict]:
    """Source ~``count`` TECH-company decision-makers for BnB Global consulting —
    real software/SaaS/cloud firms (not local restaurants/retail), with verified
    emails revealed via enrichment."""
    if not is_configured():
        return []
    leads: list[dict] = []
    page = 1
    while len(leads) < count * 2 and page <= 8:
        batch = search_people(titles=TECH_TITLES, keywords=TECH_KEYWORDS,
                              locations=locations, per_page=50, page=page)
        if not batch:
            break
        for b in batch:
            b["segment"] = "consulting"
            b["category"] = b.get("industry") or "Technology"
            leads.append(b)
        page += 1
    return _with_emails(leads, budget=count)[:count]


def fetch_commercial_leads(count: int, locations: list[str] | None = None) -> list[dict]:
    """Source ~``count`` commercial insurance prospects (business owners), with
    verified emails revealed via enrichment. ``locations`` keeps them in-territory
    (e.g. insurance → NH/MA/FL)."""
    if not is_configured():
        return []
    leads: list[dict] = []
    page = 1
    # Bias toward SMBs that commonly need commercial insurance.
    keywords = "contractor OR restaurant OR medical OR real estate OR landscaping OR retail OR construction"
    # Over-fetch a bit because enrichment drops contacts we can't get an email for.
    while len(leads) < count * 2 and page <= 8:
        batch = search_people(titles=OWNER_TITLES, keywords=keywords, locations=locations,
                              per_page=50, page=page)
        if not batch:
            break
        for b in batch:
            b["segment"] = "commercial"
            b["category"] = (b.get("industry") or "Commercial")
            leads.append(b)
        page += 1
    return _with_emails(leads, budget=count)[:count]


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


def fetch_restaurant_contacts(count: int, locations: list[str] | None = None) -> list[dict]:
    """Source ~``count`` restaurant owners/managers for SavoryMind outreach, with
    verified emails revealed via enrichment."""
    if not is_configured():
        return []
    contacts: list[dict] = []
    page = 1
    while len(contacts) < count * 2 and page <= 8:
        batch = search_people(
            titles=["Owner", "General Manager", "Manager", "Founder"],
            keywords="restaurant OR cafe OR bar OR hospitality OR dining",
            locations=locations, per_page=50, page=page,
        )
        if not batch:
            break
        contacts.extend(batch)
        page += 1
    return _with_emails(contacts, budget=count)[:count]
