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


@router.post("/commanders/{center}/run")
def commander_run(center: str, db: Session = Depends(get_db), _=Depends(_write)):
    """Run this commander's agents now (don't wait for the daily cycle)."""
    from .. import commanders
    res = commanders.run_center(db, center)
    if res.get("ok") is False:
        raise HTTPException(404, res.get("reason", "unknown commander"))
    return res


class CommanderTarget(BaseModel):
    objective_key: str
    target_value: float


@router.post("/commanders/{center}/target")
def commander_target(center: str, body: CommanderTarget,
                     db: Session = Depends(get_db), _=Depends(_write)):
    """Set the target amount for one of a commander's objectives (pick the amount)."""
    o = (db.query(Objective)
         .filter(Objective.key == body.objective_key,
                 Objective.command_center == center).first())
    if not o:
        raise HTTPException(404, "objective not found for this commander")
    o.target_value = body.target_value
    db.commit()
    return {"ok": True, "objective": o.key, "target_value": float(o.target_value or 0)}


class CommanderOrderIn(BaseModel):
    order: str
    amount: float | None = None
    objective_key: str | None = None
    run_now: bool = True


@router.post("/commanders/{center}/order")
def commander_order(center: str, body: CommanderOrderIn,
                    db: Session = Depends(get_db), _=Depends(_write)):
    """Give a commander a direct order (optionally with a target amount). Records
    the order, applies the amount to the named objective, and runs the commander
    now so the order is acted on — not just logged."""
    from .. import commanders
    from ..models import CommanderOrder
    if center not in commanders.COMMANDERS:
        raise HTTPException(404, f"unknown commander '{center}'")
    if body.amount is not None and body.objective_key:
        o = (db.query(Objective)
             .filter(Objective.key == body.objective_key,
                     Objective.command_center == center).first())
        if o:
            o.target_value = body.amount
    rec = CommanderOrder(center=center, order=body.order, amount=body.amount,
                         status="received")
    db.add(rec)
    db.commit()

    # Let the commander figure out HOW: turn the order + amount into a short plan
    # over its own agents, then execute. The plan is what the commander will do.
    plan = _commander_plan(center, commanders.COMMANDERS[center], body.order, body.amount)

    result = None
    if body.run_now:
        result = commanders.run_center(db, center)
        rec.status = "run" if result.get("ok") else "failed"
        rec.result = {"plan": plan, "ran": bool(result and result.get("ok"))}
        db.commit()
    else:
        rec.result = {"plan": plan}
        db.commit()
    return {"ok": True, "order_id": str(rec.id), "center": center,
            "amount": body.amount, "plan": plan, "ran": bool(body.run_now), "result": result}


def _commander_plan(center: str, spec: dict, order: str | None, amount: float | None) -> str:
    """A short, concrete plan for how the commander's agents will pursue the order."""
    agents = ", ".join(spec.get("agents") or []) or "its agents"
    fallback = (f"{spec['name']} will direct {agents} toward "
                f"{('$' + format(int(amount), ',')) if amount else 'the goal'}"
                + (f": {order}" if order else "."))
    from ..ai import client
    if not client.is_live():
        return fallback
    try:
        out = client.complete_json(
            f"You are the {spec['name']} for an AI marketing/sales workforce. Its agents: "
            f"{agents}. The order: \"{order or 'grow this area'}\""
            + (f" with a target of ${int(amount):,}." if amount else ".")
            + " Give a SHORT plan (3-4 steps) for how these agents will pursue it. "
              'Return JSON {"plan": "<steps as one short paragraph>"}.',
            system="You output only valid JSON.")
        if isinstance(out, dict) and out.get("plan"):
            return out["plan"]
    except Exception:  # pragma: no cover - planning is best-effort
        pass
    return fallback


@router.get("/commanders/orders")
def commander_orders(limit: int = 20, db: Session = Depends(get_db), _=Depends(_read)):
    """Recent orders given to commanders (newest first)."""
    from ..models import CommanderOrder
    rows = (db.query(CommanderOrder)
            .order_by(CommanderOrder.created_at.desc()).limit(limit).all())
    return [{"id": str(r.id), "center": r.center, "order": r.order,
             "amount": float(r.amount) if r.amount is not None else None,
             "status": r.status,
             "created_at": r.created_at.isoformat() if r.created_at else None} for r in rows]


@router.get("/admin/selftest")
def admin_selftest(db: Session = Depends(get_db), _=Depends(_read)):
    """Live health check — pings every configured/connected service."""
    from .. import selftest
    return selftest.run(db)


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
    from .. import finance
    fin = finance.summary(db)
    return {
        "monthly_income": fin["monthly_income"],
        "pipeline_value": pipeline,
        "net_worth": fin["net_worth"],
        "leads": int(leads),
        "users": int(restaurants),    # SavoryMind prospects as a proxy until live
        "reach": int(followers) + int(ig),
        "fitness_score": 0,           # wire to health connector later
    }
