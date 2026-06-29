"""Free real-lead sourcing via OpenStreetMap (Overpass API).

Finds real local businesses by category and city from OpenStreetMap — no API key,
no cost — preferring each business's published email tag and falling back to the
shared website email-finder. Produces real leads with real, deliverable emails at
$0. Set LEAD_CITIES to control the search areas.
"""
from __future__ import annotations

import logging

import httpx

from ..config import settings
from . import email_finder

log = logging.getLogger("bruno.osm")

# Several public Overpass mirrors — tried in order until one answers, so a single
# busy/blocking server never means "zero leads". kumi.systems is fast and lenient,
# so it's first; the slow maps.mail.ru mirror is the last resort.
OVERPASS_MIRRORS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
# A descriptive User-Agent is REQUIRED by Overpass servers — overpass-api.de
# returns HTTP 406 to requests sent with a default script User-Agent.
_OVERPASS_HEADERS = {
    "User-Agent": "BrunoAIWorkforce/1.0 (lead sourcing; contact brunodossantos707@gmail.com)",
    "Accept": "application/json",
}

# Commercial-insurance prospect categories → OpenStreetMap selectors. Broad on
# purpose: the wider the category net, the more real businesses we keep finding in
# the same states before the email-tagged pool is exhausted.
COMMERCIAL_OSM = {
    "Restaurant": ['node["amenity"~"restaurant|cafe|fast_food|bar|pub|biergarten|food_court|ice_cream"]'],
    "Contractor": ['node["craft"~"plumber|electrician|carpenter|hvac|roofer|painter|builder|tiler|plasterer|insulation|stonemason|metal_construction|scaffolder|window_construction|sawmill|floorer|handicraft"]'],
    "Retail store": ['node["shop"~"convenience|clothes|hardware|florist|gift|bakery|butcher|jewelry|shoes|furniture|electronics|mobile_phone|bicycle|sports|toys|pet|stationery|books|optician|deli|greengrocer|wine|alcohol|cosmetics|variety_store|department_store|supermarket|doityourself|trade"]'],
    "Real estate agency": ['node["office"~"estate_agent|property_management"]'],
    "Medical office": ['node["amenity"~"clinic|doctors|dentist|veterinary|pharmacy"]',
                       'node["healthcare"~"physiotherapist|psychotherapist|chiropractor|optometrist|podiatrist|dentist|doctor"]'],
    "Landscaper": ['node["craft"="gardener"]', 'node["shop"="garden_centre"]',
                   'node["landuse"="plant_nursery"]'],
    "Auto services": ['node["shop"~"car_repair|car|tyres|car_parts|motorcycle"]',
                      'node["amenity"~"fuel|car_wash|car_rental"]'],
    "Beauty & wellness": ['node["shop"~"hairdresser|beauty|massage|nails|tattoo"]',
                          'node["leisure"~"fitness_centre|spa"]', 'node["amenity"="gym"]'],
    "Professional services": ['node["office"~"lawyer|accountant|insurance|company|it|financial|consulting|architect|engineer|tax_advisor|employment_agency|advertising_agency|notary|surveyor"]'],
    "Hospitality": ['node["tourism"~"hotel|guest_house|motel|hostel|apartment|chalet"]'],
    "Trades & industrial": ['node["shop"~"trade|building_materials|hvac|electrical"]',
                            'node["craft"~"electronics_repair|sun_protection|key_cutter|locksmith|cleaning"]'],
    "Childcare & education": ['node["amenity"~"childcare|kindergarten|driving_school|language_school|music_school|prep_school"]'],
    "Funeral & specialty": ['node["shop"~"funeral_directors|pawnbroker|laundry|dry_cleaning|travel_agency|copyshop|locksmith"]'],
}
RESTAURANT_OSM = ['node["amenity"~"restaurant|cafe|bar|pub|fast_food"]']

# Education institutions for the Foundation's School Partnership agent — real
# schools/universities/conservatories/community centers (node + area mappings).
_EDU_FILTER = "school|college|university|kindergarten|music_school|language_school"
EDUCATION_OSM = [
    f'node["amenity"~"{_EDU_FILTER}"]', f'way["amenity"~"{_EDU_FILTER}"]',
    'node["amenity"="community_centre"]', 'way["amenity"="community_centre"]',
]

# Bound website scraping per run so the agent stays fast (each scrape is a few
# HTTP fetches). Email-tagged businesses are instant; once that pool is exhausted
# in a region, scraping website-only businesses is how we keep finding NEW leads —
# so this is configurable (raise it to dig deeper per run).
def _scrape_budget() -> int:
    return max(0, int(getattr(settings, "osm_scrape_budget", 40) or 0))


def is_enabled() -> bool:
    return bool(settings.lead_states or settings.lead_cities)


def _states() -> list[str]:
    return [s.strip() for s in (settings.lead_states or "").split(",") if s.strip()]


def _cities() -> list[str]:
    return [c.strip() for c in (settings.lead_cities or "").split(",") if c.strip()]


