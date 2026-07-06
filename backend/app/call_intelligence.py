"""Post-call intelligence: transcribe the recording, summarize with AI, and log
it to the lead's timeline (the 📞 counter + activity feed stay real)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy.orm import Session

from .ai import client
from .config import settings
from .models import Lead, Message

log = logging.getLogger("bruno.call_intel")

_PROMPT = (
    "You are a sales-call assistant for a licensed insurance producer. From this "
    "call transcript, return JSON with:\n"
    '  "summary": a 2-3 sentence recap,\n'
    '  "sentiment": "positive" | "neutral" | "negative",\n'
    '  "objections": array of objections raised (strings),\n'
    '  "next_steps": array of concrete next actions (strings),\n'
    '  "outcome": one of "reached" | "voicemail" | "no_answer" | "not_interested" '
    '| "interested" | "quoted".\n\nTranscript:\n{t}'
)


def _download(recording_url: str) -> bytes | None:
    if not recording_url:
        return None
    url = recording_url if recording_url.endswith(".mp3") else recording_url + ".mp3"
    try:
        r = httpx.get(url, auth=(settings.twilio_account_sid, settings.twilio_auth_token), timeout=60)
        r.raise_for_status()
        return r.content
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("recording download failed: %s", exc)
        return None


def summarize_transcript(transcript: str) -> dict:
    if not transcript:
        return {}
    out = client.complete_json(_PROMPT.format(t=transcript[:6000]))
    return out if isinstance(out, dict) else {}


def format_note(notes: dict, transcript: str | None, duration: int | None) -> str:
    lines = ["📞 Call logged" + (f" · {duration}s" if duration else "")]
    if notes.get("outcome"):
        lines.append(f"Outcome: {notes['outcome']}")
    if notes.get("summary"):
        lines.append(notes["summary"])
    if notes.get("objections"):
        lines.append("Objections: " + "; ".join(notes["objections"]))
    if notes.get("next_steps"):
        lines.append("Next: " + "; ".join(notes["next_steps"]))
    if notes.get("sentiment"):
        lines.append(f"Sentiment: {notes['sentiment']}")
    if not notes and transcript:
        lines.append(transcript[:500])
    return "\n".join(lines)


def process_recording(db: Session, *, lead_id: str | None, recording_url: str,
                      duration: int | None, call_sid: str | None) -> dict:
    """Transcribe → AI-summarize → log a call Message on the lead's timeline."""
    audio = _download(recording_url)
    transcript = client.transcribe(audio) if audio else None
    notes = summarize_transcript(transcript) if transcript else {}
    body = format_note(notes, transcript, duration)

    msg = Message(channel="call", direction="outbound", entity_type="lead",
                  entity_id=lead_id, from_account="insurance", body=body,
                  status="Logged", provider_id=call_sid,
                  sent_at=datetime.now(timezone.utc))
    db.add(msg)
    if lead_id:
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if lead:
            lead.times_contacted = (lead.times_contacted or 0) + 1
            lead.last_contacted_at = datetime.now(timezone.utc)
    db.commit()
    return {"transcribed": bool(transcript), "notes": notes}
