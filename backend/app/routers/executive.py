"""Executive layer — the outcome-organized 'Chief of Staff' surface.

Daily Brief (Top-3), Objectives, Command Centers, and the roll-up Scoreboard.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import objectives as obj
from .. import scoring
from ..database import get_db
from ..models import InstagramTarget, Lead, MusicPlaylist, Objective, Restaurant
from ..security import require_role

router = APIRouter(tags=["executive"])
_read = require_role("admin", "operator", "viewer")


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
