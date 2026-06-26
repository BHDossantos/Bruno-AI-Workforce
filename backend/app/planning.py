"""Predictive planning / scenario modeling.

Answers "how do I reach $X/year?" by modeling Bruno's income streams from the live
pipeline (jobs, insurance + consulting leads, SavoryMind prospects, music) and
simulating candidate PATHS — combinations of streams — each with a projected
annual figure, a probability, and the key moves. Deterministic and offline-safe:
transparent assumptions, no black box, so the numbers are explainable.
"""
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from .models import Job, Lead, Opportunity, Restaurant

# Per-deal economics (same assumptions the scoring engine uses) + annual cycles.
_COMMERCIAL, _PERSONAL = 5_000, 1_500
_CONSULTING, _RESTAURANT_ARR = 20_000, 12_000
_DEFAULT_SALARY = 275_000
_WARM = ("Replied", "Interested", "Follow-up Needed")

# Floor "addressable" annual potential per stream, so paths are meaningful before
# the pipeline fills in. These are potential run-rates, not promises.
_FLOOR = {"exec_role": 275_000, "insurance": 60_000, "consulting": 120_000,
          "savorymind": 80_000, "music": 12_000}
# Baseline landing/close probability per stream.
_PROB = {"exec_role": 0.45, "insurance": 0.6, "consulting": 0.4,
         "savorymind": 0.35, "music": 0.15}


def _count(db: Session, model, *filters) -> int:
    return int(db.query(func.count()).select_from(model).filter(*filters).scalar() or 0)


def _streams(db: Session) -> dict[str, dict]:
    best_salary = (db.query(func.max(Job.salary_min)).scalar() or 0) or _DEFAULT_SALARY

    comm = _count(db, Lead, Lead.segment == "commercial", Lead.status.in_(_WARM))
    pers = _count(db, Lead, Lead.segment == "personal", Lead.status.in_(_WARM))
    cons = _count(db, Lead, Lead.segment == "consulting", Lead.status.in_(_WARM))
    rests = _count(db, Restaurant, Restaurant.kind == "prospect", Restaurant.status.in_(_WARM))

    # Annualize warm pipeline (≈4 conversion cycles/yr for outreach businesses).
    insurance_run = (comm * _COMMERCIAL + pers * _PERSONAL) * 4
    consulting_run = cons * _CONSULTING * 2
    savory_run = rests * _RESTAURANT_ARR  # ARR is already annual

    def stream(key, label, annual, move):
        return {"key": key, "label": label,
                "annual_potential": int(max(annual, _FLOOR[key])),
                "probability": _PROB[key], "key_move": move}

    return {
        "exec_role": stream("exec_role", "Executive role", best_salary,
                            "Land one Director/VP role from the apply queue"),
        "insurance": stream("insurance", "Insurance (Thrust)", insurance_run,
                            "Convert warm pipeline + work referrals (NH/MA/FL)"),
        "consulting": stream("consulting", "BnB Global consulting", consulting_run,
                            "Close consulting engagements (US + EU)"),
        "savorymind": stream("savorymind", "SavoryMind SaaS", savory_run,
                            "Sign restaurants to annual contracts"),
        "music": stream("music", "Music (Bruno D)", 0,
                        "Grow catalog streams across the era releases"),
    }


_PATHS = [
    ("Wealth Engine", "Executive role + insurance + consulting",
     ["exec_role", "insurance", "consulting"]),
    ("Operator", "Insurance + consulting + SavoryMind SaaS",
     ["insurance", "consulting", "savorymind"]),
    ("Artist-led", "Music + insurance as the stable base",
     ["music", "insurance"]),
    ("Full Portfolio", "Every venture running at once",
     ["exec_role", "insurance", "consulting", "savorymind", "music"]),
]


def simulate(db: Session, target: int) -> dict:
    target = max(1, int(target or 1_000_000))
    streams = _streams(db)

    paths = []
    for name, desc, keys in _PATHS:
        comps = [streams[k] for k in keys if k in streams]
        projected = sum(c["annual_potential"] for c in comps)
        # Value-weighted probability, with a focus penalty for splitting attention.
        wsum = sum(c["annual_potential"] for c in comps) or 1
        base = sum(c["annual_potential"] * c["probability"] for c in comps) / wsum
        prob = round(base * (0.93 ** (len(comps) - 1)), 2)
        meets = projected >= target
        score = prob if meets else round(prob * projected / target, 3)
        paths.append({
            "name": name, "description": desc,
            "projected_annual": projected, "probability": prob,
            "meets_target": meets, "score": score,
            "components": [{"label": c["label"], "annual_potential": c["annual_potential"],
                            "probability": c["probability"]} for c in comps],
            "key_moves": [c["key_move"] for c in comps],
        })

    paths.sort(key=lambda p: (p["meets_target"], p["score"]), reverse=True)
    best = paths[0] if paths else None
    return {
        "target": target,
        "streams": list(streams.values()),
        "paths": paths,
        "recommended": best["name"] if best else None,
        "assumptions": ("Annual potentials are addressable run-rates from live "
                        "pipeline (warm leads × per-deal value × cycles/yr), floored "
                        "to a baseline. Probabilities are blended with a focus penalty "
                        "for splitting attention. Estimates, not guarantees."),
    }
