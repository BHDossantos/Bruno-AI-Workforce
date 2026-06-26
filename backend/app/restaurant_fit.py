"""SavoryMind fit/priority score for a restaurant prospect.

Estimates how good a SavoryMind target a restaurant is from the signals we have
today: reachability (email/phone/social) + need signals (weak web presence, no
online menu, known pain points). Higher = work this one first. Richer signals
(review counts, loyalty program, POS, hiring) light up when a data source like
Google Places Details / Apollo is connected.
"""
from __future__ import annotations


def score(r) -> int:
    s = 40
    # Reachable → we can actually pitch them.
    if getattr(r, "email", None):
        s += 20
    if getattr(r, "phone", None):
        s += 8
    if getattr(r, "instagram", None):
        s += 8   # active on social = engaged + reachable
    # Need signals → they'd benefit most from SavoryMind.
    if not getattr(r, "website", None):
        s += 12  # weak online presence
    if not getattr(r, "menu_url", None):
        s += 8   # no online menu → menu-intelligence opportunity
    if getattr(r, "pain_points", None):
        s += 12
    return max(0, min(100, s))
