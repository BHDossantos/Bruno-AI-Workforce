"""Agent 4: Music Marketing — runs daily at 8 AM."""
from __future__ import annotations

import logging
from datetime import date

from .. import brand
from ..ai import client, skills
from ..ai.prompts import INFLUENCER_PITCH, MUSIC_DAILY_CONTENT, PLAYLIST_PITCH
from ..integrations import providers
from ..models import Campaign, Influencer, MusicPlaylist
from .base import BaseAgent

log = logging.getLogger("bruno.agents.music")

ARTIST_GENRES = {"samba", "pagode", "brazilian jazz", "latin romance", "r&b",
                 "romantic", "italian", "spanish", "portuguese"}
PLAYLIST_TARGET = 50
INFLUENCER_TARGET = 25


class MusicAgent(BaseAgent):
    key = "music"
    name = "Music Marketing Agent"
    description = "Produces a daily content package and pitches playlists + influencers."
    schedule_cron = "0 8 * * *"  # 8 AM

    @staticmethod
    def genre_match(genre: str) -> int:
        return 100 if (genre or "").lower() in ARTIST_GENRES else 50

    def execute(self) -> dict:
        p = brand.get_profile(self.db)
        brand_ctx = brand.context(self.db)
        artist = p.music_artist or p.business_name or "the artist"
        genres = p.music_genres or "Brazilian/Latin/romantic"

        # Daily content package is the core deliverable — always generate it first.
        content = client.complete_json(
            MUSIC_DAILY_CONTENT.format(brand=brand_ctx, artist=artist, genres=genres),
            system=skills.system_prompt("social"))
        self.db.add(Campaign(channel="music", title=f"Music content {date.today()}",
                             content=content if isinstance(content, dict) else {},
                             scheduled_for=date.today()))
        self.db.commit()

        copy_system = skills.system_prompt("copywriting", "cold-email")
        sent = 0
        for pl in providers.fetch_playlists(PLAYLIST_TARGET):
            try:
                pitch = client.complete_json(
                    PLAYLIST_PITCH.format(name=pl["name"], genre=pl["genre"], curator=pl["curator_name"]),
                    system=copy_system)
                body = pitch.get("pitch") if isinstance(pitch, dict) else None
                row = MusicPlaylist(
                    name=pl["name"], curator_name=pl["curator_name"], genre=pl["genre"],
                    submission_link=pl["submission_link"], email=pl["email"], instagram=pl["instagram"],
                    followers=pl["followers"], genre_match=self.genre_match(pl["genre"]),
                    pitch=body, status="Drafted")
                self.db.add(row)
                self.db.flush()
                msg = self.dispatch_email(entity_type="playlist", entity_id=row.id, to_email=pl.get("email"),
                                          subject=f"Playlist submission for {pl['name']}", body=body,
                                          account="personal")
                if msg.status == "Sent":
                    row.status = "Sent"
                    sent += 1
                self.schedule_follow_ups("playlist", row.id)
                self.db.commit()
            except Exception:
                log.exception("Playlist pitch failed for %s", pl.get("name"))
                self.db.rollback()

        for inf in providers.fetch_influencers(INFLUENCER_TARGET):
            try:
                pitch = client.complete_json(
                    INFLUENCER_PITCH.format(name=inf["name"], niche=inf["niche"],
                                            platform=inf["platform"], handle=inf["handle"]),
                    system=skills.system_prompt("social", "copywriting"))
                dm = pitch.get("dm_pitch") if isinstance(pitch, dict) else None
                collab = pitch.get("collab_pitch") if isinstance(pitch, dict) else None
                row = Influencer(
                    name=inf["name"], niche=inf["niche"], platform=inf["platform"], handle=inf["handle"],
                    followers=inf["followers"], email=inf["email"], dm_pitch=dm, collab_pitch=collab,
                    status="Drafted")
                self.db.add(row)
                self.db.flush()
                msg = self.dispatch_email(entity_type="influencer", entity_id=row.id, to_email=inf.get("email"),
                                          subject=f"Collab idea with {inf['name']}", body=collab or dm,
                                          account="personal")
                if msg.status == "Sent":
                    row.status = "Sent"
                    sent += 1
                self.schedule_follow_ups("influencer", row.id)
                self.db.commit()
            except Exception:
                log.exception("Influencer pitch failed for %s", inf.get("name"))
                self.db.rollback()

        n_pl = self.db.query(MusicPlaylist).count()
        n_inf = self.db.query(Influencer).count()
        self.log_action("music_generated", entity="music", detail={"sent": sent})
        return {
            "summary": f"Generated today's music content package for {artist}; "
                       f"pitched playlists/influencers, auto-sent {sent}.",
            "content": bool(content),
            "playlists_total": n_pl,
            "influencers_total": n_inf,
            "sent": sent,
        }
