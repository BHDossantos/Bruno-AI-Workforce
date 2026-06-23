"""Jobs + applications routes."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Application, Job
from ..schemas import JobOut, StatusUpdate
from ..security import require_role

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=list[JobOut])
def list_jobs(limit: int = 100, min_score: int = 0,
              db: Session = Depends(get_db), _=Depends(require_role("admin", "operator", "viewer"))):
    return (db.query(Job).filter(Job.score >= min_score)
            .order_by(Job.score.desc(), Job.found_at.desc()).limit(limit).all())


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: str, db: Session = Depends(get_db), _=Depends(require_role("admin", "operator", "viewer"))):
    return db.query(Job).filter(Job.id == job_id).first()


@router.post("/{job_id}/status")
def set_application_status(job_id: str, body: StatusUpdate, db: Session = Depends(get_db),
                          _=Depends(require_role("admin", "operator"))):
    app = db.query(Application).filter(Application.job_id == job_id).first()
    if not app:
        app = Application(job_id=job_id)
        db.add(app)
    app.status = body.status
    db.commit()
    return {"job_id": job_id, "status": body.status}
