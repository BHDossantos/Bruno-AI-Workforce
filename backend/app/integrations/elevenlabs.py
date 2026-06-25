"""ElevenLabs text-to-speech (AI voiceover). Returns MP3 bytes, or None when no
key is configured / on error. Used by the video pipeline."""
from __future__ import annotations

import logging

import httpx

from ..config import settings

log = logging.getLogger("bruno.elevenlabs")
_TIMEOUT = httpx.Timeout(60.0, connect=5.0)


def is_configured() -> bool:
    return bool(settings.elevenlabs_api_key)


def tts(text: str) -> bytes | None:
    if not text or not is_configured():
        return None
    try:
        r = httpx.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{settings.elevenlabs_voice_id}",
            headers={"xi-api-key": settings.elevenlabs_api_key, "accept": "audio/mpeg",
                     "content-type": "application/json"},
            json={"text": text[:5000], "model_id": "eleven_multilingual_v2"}, timeout=_TIMEOUT)
        return r.content if r.status_code == 200 else None
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("ElevenLabs TTS failed: %s", exc)
        return None
