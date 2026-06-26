"""Music PR + Collaboration outreach agents.

Both draft personalized pitches (never sent automatically in semi-auto — they wait
in review) and never contact the same target twice. They reuse the Influencer model
for storage so they show on the Music page and flow through the follow-up engine.
Sources are synthetic placeholders until a PR/artist data source is wired.
"""
from __future__ import annotations

import logging

from .. import memory
from ..ai import client, skills
from ..ai.prompts import COLLAB_PITCH, MUSIC_PR_PITCH
from ..integrations import providers
from ..models import Influencer
from .base import BaseAgent

log = logging.getLogger("bruno.agents.music_outreach")


def _seen_emails(db) -> set[str]:
    return {(e or "").lower() for (e,) in db.query(Influencer.email)
            .filter(Influencer.email.isnot(None)).all()}


class MusicPRAgent(BaseAgent):
    key = "music_pr"
    name = "Music PR Agent"
    description = "Drafts press pitches (blogs, podcasts, radio) for the latest release."
    schedule_cron = "0 14 * * *"

    def execute(self) -> dict:
        seen = _seen_emails(self.db)
        sys = skills.system_prompt("public-relations", "copywriting")
        made = 0
        for o in providers.fetch_music_pr(30):
            if (o.get("email") or "").lower() in seen:
                continue
            try:
                mem = memory.entity_context(self.db, name=o.get("contact"), email=o.get("email"))
                art = client.complete_json(MUSIC_PR_PITCH.format(
                    name=o["name"], kind=o["kind"], focus=o["focus"],
                    contact=o.get("contact") or "", memory=mem), system=sys) if client.is_live() else {}
                pitch = art.get("pitch") if isinstance(art, dict) else None
                row = Influencer(name=o["name"], niche=f"PR · {o['kind']}", platform="press",
                                 handle=o["name"], email=o.get("email"), dm_pitch=pitch, status="Drafted")
                self.db.add(row)
                self.db.flush()
                self.dispatch_email(entity_type="influencer", entity_id=row.id, to_email=o.get("email"),
                                    subject=f"Story idea for {o['name']}", body=pitch, account="personal")
                self.schedule_follow_ups("influencer", row.id)
                seen.add((o.get("email") or "").lower())
                made += 1
                self.db.commit()
            except Exception:
                log.exception("music PR pitch failed for %s", o.get("name"))
                self.db.rollback()
        self.log_action("music_pr", entity="music", detail={"drafted": made})
        return {"summary": f"Music PR: drafted {made} press pitch(es) for review.", "drafted": made}


class CollaborationAgent(BaseAgent):
    key = "music_collab"
    name = "Music Collaboration Agent"
    description = "Drafts collaboration pitches to similarly-sized indie artists."
    schedule_cron = "0 16 * * *"

    def execute(self) -> dict:
        seen = _seen_emails(self.db)
        sys = skills.system_prompt("copywriting", "marketing-psychology")
        made = 0
        for a in providers.fetch_collab_artists(20):
            if (a.get("email") or "").lower() in seen:
                continue
            try:
                mem = memory.entity_context(self.db, name=a.get("name"), email=a.get("email"))
                art = client.complete_json(COLLAB_PITCH.format(
                    name=a["name"], genre=a["genre"], listeners=a["listeners"],
                    platform=a["platform"], memory=mem), system=sys) if client.is_live() else {}
                pitch = art.get("pitch") if isinstance(art, dict) else None
                row = Influencer(name=a["name"], niche="Collaboration", platform=a["platform"],
                                 handle=a["name"], followers=a.get("listeners"),
                                 email=a.get("email"), collab_pitch=pitch, status="Drafted")
                self.db.add(row)
                self.db.flush()
                self.dispatch_email(entity_type="influencer", entity_id=row.id, to_email=a.get("email"),
                                    subject=f"Collab idea — {a['name']}", body=pitch, account="personal")
                self.schedule_follow_ups("influencer", row.id)
                seen.add((a.get("email") or "").lower())
                made += 1
                self.db.commit()
            except Exception:
                log.exception("collab pitch failed for %s", a.get("name"))
                self.db.rollback()
        self.log_action("music_collab", entity="music", detail={"drafted": made})
        return {"summary": f"Collaboration: drafted {made} artist collab pitch(es) for review.", "drafted": made}
