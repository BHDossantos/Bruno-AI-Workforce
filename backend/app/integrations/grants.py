"""Grant discovery — Grants.gov public search API (US, free, no key).

The Foundation's Grant Research agent calls fetch_grants(); results are scored by
mission fit upstream. Everything is guarded: any network/parse error (or the API
being disabled) degrades to a small curated starter list so the agent still
produces something, and never raises.
"""
from __future__ import annotations

import logging

import httpx

from ..config import settings

log = logging.getLogger("bruno.grants")

_SEARCH_URL = "https://api.grants.gov/v1/api/search2"
_TIMEOUT = httpx.Timeout(20.0, connect=5.0)

# Keywords spanning the foundation's pillars, used to query Grants.gov.
MISSION_KEYWORDS = [
    "education", "scholarship", "music", "arts", "youth", "mentorship",
    "STEM", "technology", "digital literacy", "community", "leadership",
]


def is_enabled() -> bool:
    return bool(settings.grants_gov_enabled)


def _detail_url(opp_id: str | None) -> str | None:
    return f"https://www.grants.gov/search-results-detail/{opp_id}" if opp_id else None


def _fetch_keyword(keyword: str, rows: int) -> list[dict]:
    """One Grants.gov search2 call for posted opportunities matching a keyword."""
    payload = {"keyword": keyword, "oppStatuses": "posted", "rows": rows}
    try:
        r = httpx.post(_SEARCH_URL, json=payload, timeout=_TIMEOUT)
        if r.status_code != 200:
            log.warning("grants.gov %s -> %s", keyword, r.status_code)
            return []
        hits = ((r.json() or {}).get("data") or {}).get("oppHits") or []
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("grants.gov search failed (%s): %s", keyword, exc)
        return []
    out = []
    for h in hits:
        oid = str(h.get("id") or h.get("number") or "")
        out.append({
            "title": h.get("title"),
            "funder": h.get("agency") or h.get("agencyCode"),
            "source": "grants_gov",
            "external_id": oid or None,
            "url": _detail_url(oid),
            "deadline": h.get("closeDate"),  # MM/DD/YYYY string; parsed upstream
            "eligibility": None,
            "summary": None,
            "keyword": keyword,
        })
    return out


def fetch_grants(limit: int = 30) -> list[dict]:
    """Posted opportunities across the foundation's mission keywords (deduped)."""
    if not is_enabled():
        return _curated(limit)
    seen: set[str] = set()
    out: list[dict] = []
    per_kw = max(2, limit // max(1, len(MISSION_KEYWORDS)) + 1)
    for kw in MISSION_KEYWORDS:
        for g in _fetch_keyword(kw, per_kw):
            key = g.get("external_id") or (g.get("title") or "")
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(g)
            if len(out) >= limit:
                return out
    return out or _curated(limit)


def _curated(limit: int) -> list[dict]:
    """Offline starter list so the agent is useful before/without the live API."""
    if not settings.allow_synthetic_fallback:
        return []
    base = [
        {"title": "Arts Education Project Grant", "funder": "National Endowment for the Arts",
         "category": "Music & Arts"},
        {"title": "Music Education for Underserved Communities", "funder": "Mr. Holland's Opus Foundation",
         "category": "Music & Arts"},
        {"title": "STEM Access for Underserved Youth", "funder": "Corporate STEM Fund",
         "category": "Technology & Innovation"},
        {"title": "Digital Literacy & Coding Pathways", "funder": "Technology Education Fund",
         "category": "Technology & Innovation"},
        {"title": "Community Scholarship Initiative", "funder": "Community Foundation",
         "category": "Education & Scholarships"},
        {"title": "First-Generation College Scholarship Fund", "funder": "Education Opportunity Trust",
         "category": "Education & Scholarships"},
        {"title": "Youth Mentorship & Leadership", "funder": "Youth Development Fund",
         "category": "Opportunity & Leadership"},
        {"title": "Neighborhood Community Development Grant", "funder": "Local Initiatives Support Corp",
         "category": "Community Development"},
        {"title": "STEM Access for Underserved Youth", "funder": "Corporate STEM Fund",
         "category": "Technology & Innovation"},
        {"title": "Community Scholarship Initiative", "funder": "Community Foundation",
         "category": "Education & Scholarships"},
        {"title": "Youth Mentorship & Leadership", "funder": "Youth Development Fund",
         "category": "Opportunity & Leadership"},
    ]
    out = []
    for i in range(limit):
        b = base[i % len(base)]
        out.append({**b, "source": "curated", "external_id": f"curated-{i}",
                    "url": None, "deadline": None, "eligibility": None,
                    "summary": "Starter opportunity — wire Grants.gov / EU portals for live data.",
                    "keyword": b["category"]})
    return out
