"""Music campaign routes: playlists, influencers, content."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import outreach
from ..database import get_db
from ..integrations import spotify_api
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


@router.get("/brand")
def brand_bible(db: Session = Depends(get_db), _=Depends(_read)):
    """The Bruno D brand bible the content engine is built on — identity, category,
    signature, the era arc, playlist lanes to own, and the story angles every post
    draws from. This is what keeps the music universe consistent across channels."""
    from .. import music_brand
    return {
        "artist": music_brand.artist(db),
        "category": music_brand.CATEGORY,
        "identity": music_brand.IDENTITY,
        "edge": music_brand.EDGE,
        "signature": music_brand.SIGNATURE,
        "genres": music_brand.genres(db),
        "links": music_brand.links(db),
        "cities": music_brand.CITIES,
        "eras": music_brand.ERAS,
        "playlist_targets": music_brand.PLAYLIST_TARGETS,
        "content_angles": music_brand.CONTENT_ANGLES,
        "channels": music_brand.CHANNELS,
        "not_on": ["linkedin"],
    }


@router.get("/spotify")
def spotify(db: Session = Depends(get_db), _=Depends(_read)):
    """Live Spotify artist analytics (followers, top tracks) when connected."""
    return spotify_api.overview(db)


@router.get("/content", response_model=list[CampaignOut])
def content(limit: int = 30, db: Session = Depends(get_db), _=Depends(_read)):
    return (db.query(Campaign).filter(Campaign.channel == "music")
            .order_by(Campaign.created_at.desc()).limit(limit).all())
