"""Uptime monitoring API — watch live apps and client sites.

Thin HTTP layer over ``uptime``; probing/history/counters live in the service.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import uptime
from ..database import get_db
from ..security import require_role

router = APIRouter(prefix="/monitors", tags=["monitors"])
_read = require_role("admin", "operator", "viewer")
_write = require_role("admin", "operator")


class MonitorIn(BaseModel):
    name: str = Field(min_length=1)
    url: str = Field(min_length=1)
    business: str | None = None
    method: str = "GET"
    expected_status: int = 200
    interval_minutes: int = 5


class MonitorPatch(BaseModel):
    name: str | None = None
    url: str | None = None
    business: str | None = None
    method: str | None = None
    expected_status: int | None = None
    interval_minutes: int | None = None
    enabled: bool | None = None


@router.get("/summary")
def summary(db: Session = Depends(get_db), _=Depends(_read)):
    return uptime.summary(db)


@router.get("")
def list_monitors(db: Session = Depends(get_db), _=Depends(_read)):
    return uptime.list_monitors(db)


@router.post("")
def create_monitor(body: MonitorIn, db: Session = Depends(get_db), _=Depends(_write)):
    m = uptime.create_monitor(db, **body.model_dump())
    return uptime.get_monitor(db, m.id)


@router.get("/{monitor_id}")
def get_monitor(monitor_id: str, db: Session = Depends(get_db), _=Depends(_read)):
    out = uptime.get_monitor(db, monitor_id)
    if out is None:
        raise HTTPException(404, "monitor not found")
    return out


@router.patch("/{monitor_id}")
def update_monitor(monitor_id: str, body: MonitorPatch, db: Session = Depends(get_db), _=Depends(_write)):
    m = uptime.update_monitor(db, monitor_id, **body.model_dump(exclude_unset=True))
    if m is None:
        raise HTTPException(404, "monitor not found")
    return uptime.get_monitor(db, monitor_id)


@router.post("/{monitor_id}/check")
def check_now(monitor_id: str, db: Session = Depends(get_db), _=Depends(_write)):
    from ..models import Monitor
    m = db.get(Monitor, monitor_id)
    if m is None:
        raise HTTPException(404, "monitor not found")
    uptime.check(db, m)
    return uptime.get_monitor(db, monitor_id)


@router.delete("/{monitor_id}")
def delete_monitor(monitor_id: str, db: Session = Depends(get_db), _=Depends(_write)):
    if not uptime.delete_monitor(db, monitor_id):
        raise HTTPException(404, "monitor not found")
    return {"ok": True}
