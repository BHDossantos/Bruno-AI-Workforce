"""Executive layer — the outcome-organized 'Chief of Staff' surface.

Daily Brief (Top-3), Objectives, Command Centers, and the roll-up Scoreboard.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import actions as action_svc
from .. import objectives as obj
from .. import scoring
from ..database import get_db
from ..models import InstagramTarget, Lead, MusicPlaylist, Objective, Restaurant
from ..security import require_role

router = APIRouter(tags=["executive"])
_read = require_role("admin", "operator", "viewer")
_write = require_role("admin", "operator")


class ActionKey(BaseModel):
    key: str


@router.post("/actions/execute")
def execute_action(body: ActionKey, db: Session = Depends(get_db), _=Depends(_write)):
    return action_svc.execute(db, body.key)


@router.post("/actions/dismiss")
def dismiss_action(body: ActionKey, db: Session = Depends(get_db), _=Depends(_write)):
    return action_svc.dismiss(db, body.key)


@router.get("/brief/today")
def brief_today(top: int = 3, db: Session = Depends(get_db), _=Depends(_read)):
    return scoring.brief(db, top_n=top)


@router.get("/objectives")
def list_objectives(db: Session = Depends(get_db), _=Depends(_read)):
    obj.ensure_objectives(db)
    rows = db.query(Objective).order_by(Objective.rank).all()
    return [{
        "key": o.key, "name": o.name, "command_center": o.command_center,
        "metric": o.metric, "target_value": float(o.target_value or 0),
        "current_value": float(o.current_value or 0), "rank": o.rank,
        "weight": float(o.weight or 0), "status": o.status,
    } for o in rows]


class ObjectivePatch(BaseModel):
    weight: float | None = None
    target_value: float | None = None
    rank: int | None = None
    name: str | None = None
    status: str | None = None


@router.patch("/objectives/{key}")
def update_objective(key: str, body: ObjectivePatch, db: Session = Depends(get_db), _=Depends(_write)):
    obj.ensure_objectives(db)
    o = db.query(Objective).filter(Objective.key == key).first()
    if not o:
        raise HTTPException(404, "objective not found")
    for field, val in body.model_dump(exclude_none=True).items():
        setattr(o, field, val)
    db.commit()
    return {"key": o.key, "name": o.name, "weight": float(o.weight or 0),
            "target_value": float(o.target_value or 0), "rank": o.rank, "status": o.status}


@router.get("/search")
def global_search(q: str, db: Session = Depends(get_db), _=Depends(_read)):
    """One search across the CRM and the memory graph."""
    from .. import crm as crm_svc
    from .. import memory as mem_svc
    q = (q or "").strip()
    if not q:
        return {"contacts": [], "memories": []}
    return {
        "contacts": crm_svc.list_contacts(db, q=q, limit=12),
        "memories": mem_svc.search(db, q, k=12),
    }


@router.get("/command-centers")
def command_centers(db: Session = Depends(get_db), _=Depends(_read)):
    obj.ensure_objectives(db)
    actions = scoring.build_actions(db)
    objs = db.query(Objective).order_by(Objective.rank).all()
    out = []
    for c in obj.CENTERS:
        c_actions = [a for a in actions if a["command_center"] == c["key"]]
        out.append({
            "key": c["key"], "name": c["name"], "icon": c["icon"],
            "objectives": [{
                "key": o.key, "name": o.name, "metric": o.metric,
                "target_value": float(o.target_value or 0),
                "current_value": float(o.current_value or 0),
            } for o in objs if o.command_center == c["key"]],
            "action_count": len(c_actions),
            "top_actions": c_actions[:5],
            "pipeline_value": round(sum(a["value"] * a["probability"] for a in c_actions)),
        })
    return out


@router.get("/commanders")
def commanders_status(db: Session = Depends(get_db), _=Depends(_read)):
    from .. import commanders
    return commanders.status(db)


@router.get("/scoreboard")
def scoreboard(db: Session = Depends(get_db), _=Depends(_read)):
    """The six roll-up metrics everything else feeds into."""
    actions = scoring.build_actions(db)
    pipeline = round(sum(a["value"] * a["probability"] for a in actions))
    leads = db.query(func.count()).select_from(Lead).scalar() or 0
    restaurants = db.query(func.count()).select_from(Restaurant).filter(
        Restaurant.kind == "prospect").scalar() or 0
    followers = db.query(func.coalesce(func.sum(MusicPlaylist.followers), 0)).scalar() or 0
    ig = db.query(func.count()).select_from(InstagramTarget).scalar() or 0
    return {
        "monthly_income": 0,          # wire to real income source later
        "pipeline_value": pipeline,
        "net_worth": 0,               # wire to investments/banking later
        "leads": int(leads),
        "users": int(restaurants),    # SavoryMind prospects as a proxy until live
        "reach": int(followers) + int(ig),
        "fitness_score": 0,           # wire to health connector later
    }
