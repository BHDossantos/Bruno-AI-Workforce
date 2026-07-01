"""Insurance-need mapping — turn a prospect's business category into the SPECIFIC
coverage that category actually needs, so outreach speaks to their real risk
(a contractor → general liability + workers' comp; a restaurant → liquor liability;
a medical office → malpractice) instead of a generic "you need insurance" pitch.

Pure + offline. Keyed by substring so it's robust to category naming differences
across OSM, Apollo, and the synthetic fallback.
"""
from __future__ import annotations

# (category keywords) → the coverages that category most needs. Order matters:
# the first matching group wins, so put the most specific signals first.
_COMMERCIAL_NEEDS: list[tuple[tuple[str, ...], str]] = [
    (("contractor", "construction", "plumber", "electric", "roofer", "carpenter", "hvac", "builder", "landscap", "gardener"),
     "general liability, workers' compensation, commercial auto, and tools & equipment coverage"),
    (("restaurant", "cafe", "bar", "pub", "food", "bakery", "brewery"),
     "general and liquor liability, commercial property, and workers' compensation"),
    (("medical", "clinic", "dental", "dentist", "doctor", "veterinary", "vet", "pharmacy", "health"),
     "malpractice / professional liability, commercial property, and workers' compensation"),
    (("real estate", "estate agent", "property manag", "realtor"),
     "professional liability (errors & omissions), general liability, and property coverage"),
    (("trucking", "truck", "delivery", "moving", "logistics", "courier", "towing", "fleet"),
     "commercial auto (CAP) for the fleet, cargo coverage, and general liability"),
    (("car dealer", "dealership"),
     "commercial auto (CAP) for dealer/loaner vehicles, garage liability, and commercial property"),
    (("auto", "car repair", "tyre", "tire", "garage", "fuel", "mechanic", "motorcycle"),
     "garage liability, commercial auto (CAP) for shop vehicles, and workers' compensation"),
    (("beauty", "hairdress", "salon", "spa", "gym", "fitness", "wellness"),
     "professional and general liability plus commercial property coverage"),
    (("law", "lawyer", "attorney", "account", "financial", "consult", "agency", "it ", "tech", "professional", "office"),
     "professional liability (errors & omissions), cyber liability, and general liability"),
    (("hotel", "hospitality", "guest", "motel", "inn"),
     "general liability, commercial property, and liquor liability"),
    (("retail", "shop", "store", "boutique"),
     "general liability, commercial property, and business-interruption coverage"),
]
_COMMERCIAL_DEFAULT = "general liability, commercial property, and workers' compensation"

_PERSONAL_NEEDS: list[tuple[tuple[str, ...], str]] = [
    (("homeowner", "new home", "home", "mover", "purchase", "mortgage"),
     "home and auto coverage — bundling them usually saves money, so it's a great moment for a rate review"),
    (("auto", "car", "vehicle", "driver"),
     "auto coverage with the right liability limits — a quick rate review often beats their renewal"),
]
_PERSONAL_DEFAULT = "home and auto coverage — a quick rate review often uncovers savings"


def coverage_for(category: str | None, segment: str = "commercial") -> str:
    t = (category or "").lower()
    table = _PERSONAL_NEEDS if segment == "personal" else _COMMERCIAL_NEEDS
    default = _PERSONAL_DEFAULT if segment == "personal" else _COMMERCIAL_DEFAULT
    for keys, cov in table:
        if any(k in t for k in keys):
            return cov
    return default


def reason_for(category: str | None, segment: str = "commercial") -> str:
    """A specific, outreach-ready 'why they need us' line for this category."""
    cov = coverage_for(category, segment)
    label = category or ("This prospect" if segment == "personal" else "These businesses")
    if segment == "personal":
        return f"{label}: needs {cov}."
    return f"A {label.lower()} typically needs {cov}."