def _areas() -> list[tuple[str, str]]:
    """(label, Overpass area-clause) to search. States (admin_level 4) take
    precedence and give a wide pool; otherwise fall back to cities (level 8)."""
    if _states():
        return [(s, f'area["name"="{s}"]["admin_level"="4"]->.a;') for s in _states()]
    return [(c, f'area["name"="{c}"]["admin_level"="8"]->.a;') for c in _cities()]


# ── Geography scopes (US + Europe) ──────────────────────────────────────────
US_STATES = [
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
    "Connecticut", "Delaware", "Florida", "Georgia", "Hawaii", "Idaho", "Illinois",
    "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana", "Maine", "Maryland",
    "Massachusetts", "Michigan", "Minnesota", "Mississippi", "Missouri", "Montana",
    "Nebraska", "Nevada", "New Hampshire", "New Jersey", "New Mexico", "New York",
    "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon", "Pennsylvania",
    "Rhode Island", "South Carolina", "South Dakota", "Tennessee", "Texas", "Utah",
    "Vermont", "Virginia", "Washington", "West Virginia", "Wisconsin", "Wyoming",
]
EUROPE_COUNTRIES = [
    "United Kingdom", "Ireland", "Germany", "France", "Spain", "Italy",
    "Netherlands", "Portugal", "Belgium", "Switzerland", "Austria", "Sweden",
    "Denmark", "Norway", "Finland", "Poland", "Czechia",
]
# Worldwide reach for businesses that sell globally (BnB Global consulting +
# SavoryMind). English-friendly, high-business-density countries across every
# region, so a "global" scope truly sweeps the world (rotated over days).
WORLD_COUNTRIES = EUROPE_COUNTRIES + [
    "Canada", "Mexico", "Brazil", "Argentina", "Chile", "Colombia",
    "Australia", "New Zealand", "Singapore", "India", "Japan", "South Korea",
    "United Arab Emirates", "Israel", "South Africa", "Nigeria", "Kenya",
    "Philippines", "Indonesia", "Malaysia", "Thailand", "Vietnam",
    "Greece", "Romania", "Hungary", "Croatia", "Estonia", "Lithuania",
]


def _spec(name: str, level: str) -> tuple[str, str]:
    return (name, f'area["name"="{name}"]["admin_level"="{level}"]->.a;')


def scope_areas(scope: str) -> list[tuple[str, str]]:
    """Expand a scope keyword/list into Overpass areas. Countries are admin_level
    2, US states level 4. Accepts 'us' | 'eu' | 'us_eu' | comma-separated names."""
    s = (scope or "").strip().lower()
    if s in ("us", "usa", "united states"):
        return [_spec(x, "4") for x in US_STATES]
    if s in ("eu", "europe"):
        return [_spec(x, "2") for x in EUROPE_COUNTRIES]
    if s in ("global", "worldwide", "world"):
        # Truly worldwide: US states + a broad set of countries across every region.
        return [_spec(x, "4") for x in US_STATES] + [_spec(x, "2") for x in WORLD_COUNTRIES]
    if s in ("us_eu", "us+eu"):
        return [_spec(x, "4") for x in US_STATES] + [_spec(x, "2") for x in EUROPE_COUNTRIES]
    return [_spec(x.strip(), "4") for x in (scope or "").split(",") if x.strip()]


def _rotate(areas: list, n: int) -> list:
    """Pick a rotating window of n areas (by day-of-year) so a large scope sweeps
    everything over time without timing out a single Overpass run."""
    if n <= 0 or len(areas) <= n:
        return areas
    from datetime import date
    start = (date.today().timetuple().tm_yday * n) % len(areas)
    return [areas[(start + i) % len(areas)] for i in range(n)]


def _scoped_areas(scope: str | None) -> list[tuple[str, str]]:
    if scope:
        return _rotate(scope_areas(scope), settings.lead_areas_per_run)
    return _areas()


def _clean_email(e: str | None) -> str | None:
    return email_finder.clean_email(e)


_TIMEOUT = httpx.Timeout(30.0, connect=5.0)
# Email tags are selective, so an email-only query is fast even statewide.
_EMAIL_TAGS = ('["email"]', '["contact:email"]')
_SITE_TAGS = ('["website"]', '["contact:website"]')


def _post_overpass(body: str) -> list[dict]:
    """POST a query to Overpass, failing over across mirrors on any error/limit."""
    last = ""
    for url in OVERPASS_MIRRORS:
        try:
            r = httpx.post(url, data={"data": body}, headers=_OVERPASS_HEADERS, timeout=_TIMEOUT)
            if r.status_code != 200:  # busy/blocked/bad → just try the next mirror
                last = f"{url} -> HTTP {r.status_code}"
                continue
            return r.json().get("elements", [])
        except Exception as exc:  # pragma: no cover - network guard
            last = f"{url} -> {exc}"
            continue
    log.warning("All Overpass mirrors failed: %s", last)
    return []


