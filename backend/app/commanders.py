"""AI Commander hierarchy — CEO → Commanders → Agents.

The CEO orchestrates four Commanders (Wealth, Business, Influence, Life). Each
Commander runs its agents, then the CEO rolls every Commander's output up into
its objectives' current values. The orchestration graph is built with
**LangGraph** when available (shared state, durable, extensible to human-approval
gates); it falls back to a plain sequential run so the daily cycle never breaks.
"""
from __future__ import annotations

import logging
from typing import TypedDict

from sqlalchemy import func
from sqlalchemy.orm import Session

from . import scoring
from .agents import AGENTS
from .config import settings
from .models import InstagramTarget, Job, Lead, MusicPlaylist, Objective, Restaurant

log = logging.getLogger("bruno.commanders")

# Commander → the agents it directs. (Life has no agents yet — placeholder.)
COMMANDERS: dict[str, dict] = {
    "wealth":    {"name": "Wealth Commander",    "agents": ["job_hunter", "insurance"]},
    "business":  {"name": "Business Commander",  "agents": ["savorymind", "bnbglobal"]},
    "influence": {"name": "Influence Commander", "agents": ["music", "instagram"]},
    "life_ops":  {"name": "Life Commander",      "agents": []},
}


def _run_content_factory(db: Session) -> dict:
    """Influence Commander: produce a fresh multi-channel content pack per business
    line from the evergreen library (one idea → every platform)."""
    from datetime import date

    from . import content_analytics, content_factory
    if not settings.content_factory_enabled:
        return {}
    seed = date.today().timetuple().tm_yday
    out = {}
    for business in ("executive", "bnbglobal", "savorymind", "music"):
        try:
            topic = content_analytics.best_topic(db, business, seed)  # bias to what performs
            out[business] = content_factory.generate_pack(db, topic, business)
        except Exception as exc:  # one line failing must not stop the rest
            out[business] = {"ok": False, "reason": str(exc)}
    return out


def _run_commander(db: Session, center: str) -> dict:
    spec = COMMANDERS[center]
    out: dict[str, dict] = {}
    for key in spec["agents"]:
        cls = AGENTS.get(key)
        if not cls:
            continue
        try:
            out[key] = cls(db).run()
        except Exception as exc:  # one agent failing must not stop the commander
            log.exception("Agent %s failed under %s", key, center)
            out[key] = {"error": str(exc)}
    # The Influence Commander also runs the Content Factory (one idea → every channel).
    if center == "influence":
        out["content_factory"] = _run_content_factory(db)
    return {"commander": spec["name"], "center": center, "agents": out}


def rollup_objectives(db: Session) -> None:
    """Update each objective's current_value from live data (real numbers)."""
    actions = scoring.build_actions(db)

    def pipeline(center: str) -> float:
        return round(sum(a["value"] * a["probability"]
                         for a in actions if a["command_center"] == center))

    updates = {
        "exec_role": pipeline("wealth"),
        "insurance": round(sum(a["value"] * a["probability"] for a in actions
                               if a["objective"] == "insurance")),
        "consulting": round(sum(a["value"] * a["probability"] for a in actions
                                if a["objective"] == "consulting")),
        "savorymind": float(db.query(func.count()).select_from(Restaurant)
                            .filter(Restaurant.kind == "prospect").scalar() or 0),
        "music": float(db.query(func.coalesce(func.sum(MusicPlaylist.followers), 0)).scalar() or 0)
                 + float(db.query(func.count()).select_from(InstagramTarget).scalar() or 0),
    }
    for key, val in updates.items():
        obj = db.query(Objective).filter(Objective.key == key).first()
        if obj is not None:
            obj.current_value = val
    db.commit()
    # Net worth rolls up from the finance ledger.
    from . import finance
    finance.rollup(db)


# ── Orchestration ────────────────────────────────────────────────────────────
def _run_ceo_agent(db: Session) -> dict:
    """The CEO's own summarization step — produces the daily executive report."""
    cls = AGENTS.get("ceo_dashboard")
    if not cls:
        return {}
    try:
        return cls(db).run()
    except Exception as exc:  # pragma: no cover
        log.exception("CEO dashboard agent failed")
        return {"error": str(exc)}


def _run_sequential(db: Session) -> dict:
    results = {c: _run_commander(db, c) for c in COMMANDERS}
    rollup_objectives(db)
    results["ceo_report"] = _run_ceo_agent(db)
    return results


class _GraphState(TypedDict, total=False):
    """Shared state passed between LangGraph nodes. Module-level so LangGraph's
    type-hint introspection can resolve it (a local class breaks get_type_hints)."""
    results: dict


def _run_langgraph(db: Session) -> dict:
    """Run commanders through a LangGraph StateGraph (CEO → commanders → rollup)."""
    from langgraph.graph import END, START, StateGraph

    def node(center):
        def _fn(state: _GraphState) -> _GraphState:
            res = dict(state.get("results") or {})
            res[center] = _run_commander(db, center)
            return {"results": res}
        return _fn

    def rollup_node(state: _GraphState) -> _GraphState:
        rollup_objectives(db)
        res = dict(state.get("results") or {})
        res["ceo_report"] = _run_ceo_agent(db)  # CEO summarizes after commanders
        return {"results": res}

    g = StateGraph(_GraphState)
    order = list(COMMANDERS)
    for c in order:
        g.add_node(c, node(c))
    g.add_node("rollup", rollup_node)
    g.add_edge(START, order[0])
    for a, b in zip(order, order[1:]):
        g.add_edge(a, b)
    g.add_edge(order[-1], "rollup")
    g.add_edge("rollup", END)

    final = g.compile().invoke({"results": {}})
    return final.get("results", {})


def run_ceo(db: Session) -> dict:
    """Run the full daily cycle through the commander hierarchy."""
    try:
        results = _run_langgraph(db)
        engine = "langgraph"
    except Exception as exc:  # graceful fallback keeps the daily cycle reliable
        log.warning("LangGraph orchestration unavailable (%s) — running sequentially", exc)
        results = _run_sequential(db)
        engine = "sequential"
    return {"engine": engine, "commanders": results}


def status(db: Session) -> list[dict]:
    """Commander roster + their objectives + live pipeline, for the dashboard."""
    actions = scoring.build_actions(db)
    out = []
    for center, spec in COMMANDERS.items():
        objs = db.query(Objective).filter(Objective.command_center == center).all()
        c_actions = [a for a in actions if a["command_center"] == center]
        out.append({
            "center": center, "name": spec["name"], "agents": spec["agents"],
            "objectives": [{"key": o.key, "name": o.name,
                            "current_value": float(o.current_value or 0),
                            "target_value": float(o.target_value or 0)} for o in objs],
            "open_actions": len(c_actions),
            "pipeline_value": round(sum(a["value"] * a["probability"] for a in c_actions)),
        })
    return out
