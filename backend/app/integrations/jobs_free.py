"""Free real job sourcing aggregated across several top remote-job boards.

No API keys, no cost — we only need the public listing + apply link. Sources:
Remotive, RemoteOK, Arbeitnow, Jobicy (and easily extensible). Results are
normalized, filtered to REMOTE roles that match the candidate's skills, and
deduped. Gated by ENABLE_FREE_JOBS so tests never hit the network.
"""
from __future__ import annotations

import logging
import re

import httpx

from ..config import settings

log = logging.getLogger("bruno.jobs_free")
_HEADERS = {"User-Agent": "BrunoAIWorkforce/1.0 (job search; +https://example.com)"}
_TIMEOUT = httpx.Timeout(20.0, connect=5.0)

# Only surface roles that fit the candidate's skills (exec IT/cloud leadership).
SKILL_TERMS = (
    "director", "head of", "vp ", "vice president", "chief", "cto", "principal",
    "engineering manager", "sre", "site reliability", "cloud", "infrastructure",
    "platform", "devops", "kubernetes", "reliability", "ai", "machine learning",
    "data platform", "architect",
)


def is_enabled() -> bool:
    return bool(settings.enable_free_jobs)


def _salary(s) -> int | None:
    if s is None:
        return None
    if isinstance(s, (int, float)) and s > 1000:
        return int(s)
    txt = str(s).lower().replace(",", "")
    m = re.search(r"\$?\s*(\d{2,3})\s*k", txt)
    if m:
        return int(m.group(1)) * 1000
    m = re.search(r"(\d{5,7})", txt)
    return int(m.group(1)) if m else None


def _strip_html(s: str | None) -> str:
    return re.sub(r"<[^>]+>", " ", s or "")[:2000]


def _fits(title: str, desc: str) -> bool:
    text = f"{title} {desc}".lower()
    return any(term in text for term in SKILL_TERMS)


def _get_json(url: str, **params):
    try:
        r = httpx.get(url, params=params or None, headers=_HEADERS, timeout=_TIMEOUT)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("job source failed %s: %s", url, exc)
        return None


def _remotive() -> list[dict]:
    out = []
    for term in ("director", "head of engineering", "cloud", "site reliability", "platform"):
        data = _get_json("https://remotive.com/api/remote-jobs", search=term, limit=50)
        for j in (data or {}).get("jobs", []):
            out.append({"title": j.get("title"), "company": j.get("company_name"),
                        "location": j.get("candidate_required_location") or "Remote",
                        "salary_min": _salary(j.get("salary")), "source": "remotive",
                        "url": j.get("url"), "description": _strip_html(j.get("description"))})
    return out


def _remoteok() -> list[dict]:
    data = _get_json("https://remoteok.com/api")
    out = []
    for j in data or []:
        if not isinstance(j, dict) or not j.get("position"):
            continue  # first element is a legal notice
        out.append({"title": j.get("position"), "company": j.get("company"),
                    "location": j.get("location") or "Remote",
                    "salary_min": _salary(j.get("salary_min")), "source": "remoteok",
                    "url": j.get("url") or j.get("apply_url"),
                    "description": _strip_html(j.get("description"))})
    return out


def _arbeitnow() -> list[dict]:
    data = _get_json("https://www.arbeitnow.com/api/job-board-api")
    out = []
    for j in (data or {}).get("data", []):
        if not j.get("remote", True):
            continue
        out.append({"title": j.get("title"), "company": j.get("company_name"),
                    "location": j.get("location") or "Remote", "salary_min": None,
                    "source": "arbeitnow", "url": j.get("url"),
                    "description": _strip_html(j.get("description"))})
    return out


def _jobicy() -> list[dict]:
    data = _get_json("https://jobicy.com/api/v2/remote-jobs", count=50)
    out = []
    for j in (data or {}).get("jobs", []):
        out.append({"title": j.get("jobTitle"), "company": j.get("companyName"),
                    "location": j.get("jobGeo") or "Remote",
                    "salary_min": _salary(j.get("annualSalaryMin")), "source": "jobicy",
                    "url": j.get("url"), "description": _strip_html(j.get("jobExcerpt"))})
    return out


_SOURCES = (_remotive, _remoteok, _arbeitnow, _jobicy)


def fetch_jobs(limit: int = 60) -> list[dict]:
    if not is_enabled():
        return []
    seen_urls: set[str] = set()
    seen_key: set[tuple] = set()
    out: list[dict] = []
    for src in _SOURCES:
        try:
            rows = src()
        except Exception as exc:  # pragma: no cover
            log.warning("job source %s errored: %s", src.__name__, exc)
            continue
        for r in rows:
            title, company, url = r.get("title"), r.get("company"), r.get("url")
            if not title or not url or url in seen_urls:
                continue
            key = (title.lower().strip(), (company or "").lower().strip())
            if key in seen_key:
                continue
            if not _fits(title, r.get("description", "")):
                continue  # remote roles that fit the candidate's skills only
            seen_urls.add(url)
            seen_key.add(key)
            out.append({
                "title": title, "company": company or "Unknown",
                "location": r.get("location") or "Remote", "remote": True,
                "salary_min": r.get("salary_min"), "salary_max": None,
                "source": r.get("source"), "url": url, "description": r.get("description") or "",
            })
            if len(out) >= limit:
                return out
    return out
