"""Projects / delivery API — track client engagements and their deliverables.

Thin HTTP layer over ``projects``; all lifecycle/health logic lives in the service.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import projects
from ..database import get_db
from ..security import require_role

router = APIRouter(prefix="/projects", tags=["projects"])
_read = require_role("admin", "operator", "viewer")
_write = require_role("admin", "operator")


class ProjectIn(BaseModel):
    name: str = Field(min_length=1)
    business: str = "insurance"
    client_id: str | None = None
    client_name: str | None = None
    description: str | None = None
    owner: str | None = None
    start_date: str | None = None
    due_date: str | None = None


class ProjectPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    owner: str | None = None
    client_name: str | None = None
    business: str | None = None
    status: str | None = None
    start_date: str | None = None
    due_date: str | None = None


class TaskIn(BaseModel):
    title: str = Field(min_length=1)
    owner: str | None = None
    due_date: str | None = None
    status: str = "Todo"


class TaskStatusIn(BaseModel):
    status: str


@router.get("/summary")
def summary(business: str | None = None, db: Session = Depends(get_db), _=Depends(_read)):
    return projects.summary(db, business=business)


@router.get("")
def list_projects(business: str | None = None, status: str | None = None,
                  limit: int = 200, db: Session = Depends(get_db), _=Depends(_read)):
    return projects.list_projects(db, business=business, status=status, limit=limit)


@router.post("")
def create_project(body: ProjectIn, db: Session = Depends(get_db), _=Depends(_write)):
    p = projects.create_project(db, **body.model_dump())
    return projects.get_project(db, p.id)


@router.get("/{project_id}")
def get_project(project_id: str, db: Session = Depends(get_db), _=Depends(_read)):
    out = projects.get_project(db, project_id)
    if out is None:
        raise HTTPException(404, "project not found")
    return out


@router.patch("/{project_id}")
def update_project(project_id: str, body: ProjectPatch, db: Session = Depends(get_db), _=Depends(_write)):
    p = projects.update_project(db, project_id, **body.model_dump(exclude_unset=True))
    if p is None:
        raise HTTPException(404, "project not found")
    return projects.get_project(db, project_id)


@router.delete("/{project_id}")
def delete_project(project_id: str, db: Session = Depends(get_db), _=Depends(_write)):
    if not projects.delete_project(db, project_id):
        raise HTTPException(404, "project not found")
    return {"ok": True}


@router.post("/{project_id}/tasks")
def add_task(project_id: str, body: TaskIn, db: Session = Depends(get_db), _=Depends(_write)):
    t = projects.add_task(db, project_id, title=body.title, owner=body.owner,
                          due_date=body.due_date, status=body.status)
    if t is None:
        raise HTTPException(404, "project not found")
    return projects.get_project(db, project_id)


@router.post("/tasks/{task_id}/status")
def set_task_status(task_id: str, body: TaskStatusIn, db: Session = Depends(get_db), _=Depends(_write)):
    t = projects.set_task_status(db, task_id, body.status)
    if t is None:
        raise HTTPException(404, "task not found")
    return {"ok": True, "status": t.status}


@router.delete("/tasks/{task_id}")
def delete_task(task_id: str, db: Session = Depends(get_db), _=Depends(_write)):
    if not projects.delete_task(db, task_id):
        raise HTTPException(404, "task not found")
    return {"ok": True}
