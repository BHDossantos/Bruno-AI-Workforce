"""Sales Agent + Performance API.

  • POST /sales-agent/run       → run one autonomous email→text→call selling pass
  • GET  /sales-agent/status    → is it live, today's touches, pipeline split
  • GET  /sales-agent/needs-you → leads that engaged and need a human
  • GET  /performance           → funnel + revenue + trend
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import sales_agent, sales_performance
from ..database import get_db
from ..security import require_role

router = APIRouter(tags=["sales"])
_write = require_role("admin", "operator")
_read = require_role("admin", "operator", "viewer")


def _refresh(db: Session) -> None:
    try:
        from .. import runtime_config
        runtime_config.apply_to_settings(db)
    except Exception:
        pass


@router.post("/sales-agent/run")
def sales_agent_run(db: Session = Depends(get_db), _=Depends(_write)):
    """Run one full outbound selling pass now — email → text → call, hands-free,
    each channel paced and compliance-gated. Returns what actually went out."""
    _refresh(db)
    result = sales_agent.run(db)
    return {"ok": True, **result}


@router.get("/sales-agent/status")
def sales_agent_status(db: Session = Depends(get_db), _=Depends(_read)):
    """Is the agent live, today's touches by channel, and the pipeline split."""
    return sales_agent.status(db)


@router.get("/sales-agent/needs-you")
def sales_agent_needs_you(db: Session = Depends(get_db), _=Depends(_read)):
    """Leads that engaged (replied / interested / follow-up) — pulled out of the
    outbound machine because they need you, hottest first."""
    return {"leads": sales_agent.needs_attention(db)}


@router.get("/performance")
def performance(db: Session = Depends(get_db), _=Depends(_read)):
    """The funnel + revenue view: Leads → Contacted → Engaged → Won with conversion,
    real commission from signed clients, this-month vs goal, and the trend."""
    _refresh(db)  # so commission % / goal reflect the latest Setup values
    return sales_performance.report(db)
