"""Live job sourcing (Indeed et al. via the JSearch aggregator).

JSearch (RapidAPI) aggregates listings from Indeed, LinkedIn, Glassdoor, ZipRecruiter
and company boards behind one API, which is the most practical way to pull real
executive postings server-side (Indeed has no open public search API). Returns
``[]`` so callers fall back to synthetic data when ``JOBS_API_KEY`` is unset or
the API errors.

Docs: https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch
"""
from __future__ import annotations

import logging

import httpx

from ..config import settings

log = logging.getLogger("bruno.jobs_api")


def is_configured() -> bool:
    return bool(settings.jobs_api_key)


def _search(query: str, pages: int = 1) -> list[dict]:
    headers = {
        "X-RapidAPI-Key": settings.jobs_api_key,
        "X-RapidAPI-Host": settings.jobs_api_host,
    }
    params = {"query": query, "num_pages": str(pages), "date_posted": "week"}
    resp = httpx.get(f"https://{settings.jobs_api_host}/search", headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json().get("data", [])


def _map(job: dict) -> dict:
    smin = job.get("job_min_salary")
    smax = job.get("job_max_salary")
    remote = bool(job.get("job_is_remote"))
    city = job.get("job_city") or ""
    state = job.get("job_state") or ""
    location = "Remote" if remote else ", ".join(filter(None, [city, state])) or job.get("job_country") or ""
    return {
        "title": job.get("job_title") or "",
        "company": job.get("employer_name"),
        "location": location,
        "remote": remote,
        "salary_min": int(smin) if smin else None,
        "salary_max": int(smax) if smax else None,
        "source": (job.get("job_publisher") or "indeed").lower(),
        "url": job.get("job_apply_link") or job.get("job_google_link"),
        "description": (job.get("job_description") or "")[:4000],
    }


def fetch_jobs(titles: list[str], limit: int = 80, location: str | None = None) -> list[dict]:
    """Query each target title (optionally biased to a location) and return
    mapped, de-duplicated jobs."""
    if not is_configured():
        return []
    seen: set[str] = set()
    out: list[dict] = []
    for title in titles:
        if len(out) >= limit:
            break
        query = f"{title} in {location}" if location else title
        try:
            for raw in _search(query, pages=1):
                mapped = _map(raw)
                key = (mapped["title"] + "|" + (mapped["company"] or "")).lower()
                if key in seen or not mapped["title"]:
                    continue
                seen.add(key)
                out.append(mapped)
        except Exception as exc:  # pragma: no cover - network guard
            log.warning("Jobs API search failed for '%s': %s", title, exc)
            continue
    return out[:limit]
