"""SavoryMind value mapping — turn a restaurant's pain signal into a specific,
quantified outcome SavoryMind delivers, so the pitch leads with a concrete result
("lift average check 12–18%") instead of a vague "grow your revenue".

Pure + offline. Keyed by substring against the prospect's pain points.
"""
from __future__ import annotations

_VALUE: list[tuple[tuple[str, ...], str]] = [
    (("average ticket", "low ticket", "average check", "low check", "margin", "spend"),
     "menu engineering and smart pairings that lift the average check 12–18%"),
    (("review", "reputation", "rating", "feedback"),
     "turning your best dishes into review magnets and fixing the items dragging ratings down"),
    (("upsell", "point of sale", "pos", "add-on", "attach"),
     "AI pairing prompts that add a high-margin item to more tickets"),
    (("outdated menu", "menu", "pricing", "price"),
     "a data-driven menu redesign and pricing that grows revenue per cover"),
    (("no-show", "no show", "reservation", "booking", "empty", "slow shift"),
     "cutting no-shows and filling slow shifts with targeted offers"),
    (("online", "website", "digital", "ordering"),
     "a stronger online presence and ordering flow that converts browsers into covers"),
]
_DEFAULT = "menu intelligence that grows revenue per cover without adding headcount"


def value_for(pain: str | None) -> str:
    t = (pain or "").lower()
    for keys, val in _VALUE:
        if any(k in t for k in keys):
            return val
    return _DEFAULT


def best_insight(menu_insight: str | None, pain: str | None) -> str:
    """Lead the pitch with the AI menu insight when we have a real one; otherwise
    fall back to the quantified value for this restaurant's pain signal."""
    mi = (menu_insight or "").strip()
    # Skip placeholder/generic pains so we never lead with "research before outreach".
    if mi and "research" not in mi.lower() and "unknown" not in mi.lower():
        return mi
    return value_for(pain)


def hint_for(pain: str | None) -> str:
    """Prompt hint so the pitch leads with a specific, measurable SavoryMind outcome."""
    return ("LEAD WITH THIS OUTCOME — " + value_for(pain)
            + ". Make it concrete and owner-friendly (covers, average check, reviews, "
            "margins) — never ML jargon.")
