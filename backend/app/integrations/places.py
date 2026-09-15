"""Real-lead sourcing via Google Places API (Text Search).

Places returns the business's real website, from which we extract a contact email
via email_finder. But Text Search bills PER REQUEST at Google's most expensive tier
(we ask for phone + website), and the sweep re-runs the same 14 queries × areas every
pass — which ran up ~$2.5k/mo. So Places is OFF unless PLACES_ENABLED=true, and when
on it's guarded two ways (see _may_search): a per-"query in area" cooldown skips a
sweep already run recently, and a hard monthly request cap backstops a runaway.
Key-gated: active only when GOOGLE_PLACES_API_KEY is set AND places_enabled is on.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

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
    # Both gates: the key must exist AND Places must be explicitly enabled. Off by
    # default so a stray key can never resume the expensive sweep on its own.
    return bool(settings.google_places_api_key) and bool(settings.places_enabled)


def _may_search(query_key: str) -> bool:
    """Cost gate for ONE Text Search request. Returns True (and logs the request) only
    when both guardrails pass: the monthly request cap isn't hit, and this exact
    "query in area" wasn't already searched within the cooldown window. Uses its own
    short-lived session; on any DB error it fails CLOSED (skip) — a missed sweep is
    cheap, an unmetered one is not."""
    from ..database import SessionLocal
    from ..models import PlacesSearchLog
    from sqlalchemy import func as _func

    try:
        with SessionLocal() as db:
            # (a) Monthly cap — count requests logged since the 1st of this month (UTC).
            cap = max(0, int(settings.places_monthly_request_cap or 0))
            month_start = datetime.now(timezone.utc).replace(
                day=1, hour=0, minute=0, second=0, microsecond=0)
            used = (db.query(_func.count()).select_from(PlacesSearchLog)
                    .filter(PlacesSearchLog.created_at >= month_start).scalar() or 0)
            if cap and used >= cap:
                log.warning("Places monthly request cap reached (%s) — skipping search", cap)
                return False
            # (b) Per-query cooldown — skip if this exact sweep ran within the window.
            cooldown = max(0, int(settings.places_query_cooldown_days or 0))
            if cooldown:
                cutoff = datetime.now(timezone.utc) - timedelta(days=cooldown)
                recent = (db.query(PlacesSearchLog)
                          .filter(PlacesSearchLog.query_key == query_key,
                                  PlacesSearchLog.created_at >= cutoff).first())
                if recent:
                    return False
            db.add(PlacesSearchLog(query_key=query_key))
            db.commit()
            return True
    except Exception as exc:  # pragma: no cover - DB guard; fail closed to protect spend
        log.warning("Places cost gate unavailable (%s) — skipping search to be safe", exc)
        return False


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
    # Cost gate: skip (and don't bill) a query on cooldown or over the monthly cap.
    if not _may_search(query):
        return []
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
