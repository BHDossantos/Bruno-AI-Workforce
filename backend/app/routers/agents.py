"""Agent management: list agents, trigger runs, and per-agent performance health."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..agents import AGENTS
from ..database import get_db
from ..models import Agent, Task
from ..schemas import AgentOut
from ..security import require_role

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("", response_model=list[AgentOut])
def list_agents(db: Session = Depends(get_db), _=Depends(require_role("admin", "operator", "viewer"))):
    return db.query(Agent).order_by(Agent.schedule_cron).all()


class BlueprintIn(BaseModel):
    url: str


@router.post("/blueprint")
def create_blueprint(body: BlueprintIn, db: Session = Depends(get_db),
                     _=Depends(require_role("admin", "operator"))):
    """Create an AI sales agent from a business URL — scans the site and generates
    the offer, ICP, target industries, pain points, angles and message scripts."""
    from .. import agent_builder
    return agent_builder.build_from_url(db, body.url)


@router.get("/blueprints")
def list_blueprints(db: Session = Depends(get_db),
                    _=Depends(require_role("admin", "operator", "viewer"))):
    from .. import agent_builder
    return agent_builder.list_blueprints(db)


def _suggest(runs: int, success_rate: int | None, last_error: str | None) -> str:
    """A plain-language self-improvement nudge from an agent's own track record."""
    if runs == 0:
        return "Never run yet — trigger it once to start a baseline."
    if success_rate is not None and success_rate < 60:
        return f"High failure rate — investigate the recurring error: {(last_error or '')[:120]}"
    if last_error:
        return f"Last run errored — check: {last_error[:120]}"
    if success_rate == 100 and runs >= 5:
        return "Healthy and reliable — safe to increase cadence or autonomy."
    return "Stable — keep monitoring."


@router.get("/health")
def agents_health(db: Session = Depends(get_db),
                  _=Depends(require_role("admin", "operator", "viewer"))):
    """Each agent's self-report: run count, success/failure rate, avg duration, last
    error — so the workforce (and you) can see what's working and tune it."""
    out = []
    for a in db.query(Agent).all():
        tasks = (db.query(Task).filter(Task.agent_id == a.id)
                 .order_by(Task.created_at.desc()).limit(200).all())
        runs = len(tasks)
        done = [t for t in tasks if t.status in ("success", "error")]
        successes = sum(1 for t in done if t.status == "success")
        errors = sum(1 for t in done if t.status == "error")
        success_rate = round(100 * successes / len(done)) if done else None
        durs = [(t.finished_at - t.started_at).total_seconds()
                for t in tasks if t.finished_at and t.started_at]
        avg_dur = round(sum(durs) / len(durs), 1) if durs else None
        last_error = next((t.error for t in tasks if t.status == "error" and t.error), None)
        out.append({
            "key": a.key, "name": a.name,
            "runs": runs, "successes": successes, "errors": errors,
            "success_rate": success_rate, "avg_duration_sec": avg_dur,
            "last_run_at": a.last_run_at.isoformat() if a.last_run_at else None,
            "last_status": done[0].status if done else None,
            "last_error": last_error,
            "suggestion": _suggest(runs, success_rate, last_error),
        })
    out.sort(key=lambda x: (x["success_rate"] is None, x["success_rate"] or 0))
    return out


@router.post("/{key}/run")
def run_agent(key: str, db: Session = Depends(get_db), _=Depends(require_role("admin", "operator"))):
    """Run a single agent immediately (manual trigger)."""
    cls = AGENTS.get(key)
    if not cls:
        raise HTTPException(status_code=404, detail=f"Unknown agent '{key}'")
    result = cls(db).run()
    return {"agent": key, "result": result}


@router.post("/run-all")
def run_all(db: Session = Depends(get_db), _=Depends(require_role("admin"))):
    """Run the full daily cycle through the CEO → Commander → Agent hierarchy."""
    from .. import commanders
    return commanders.run_ceo(db)
