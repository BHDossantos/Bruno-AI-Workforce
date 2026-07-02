"""Music campaign routes: playlists, influencers, content."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import music_release, outreach
from ..database import get_db
from ..integrations import spotify_api
from ..models import Campaign, Influencer, MusicPlaylist, MusicRelease
from ..schemas import (CampaignOut, InfluencerOut, MusicReleaseCreate, MusicReleaseOut,
                       PlaylistOut, ReleasePieceOut)
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


@router.get("/catalog")
def catalog(_=Depends(_read)):
    """The artist's real released discography (albums, tracks, singles) plus the
    top-streamed 'popular' set to focus on — so the promotion engine works from
    actual songs, not placeholders."""
    from .. import music_catalog
    return {"stats": music_catalog.stats(), "popular": music_catalog.popular(),
            "albums": music_catalog.all_albums()}


class PromoteIn(BaseModel):
    title: str


def _promote_one(db: Session, title: str) -> MusicRelease | None:
    """Create a MusicRelease from a catalog song, idempotently. None if unknown."""
    from .. import music_catalog
    track = music_catalog.find_track(title)
    if not track:
        return None
    existing = db.query(MusicRelease).filter(MusicRelease.title == track["title"]).first()
    if existing:
        return existing
    r = MusicRelease(title=track["title"], era=track["album"], story=track["theme"],
                     language=track["language"], status="Planned")
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


@router.post("/catalog/promote", response_model=MusicReleaseOut)
def promote_catalog_track(payload: PromoteIn, db: Session = Depends(get_db), _=Depends(_write)):
    """Turn a real catalog song into a MusicRelease (its era) so its full content
    kit can be built. Idempotent — returns the existing release if already made."""
    r = _promote_one(db, payload.title)
    if not r:
        raise HTTPException(status_code=404, detail="Song not found in the catalog")
    return r


@router.post("/catalog/promote-top10")
def promote_top10(db: Session = Depends(get_db), _=Depends(_write)):
    """Promote all of the top-streamed 'Popular' songs in one click, so the
    priority set is queued as releases ready for content kits. Idempotent."""
    from .. import music_catalog
    promoted = []
    for row in music_catalog.popular():
        r = _promote_one(db, row["title"])
        if r:
            promoted.append({"id": str(r.id), "title": r.title, "rank": row["rank"]})
    return {"ok": True, "promoted": len(promoted), "releases": promoted}


@router.get("/releases", response_model=list[MusicReleaseOut])
def releases(db: Session = Depends(get_db), _=Depends(_read)):
    return db.query(MusicRelease).order_by(MusicRelease.created_at.desc()).limit(100).all()


@router.post("/releases", response_model=MusicReleaseOut)
def create_release(payload: MusicReleaseCreate, db: Session = Depends(get_db), _=Depends(_write)):
    r = MusicRelease(**payload.model_dump(exclude_none=True))
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


@router.post("/releases/{release_id}/kit")
def build_release_kit(release_id: str, db: Session = Depends(get_db), _=Depends(_write)):
    """Generate the full 15-20 piece content kit for this song (one era moment)."""
    r = db.query(MusicRelease).filter(MusicRelease.id == release_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Release not found")
    return music_release.build_kit(db, r)


@router.get("/releases/{release_id}/pieces", response_model=list[ReleasePieceOut])
def release_pieces(release_id: str, db: Session = Depends(get_db), _=Depends(_read)):
    return music_release.pieces_for(db, release_id)


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
