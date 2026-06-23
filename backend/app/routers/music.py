"""Music campaign routes: playlists, influencers, content."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Campaign, Influencer, MusicPlaylist
from ..schemas import CampaignOut, InfluencerOut, PlaylistOut
from ..security import require_role

router = APIRouter(prefix="/music", tags=["music"])
_read = require_role("admin", "operator", "viewer")


@router.get("/playlists", response_model=list[PlaylistOut])
def playlists(limit: int = 100, db: Session = Depends(get_db), _=Depends(_read)):
    return (db.query(MusicPlaylist).order_by(MusicPlaylist.genre_match.desc(),
            MusicPlaylist.created_at.desc()).limit(limit).all())


@router.get("/influencers", response_model=list[InfluencerOut])
def influencers(limit: int = 100, db: Session = Depends(get_db), _=Depends(_read)):
    return db.query(Influencer).order_by(Influencer.created_at.desc()).limit(limit).all()


@router.get("/content", response_model=list[CampaignOut])
def content(limit: int = 30, db: Session = Depends(get_db), _=Depends(_read)):
    return (db.query(Campaign).filter(Campaign.channel == "music")
            .order_by(Campaign.created_at.desc()).limit(limit).all())
