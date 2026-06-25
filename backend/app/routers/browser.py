"""Browser-Use worker API — prepare and run form-filling tasks."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import browser
from ..database import get_db
from ..security import require_role

router = APIRouter(prefix="/browser", tags=["browser"])
_read = require_role("admin", "operator", "viewer")
_write = require_role("admin", "operator")


class RunIn(BaseModel):
    auto_submit: bool | None = None


@router.get("/profile")
def applicant_profile_view(_=Depends(_read)):
    """The applicant profile the Autopilot uses to fill applications."""
    from .. import applicant_profile
    return {"profile": applicant_profile.PROFILE, "screening": applicant_profile.SCREENING,
            "short_answers": applicant_profile.SHORT_ANSWERS}


@router.get("/tasks")
def list_tasks(db: Session = Depends(get_db), _=Depends(_read)):
    return browser.list_tasks(db)


@router.get("/tasks/{task_id}")
def get_task(task_id: str, db: Session = Depends(get_db), _=Depends(_read)):
    t = browser.get_task(db, task_id)
    if not t:
        raise HTTPException(404, "task not found")
    return t


@router.post("/apply/{job_id}")
def prepare_application(job_id: str, db: Session = Depends(get_db), _=Depends(_write)):
    t = browser.prepare_job_application(db, job_id)
    if not t:
        raise HTTPException(404, "job not found")
    return browser._out(t)


@router.post("/tasks/{task_id}/run")
def run_task(task_id: str, body: RunIn = RunIn(), db: Session = Depends(get_db), _=Depends(_write)):
    t = browser.run(db, task_id, auto_submit=body.auto_submit)
    if not t:
        raise HTTPException(404, "task not found")
    return browser._out(t)
