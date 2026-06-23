"""Agent 4: Music Marketing — runs daily at 8 AM."""
from __future__ import annotations

from datetime import date

from ..ai import client
from ..ai.prompts import (
    INFLUENCER_PITCH,
    MUSIC_DAILY_CONTENT,
    PLAYLIST_PITCH,
)
from ..integrations import providers
from ..models import Campaign, Influencer, MusicPlaylist
from .base import BaseAgent

# Artist target genres for genre-match scoring.
ARTIST_GENRES = {"samba", "pagode", "brazilian jazz", "latin romance", "r&b",
                 "romantic", "italian", "spanish", "portuguese"}
PLAYLIST_TARGET = 50
INFLUENCER_TARGET = 25


class MusicAgent(BaseAgent):
    key = "music"
    name = "Music Marketing Agent"
    description = "Finds playlists + influencers, drafts pitches, and produces a daily content package."
    schedule_cron = "0 8 * * *"  # 8 AM

    @staticmethod
    def genre_match(genre: str) -> int:
        return 100 if (genre or "").lower() in ARTIST_GENRES else 50

    def execute(self) -> dict:
        playlists = providers.fetch_playlists(PLAYLIST_TARGET)
        influencers = providers.fetch_influencers(INFLUENCER_TARGET)

        for p in playlists:
            pitch = client.complete_json(PLAYLIST_PITCH.format(
                name=p["name"], genre=p["genre"], curator=p["curator_name"]))
            self.db.add(MusicPlaylist(
                name=p["name"], curator_name=p["curator_name"], genre=p["genre"],
                submission_link=p["submission_link"], email=p["email"], instagram=p["instagram"],
                followers=p["followers"], genre_match=self.genre_match(p["genre"]),
                pitch=pitch.get("pitch") if isinstance(pitch, dict) else None, status="Drafted",
            ))

        for inf in influencers:
            pitch = client.complete_json(INFLUENCER_PITCH.format(
                name=inf["name"], niche=inf["niche"], platform=inf["platform"], handle=inf["handle"]))
            self.db.add(Influencer(
                name=inf["name"], niche=inf["niche"], platform=inf["platform"], handle=inf["handle"],
                followers=inf["followers"], email=inf["email"],
                dm_pitch=pitch.get("dm_pitch") if isinstance(pitch, dict) else None,
                collab_pitch=pitch.get("collab_pitch") if isinstance(pitch, dict) else None,
                status="Drafted",
            ))

        # Daily content package.
        content = client.complete_json(MUSIC_DAILY_CONTENT)
        self.db.add(Campaign(channel="music", title=f"Music content {date.today()}",
                             content=content if isinstance(content, dict) else {}, scheduled_for=date.today()))

        self.log_action("music_generated", entity="music",
                        detail={"playlists": len(playlists), "influencers": len(influencers)})
        return {
            "summary": f"Found {len(playlists)} playlists and {len(influencers)} influencers; "
                       f"generated daily content package.",
            "playlists": len(playlists),
            "influencers": len(influencers),
        }
