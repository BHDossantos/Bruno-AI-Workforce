"""Agent management: list agents and trigger runs on demand."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..agents import AGENTS
from ..database import get_db
from ..models import Agent
from ..schemas import AgentOut
from ..security import require_role

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("", response_model=list[AgentOut])
def list_agents(db: Session = Depends(get_db), _=Depends(require_role("admin", "operator", "viewer"))):
    return db.query(Agent).order_by(Agent.schedule_cron).all()


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
