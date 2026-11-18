"""Projects / delivery — the post-sale 'are we delivering what we sold?' layer.

A self-contained domain (narrow interface, own tests): a Project groups its
ProjectTask rows for one client. Health is DERIVED, never stored, so it can't go
stale — ``_health`` reads due dates + open-task counts each time. No new columns
on existing tables; two brand-new tables only (create_all safe).
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from .models import Project, ProjectTask

ACTIVE_STATUSES = ("Planned", "Active", "Blocked")


def _parse_date(v):
    if not v:
        return None
    if isinstance(v, date):
        return v
    try:
        return datetime.fromisoformat(str(v)).date()
    except ValueError:
        return None


def _health(p: Project) -> str:
    """on_track | at_risk | overdue — derived from due date and open tasks."""
    if p.status in ("Done", "Cancelled"):
        return "done"
    today = date.today()
    open_tasks = [t for t in p.tasks if t.status != "Done"]
    overdue_tasks = [t for t in open_tasks if t.due_date and t.due_date < today]
    if (p.due_date and p.due_date < today) or overdue_tasks or p.status == "Blocked":
        return "overdue" if (p.due_date and p.due_date < today) or overdue_tasks else "at_risk"
    # Due within a week with work still open → at risk.
    if p.due_date and (p.due_date - today).days <= 7 and open_tasks:
        return "at_risk"
    return "on_track"


def create_project(db: Session, *, name: str, business: str = "insurance",
                   client_id=None, client_name: str | None = None,
                   description: str | None = None, owner: str | None = None,
                   start_date=None, due_date=None) -> Project:
    p = Project(
        name=name.strip(), business=business or "insurance",
        client_id=client_id, client_name=client_name, description=description,
        owner=owner, start_date=_parse_date(start_date), due_date=_parse_date(due_date),
        status="Active")
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def update_project(db: Session, project_id, **fields) -> Project | None:
    p = db.get(Project, project_id)
    if p is None:
        return None
    for key in ("name", "description", "owner", "client_name", "business"):
        if fields.get(key) is not None:
            setattr(p, key, fields[key])
    if fields.get("status"):
        p.status = fields["status"].capitalize()
    for key in ("start_date", "due_date"):
        if key in fields:
            setattr(p, key, _parse_date(fields[key]))
    db.commit()
    db.refresh(p)
    return p


def delete_project(db: Session, project_id) -> bool:
    p = db.get(Project, project_id)
    if p is None:
        return False
    db.delete(p)
    db.commit()
    return True


def add_task(db: Session, project_id, *, title: str, owner: str | None = None,
             due_date=None, status: str = "Todo") -> ProjectTask | None:
    p = db.get(Project, project_id)
    if p is None:
        return None
    t = ProjectTask(project_id=p.id, title=title.strip(), owner=owner,
                    due_date=_parse_date(due_date), status=status.capitalize())
    if t.status == "Done":
        t.done_at = datetime.now(timezone.utc)
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def set_task_status(db: Session, task_id, status: str) -> ProjectTask | None:
    t = db.get(ProjectTask, task_id)
    if t is None:
        return None
    status = status.capitalize()
    if status not in ("Todo", "Doing", "Done"):
        return t
    t.status = status
    t.done_at = datetime.now(timezone.utc) if status == "Done" else None
    db.commit()
    db.refresh(t)
    return t


def delete_task(db: Session, task_id) -> bool:
    t = db.get(ProjectTask, task_id)
    if t is None:
        return False
    db.delete(t)
    db.commit()
    return True


def _task_dict(t: ProjectTask) -> dict:
    return {
        "id": str(t.id), "title": t.title, "status": t.status, "owner": t.owner,
        "due_date": t.due_date.isoformat() if t.due_date else None,
    }


def _project_dict(p: Project, *, with_tasks: bool = False) -> dict:
    total = len(p.tasks)
    done = sum(1 for t in p.tasks if t.status == "Done")
    out = {
        "id": str(p.id), "name": p.name, "business": p.business,
        "client_id": str(p.client_id) if p.client_id else None,
        "client_name": p.client_name, "description": p.description, "owner": p.owner,
        "status": p.status, "health": _health(p),
        "start_date": p.start_date.isoformat() if p.start_date else None,
        "due_date": p.due_date.isoformat() if p.due_date else None,
        "task_count": total, "tasks_done": done,
        "progress": round(done / total, 2) if total else 0.0,
    }
    if with_tasks:
        out["tasks"] = [_task_dict(t) for t in sorted(p.tasks, key=lambda t: (t.position, t.created_at or datetime.min))]
    return out


def list_projects(db: Session, *, business: str | None = None,
                  status: str | None = None, limit: int = 200) -> list[dict]:
    q = db.query(Project)
    if business:
        q = q.filter(Project.business == business)
    if status:
        q = q.filter(Project.status == status.capitalize())
    rows = q.order_by(Project.created_at.desc()).limit(limit).all()
    return [_project_dict(p) for p in rows]


def get_project(db: Session, project_id) -> dict | None:
    p = db.get(Project, project_id)
    return _project_dict(p, with_tasks=True) if p else None


def summary(db: Session, *, business: str | None = None) -> dict:
    q = db.query(Project)
    if business:
        q = q.filter(Project.business == business)
    rows = q.all()
    active = [p for p in rows if p.status in ACTIVE_STATUSES]
    at_risk = overdue = 0
    for p in active:
        h = _health(p)
        if h == "overdue":
            overdue += 1
        elif h == "at_risk":
            at_risk += 1
    return {
        "total": len(rows), "active": len(active),
        "at_risk": at_risk, "overdue": overdue,
        "done": sum(1 for p in rows if p.status == "Done"),
    }
