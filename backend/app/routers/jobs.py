"""Jobs + applications routes (incl. the one-click apply queue)."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Application, Job
from ..schemas import JobOut, StatusUpdate
from ..security import require_role

router = APIRouter(prefix="/jobs", tags=["jobs"])

# Application statuses that mean "handled" (drop from the apply queue).
_DONE_APP = {"Applied", "Skipped", "Sent", "Replied", "Interested", "Closed Won", "Closed Lost"}


@router.get("", response_model=list[JobOut])
def list_jobs(limit: int = 100, min_score: int = 0,
              db: Session = Depends(get_db), _=Depends(require_role("admin", "operator", "viewer"))):
    return (db.query(Job).filter(Job.score >= min_score)
            .order_by(Job.score.desc(), Job.found_at.desc()).limit(limit).all())


# ── One-click apply queue ─────────────────────────────────────────────────────
# Compliant: we prepare the apply link + tailored materials; you click apply and
# mark it done. No bot submits anything (that violates job-board ToS).
@router.get("/queue")
def apply_queue(limit: int = 100, db: Session = Depends(get_db),
                _=Depends(require_role("admin", "operator", "viewer"))):
    apps = {a.job_id: a for a in db.query(Application).all()}
    jobs = db.query(Job).order_by(Job.score.desc(), Job.found_at.desc()).limit(limit * 2).all()
    out = []
    for j in jobs:
        app = apps.get(j.id)
        status = app.status if app else "New"
        if status in _DONE_APP:
            continue
        out.append({
            "job_id": str(j.id), "title": j.title, "company": j.company,
            "location": j.location, "remote": j.remote,
            "salary_min": j.salary_min, "salary_max": j.salary_max,
            "score": j.score, "score_breakdown": j.score_breakdown,
            "url": j.url, "source": j.source,
            "resume_match": j.resume_match, "cover_letter": j.cover_letter,
            "status": status,
        })
        if len(out) >= limit:
            break
    return out


class ApplyMark(BaseModel):
    job_id: str
    status: str = "Applied"  # Applied | Skipped


@router.post("/queue/mark")
def mark_apply(body: ApplyMark, db: Session = Depends(get_db),
               _=Depends(require_role("admin", "operator"))):
    app = db.query(Application).filter(Application.job_id == body.job_id).first()
    if not app:
        app = Application(job_id=body.job_id)
        db.add(app)
    app.status = body.status
    if body.status == "Applied":
        app.applied_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True, "job_id": body.job_id, "status": body.status}


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