def _build(area_head: str, selectors: list[str], tags: tuple, cap: int) -> str:
    parts = "".join(f"{s}{tag}(area.a);" for s in selectors for tag in tags)
    return f'[out:json][timeout:25];{area_head}(' + parts + f');out tags {cap};'


def _category_for(t: dict, default: str = "Commercial") -> str:
    """Best-effort business category from OSM tags (for the lead record)."""
    if t.get("amenity") in {"restaurant", "cafe", "fast_food", "bar", "pub"}:
        return "Restaurant"
    if t.get("craft"):
        return "Contractor"
    if t.get("office"):
        return "Professional services"
    if t.get("tourism"):
        return "Hospitality"
    if t.get("amenity") in {"clinic", "doctors", "dentist", "veterinary", "pharmacy"}:
        return "Medical office"
    if t.get("shop"):
        return "Retail store"
    return default


def _harvest(selectors: list[str], segment: str, count: int,
             areas: list[tuple[str, str]] | None = None) -> list[dict]:
    """Pull up to ``count`` leads with real emails across the given areas (or the
    configured fallback areas).

    Pass 1 grabs email-tagged businesses (instant, and selective enough to be
    fast even statewide). Pass 2 fills any shortfall by scraping website-only
    businesses within a small budget, so the run never hangs.
    """
    seen: set[str] = set()
    out: list[dict] = []
    areas = areas if areas is not None else _areas()

    # Pass 1 — email-tagged businesses across each area (no scraping needed).
    for label, head in areas:
        if len(out) >= count:
            break
        for el in _post_overpass(_build(head, selectors, _EMAIL_TAGS, 200)):
            t = el.get("tags", {})
            if not t.get("name"):
                continue
            email = _clean_email(t.get("contact:email") or t.get("email"))
            if not email or email in seen:
                continue
            seen.add(email)
            out.append(_row(t, email, label, segment))
            if len(out) >= count:
                break

    # Pass 2 — website-only businesses, scraped to fill the shortfall (bounded).
    if len(out) < count:
        budget = [_scrape_budget()]
        for label, head in areas:
            if len(out) >= count or budget[0] <= 0:
                break
            for el in _post_overpass(_build(head, selectors, _SITE_TAGS, 120)):
                if len(out) >= count or budget[0] <= 0:
                    break
                t = el.get("tags", {})
                website = t.get("website") or t.get("contact:website")
                if not t.get("name") or not website:
                    continue
                email = email_finder.extract_email(website, budget)
                if not email or email in seen:
                    continue
                seen.add(email)
                out.append(_row(t, email, label, segment))

    return out[:count]


def _row(t: dict, email: str, area_label: str, segment: str) -> dict:
    cat = _category_for(t)
    # Prefer the business's own city tag; fall back to the searched area label.
    city = t.get("addr:city") or area_label
    return {
        "segment": segment, "category": cat, "company_name": t.get("name"),
        "owner_name": None, "email": email,
        "phone": t.get("phone") or t.get("contact:phone"),
        "website": t.get("website") or t.get("contact:website"),
        "linkedin": None, "industry": cat, "city": city,
    }


def _all_commercial_selectors() -> list[str]:
    sels: list[str] = []
    for v in COMMERCIAL_OSM.values():
        sels.extend(v)
    return sels


def fetch_commercial_leads(count: int, scope: str | None = None) -> list[dict]:
    if not (is_enabled() or (scope and settings.wider_lead_sourcing)):
        return []  # master gate (tests: empty LEAD_STATES + flag off → no network)
    areas = _scoped_areas(scope)
    if not areas:
        return []
    return _harvest(_all_commercial_selectors(), "commercial", count, areas)


def fetch_education_leads(count: int, scope: str | None = None) -> list[dict]:
    """Real education institutions (schools/universities/conservatories/community
    centers) for foundation school-partnership outreach — not generic businesses."""
    if not (is_enabled() or (scope and settings.wider_lead_sourcing)):
        return []
    areas = _scoped_areas(scope)
    if not areas:
        return []
    rows = _harvest(EDUCATION_OSM, "school_partner", count, areas)
    for r in rows:
        r["category"] = "Education institution"
        r["industry"] = "Education"
    return rows


def fetch_restaurants(count: int, scope: str | None = None) -> list[dict]:
    if not (is_enabled() or (scope and settings.wider_lead_sourcing)):
        return []  # master gate (tests: empty LEAD_STATES + flag off → no network)
    areas = _scoped_areas(scope)
    if not areas:
        return []
    rows = _harvest(RESTAURANT_OSM, "commercial", count, areas)
    return [{
        "kind": "prospect", "name": r["company_name"], "owner_manager": None,
        "website": r["website"], "menu_url": None, "instagram": None,
        "email": r["email"], "phone": r["phone"], "cuisine": None, "city": r["city"],
        "pain_points": "Research before outreach",
    } for r in rows]
