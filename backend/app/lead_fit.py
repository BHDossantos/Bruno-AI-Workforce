"""Fit/priority score for an insurance or consulting lead.

Estimates how good a prospect is from the signals we have today: reachability
(email/phone/website/LinkedIn — can we actually get the pitch in front of a human?)
plus fit signals (named decision-maker, high-value segment, qualifying reason).
Higher = work this one first, so the agents spend their effort on the strongest
prospects instead of the next row in the list. Richer signals (revenue, employee
count, tech stack, funding) light up when a paid source like Apollo is connected.

Works on either a sourcing dict (during sourcing) or a Lead ORM row (for the
schema computed field) — everything is read via ``getattr``/``get``.
"""
from __future__ import annotations

# Segments that are the explicit priority — commercial insurance and referral
# partners convert higher and stickier; consulting is the BnB Global engine.
_PRIORITY_SEGMENTS = {"commercial", "referral_partner", "consulting"}


def _get(obj, key):
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def score(lead) -> int:
    # In-market INBOUND leads (EverQuote quote requests / opt-in web leads) are the
    # single strongest signal — a real person actively shopping right now. They
    # outrank every cold-sourced prospect, so they hit the ceiling and sort first
    # even on fit-ranked views. We detect them by the hot score stamped on import
    # (or an everquote intake source).
    stored = _get(lead, "score") or 0
    intake = _get(lead, "intake") or {}
    in_market = stored >= 80 or (isinstance(intake, dict) and intake.get("source") == "everquote")
    if in_market:
        return 100

    s = 35
    # Reachability → we can actually pitch them.
    if _get(lead, "email"):
        s += 25
    if _get(lead, "phone"):
        s += 10
    if _get(lead, "website"):
        s += 8
    if _get(lead, "linkedin"):
        s += 6
    # Fit signals → worth the agent's time.
    if _get(lead, "owner_name"):
        s += 8   # named decision-maker → personalized, higher-reply outreach
    if _get(lead, "segment") in _PRIORITY_SEGMENTS:
        s += 10  # priority book of business
    if _get(lead, "reason"):
        s += 4   # a concrete qualifying reason on file
    return max(0, min(99, s))  # cold-sourced tops out below an in-market lead
