"""Music campaign routes: playlists, influencers, content."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import outreach
from ..database import get_db
from ..models import Campaign, Influencer, MusicPlaylist
from ..schemas import CampaignOut, InfluencerOut, PlaylistOut
from ..security import require_role

router = APIRouter(prefix="/music", tags=["music"])
_read = require_role("admin", "operator", "viewer")
_write = require_role("admin", "operator")


@router.get("/playlists", response_model=list[PlaylistOut])
def playlists(limit: int = 100, db: Session = Depends(get_db), _=Depends(_read)):
    return (db.query(MusicPlaylist).order_by(MusicPlaylist.genre_match.desc(),
            MusicPlaylist.created_at.desc()).limit(limit).all())


@router.get("/influencers", response_model=list[InfluencerOut])
def influencers(limit: int = 100, db: Session = Depends(get_db), _=Depends(_read)):
    return db.query(Influencer).order_by(Influencer.created_at.desc()).limit(limit).all()


@router.post("/playlists/{playlist_id}/send")
def send_playlist_pitch(playlist_id: str, db: Session = Depends(get_db), _=Depends(_write)):
    """Reach out to a playlist curator now — emails the pitch."""
    p = db.query(MusicPlaylist).filter(MusicPlaylist.id == playlist_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Playlist not found")
    if not p.email:
        return {"ok": False, "reason": "no curator email on file"}
    msg = outreach.dispatch_email(db, entity_type="playlist", entity_id=p.id,
                                  to_email=p.email, subject=f"Playlist submission — {p.name}",
                                  body=p.pitch, account="personal", actor="manual")
    if msg.status == "Sent" and p.status in (None, "New", "Drafted"):
        p.status = "Sent"
    db.commit()
    return {"ok": True, "status": msg.status, "to": p.email}


@router.post("/influencers/{influencer_id}/send")
def send_influencer_pitch(influencer_id: str, db: Session = Depends(get_db), _=Depends(_write)):
    """Reach out to an influencer now — emails the collab pitch."""
    inf = db.query(Influencer).filter(Influencer.id == influencer_id).first()
    if not inf:
        raise HTTPException(status_code=404, detail="Influencer not found")
    if not inf.email:
        return {"ok": False, "reason": "no email on file"}
    msg = outreach.dispatch_email(db, entity_type="influencer", entity_id=inf.id,
                                  to_email=inf.email, subject="Collab opportunity",
                                  body=inf.collab_pitch or inf.dm_pitch, account="personal", actor="manual")
    if msg.status == "Sent" and inf.status in (None, "New", "Drafted"):
        inf.status = "Sent"
    db.commit()
    return {"ok": True, "status": msg.status, "to": inf.email}


@router.get("/content", response_model=list[CampaignOut])
def content(limit: int = 30, db: Session = Depends(get_db), _=Depends(_read)):
    return (db.query(Campaign).filter(Campaign.channel == "music")
            .order_by(Campaign.created_at.desc()).limit(limit).all())
