"""Free real job sourcing via the Remotive API (no key, no cost).

Remotive (https://remotive.com/api/remote-jobs) returns real, currently-open
remote roles as JSON. We search several executive/leadership terms, dedupe, and
map to the shared job shape so the Job Hunter agent scores real openings — with a
real apply URL for the one-click apply queue. Gated by ENABLE_FREE_JOBS so tests
never hit the network.
"""
from __future__ import annotations

import logging
import re

import httpx

from ..config import settings

log = logging.getLogger("bruno.jobs_free")
REMOTIVE = "https://remotive.com/api/remote-jobs"
_HEADERS = {"User-Agent": "BrunoAIWorkforce/1.0 (job search; +https://example.com)"}
_TIMEOUT = httpx.Timeout(20.0, connect=5.0)

# Executive / leadership search terms aligned to the candidate profile.
SEARCH_TERMS = [
    "director", "head of engineering", "vp engineering", "cto",
    "principal engineer", "engineering manager", "site reliability",
    "platform engineering", "cloud architect", "infrastructure",
]


def is_enabled() -> bool:
    return bool(settings.enable_free_jobs)


def _salary(s: str | None) -> int | None:
    """Best-effort parse of a salary string like '$180k - $220k' → 180000."""
    if not s:
        return None
    txt = s.lower().replace(",", "")
    m = re.search(r"\$?\s*(\d{2,3})\s*k", txt)
    if m:
        return int(m.group(1)) * 1000
    m = re.search(r"(\d{5,7})", txt)
    return int(m.group(1)) if m else None


def fetch_jobs(limit: int = 60) -> list[dict]:
    if not is_enabled():
        return []
    out: list[dict] = []
    seen: set[str] = set()
    for term in SEARCH_TERMS:
        if len(out) >= limit:
            break
        try:
            r = httpx.get(REMOTIVE, params={"search": term, "limit": 50},
                          headers=_HEADERS, timeout=_TIMEOUT)
            if r.status_code != 200:
                continue
            jobs = r.json().get("jobs", [])
        except Exception as exc:  # pragma: no cover - network guard
            log.warning("Remotive fetch failed (%s): %s", term, exc)
            continue
        for j in jobs:
            url = j.get("url")
            if not url or url in seen:
                continue
            seen.add(url)
            smin = _salary(j.get("salary"))
            out.append({
                "title": j.get("title") or "",
                "company": j.get("company_name") or "Unknown",
                "location": j.get("candidate_required_location") or "Remote",
                "remote": True,
                "salary_min": smin,
                "salary_max": None,
                "source": "remotive",
                "url": url,
                "description": re.sub(r"<[^>]+>", " ", j.get("description") or "")[:2000],
            })
            if len(out) >= limit:
                break
    return out
