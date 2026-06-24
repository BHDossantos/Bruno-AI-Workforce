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
    dict(key="exec_role", name="Land a $250–350k executive role",
         command_center="wealth", metric="income", target_value=300_000, rank=1, weight=1.0),
    dict(key="insurance", name="Grow the insurance book (fast cash flow)",
         command_center="wealth", metric="income", target_value=80_000, rank=2, weight=0.8),
    dict(key="consulting", name="Build consulting income",
         command_center="wealth", metric="income", target_value=50_000, rank=3, weight=0.6),
    dict(key="savorymind", name="Grow SavoryMind",
         command_center="business", metric="revenue", target_value=120_000, rank=4, weight=0.5),
    dict(key="music", name="Grow music influence",
         command_center="influence", metric="followers", target_value=50_000, rank=5, weight=0.25),
]

CENTERS = [
    {"key": "wealth", "name": "Wealth", "icon": "💰"},
    {"key": "business", "name": "Business", "icon": "🏢"},
    {"key": "influence", "name": "Influence", "icon": "📣"},
    {"key": "personal", "name": "Personal", "icon": "💪"},
    {"key": "life_ops", "name": "Life Operations", "icon": "🗂️"},
]


def ensure_objectives(db: Session) -> None:
    """Create any missing default objectives (idempotent)."""
    existing = {k for (k,) in db.query(Objective.key).all()}
    created = False
    for d in DEFAULTS:
        if d["key"] not in existing:
            db.add(Objective(**d))
            created = True
    if created:
        db.commit()


def weights(db: Session) -> dict[str, float]:
    """objective key -> weight (falls back to defaults if the table is empty)."""
    rows = db.query(Objective.key, Objective.weight).all()
    if rows:
        return {k: float(w) for k, w in rows}
    return {d["key"]: d["weight"] for d in DEFAULTS}
