"""Objectives — the outcomes the platform optimizes for.

Seeded with Bruno's COO-ranked objectives. The ``weight`` flows into the scoring
engine so high-ROI objectives (executive role) outrank low-ROI ones (music) for
today's attention, no matter how many opportunities each generates.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from .models import Objective

# command_center keys: wealth | business | influence | personal | life_ops
DEFAULTS = [
    dict(key="net_worth", name="Grow net worth to $1M",
         command_center="wealth", metric="net_worth", target_value=1_000_000, rank=1, weight=1.0),
    dict(key="exec_role", name="Land a $250–350k executive role",
         command_center="wealth", metric="income", target_value=300_000, rank=1, weight=1.0),
    dict(key="insurance", name="Grow the insurance book (fast cash flow)",
         command_center="wealth", metric="income", target_value=80_000, rank=2, weight=0.8),
    # Consulting (BnB Global) lives under the Business Commander — same place its
    # scored pipeline is counted, so the card math lines up.
    dict(key="consulting", name="Build consulting income",
         command_center="business", metric="income", target_value=50_000, rank=3, weight=0.6),
    dict(key="savorymind", name="Grow SavoryMind",
         command_center="business", metric="revenue", target_value=120_000, rank=4, weight=0.5),
    dict(key="music", name="Grow music influence",
         command_center="influence", metric="followers", target_value=50_000, rank=5, weight=0.25),
    # Life Commander objective so the Life center is live (not "no objectives yet").
    dict(key="life_ops", name="Stay healthy & organized",
         command_center="life_ops", metric="tasks", target_value=100, rank=6, weight=0.2),
]

CENTERS = [
    {"key": "wealth", "name": "Wealth", "icon": "💰"},
    {"key": "business", "name": "Business", "icon": "🏢"},
    {"key": "influence", "name": "Influence", "icon": "📣"},
    {"key": "personal", "name": "Personal", "icon": "💪"},
    {"key": "life_ops", "name": "Life Operations", "icon": "🗂️"},
]


def ensure_objectives(db: Session) -> None:
    """Create any missing default objectives AND reconcile the command_center of
    known objectives (idempotent), so a center re-org (e.g. consulting → business)
    is applied to existing databases without a manual migration."""
    rows = {o.key: o for o in db.query(Objective).all()}
    changed = False
    for d in DEFAULTS:
        existing = rows.get(d["key"])
        if existing is None:
            db.add(Objective(**d))
            changed = True
        elif existing.command_center != d["command_center"]:
            existing.command_center = d["command_center"]
            changed = True
    if changed:
        db.commit()


def weights(db: Session) -> dict[str, float]:
    """objective key -> weight (falls back to defaults if the table is empty)."""
    rows = db.query(Objective.key, Objective.weight).all()
    if rows:
        return {k: float(w) for k, w in rows}
    return {d["key"]: d["weight"] for d in DEFAULTS}
