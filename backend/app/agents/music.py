"""Agent 4: Music Marketing — runs daily at 8 AM."""
from __future__ import annotations

from datetime import date

from ..ai import client, skills
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
    description = "Finds playlists + influencers, auto-sends pitches, and produces a daily content package."
    schedule_cron = "0 8 * * *"  # 8 AM

    @staticmethod
    def genre_match(genre: str) -> int:
        return 100 if (genre or "").lower() in ARTIST_GENRES else 50

    def execute(self) -> dict:
        playlists = providers.fetch_playlists(PLAYLIST_TARGET)
        influencers = providers.fetch_influencers(INFLUENCER_TARGET)
        copy_system = skills.system_prompt("copywriting", "cold-email")
        sent = 0

        for p in playlists:
            pitch = client.complete_json(
                PLAYLIST_PITCH.format(name=p["name"], genre=p["genre"], curator=p["curator_name"]),
                system=copy_system)
            body = pitch.get("pitch") if isinstance(pitch, dict) else None
            row = MusicPlaylist(
                name=p["name"], curator_name=p["curator_name"], genre=p["genre"],
                submission_link=p["submission_link"], email=p["email"], instagram=p["instagram"],
                followers=p["followers"], genre_match=self.genre_match(p["genre"]),
                pitch=body, status="Drafted",
            )
            self.db.add(row)
            self.db.flush()
            msg = self.dispatch_email(entity_type="playlist", entity_id=row.id, to_email=p.get("email"),
                                      subject=f"Playlist submission for {p['name']}", body=body,
                                      account="personal")
            if msg.status == "Sent":
                row.status = "Sent"
                sent += 1
            self.schedule_follow_ups("playlist", row.id)

        for inf in influencers:
            pitch = client.complete_json(
                INFLUENCER_PITCH.format(name=inf["name"], niche=inf["niche"],
                                        platform=inf["platform"], handle=inf["handle"]),
                system=skills.system_prompt("social", "copywriting"))
            dm = pitch.get("dm_pitch") if isinstance(pitch, dict) else None
            collab = pitch.get("collab_pitch") if isinstance(pitch, dict) else None
            row = Influencer(
                name=inf["name"], niche=inf["niche"], platform=inf["platform"], handle=inf["handle"],
                followers=inf["followers"], email=inf["email"], dm_pitch=dm, collab_pitch=collab,
                status="Drafted",
            )
            self.db.add(row)
            self.db.flush()
            msg = self.dispatch_email(entity_type="influencer", entity_id=row.id, to_email=inf.get("email"),
                                      subject=f"Collab idea with {inf['name']}", body=collab or dm,
                                      account="personal")
            if msg.status == "Sent":
                row.status = "Sent"
                sent += 1
            self.schedule_follow_ups("influencer", row.id)

        # Daily content package (uses the social skill).
        content = client.complete_json(MUSIC_DAILY_CONTENT, system=skills.system_prompt("social"))
        self.db.add(Campaign(channel="music", title=f"Music content {date.today()}",
                             content=content if isinstance(content, dict) else {}, scheduled_for=date.today()))

        self.log_action("music_generated", entity="music",
                        detail={"playlists": len(playlists), "influencers": len(influencers), "sent": sent})
        return {
            "summary": f"Found {len(playlists)} playlists and {len(influencers)} influencers; "
                       f"auto-sent {sent} pitches; generated daily content package.",
            "playlists": len(playlists),
            "influencers": len(influencers),
            "sent": sent,
        }
