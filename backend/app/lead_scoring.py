"""Explainable lead score — wraps the numeric fit score (lead_fit) with the
human-readable reasons + temperature band behind it.

Instantly/Smartlead-style lead intelligence: "92/100 — has email, named owner,
priority segment, replied once". The number stays single-sourced in lead_fit;
this adds the *why* and a hot/warm/cold band for the UI. Pure function, no network.
"""
from __future__ import annotations

from . import lead_fit
from .lead_temperature import DEAD, HOT, WARM, classify
from .models import Lead

_PRIORITY = {"commercial", "referral_partner", "consulting"}


def score_lead(lead: Lead) -> dict:
    base = lead_fit.score(lead)  # single source of truth for the number
    temp = classify(lead.status)

    reasons: list[str] = []
    if temp == HOT:
        reasons.append("🔥 Hot — buying signal")
    elif temp == WARM:
        reasons.append("🌤️ Warm — engaged/replied")
    elif temp == DEAD:
        reasons.append("Closed / opted-out")
    if lead.email:
        reasons.append("Has email")
    if lead.owner_name:
        reasons.append("Named decision-maker")
    if (lead.segment or "") in _PRIORITY:
        reasons.append("Priority segment")
    if lead.phone:
        reasons.append("Has phone")
    if not lead.email and not lead.phone:
        reasons.append("No contact channel — enrich first")

    band = "hot" if base >= 70 else "warm" if base >= 50 else "cold"
    return {"score": int(base), "band": band, "reasons": reasons[:4]}
