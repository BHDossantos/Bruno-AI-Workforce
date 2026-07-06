"""Thin OpenAI wrapper with a deterministic offline fallback.

When no OpenAI key is configured the helpers return clearly-marked stub content
so the whole pipeline (agents, scheduler, dashboard) runs end-to-end without
external credentials. Connect a real key — via env var OR the in-app Setup page
(runtime_config) — to get production output.

The client is built lazily from the CURRENT ``settings.openai_api_key`` and
rebuilt whenever that key changes, so a key connected at runtime through Setup
takes effect immediately without a redeploy (the module used to build the client
once at import, which meant a Setup-saved key silently never activated).
"""
from __future__ import annotations

import json
import logging

from ..config import settings

log = logging.getLogger("bruno.ai")

try:  # OpenAI is optional at import time so the app boots without it.
    from openai import OpenAI as _OpenAI
except Exception:  # pragma: no cover - import guard
    _OpenAI = None

_client = None
_client_key: str | None = None  # the api key the cached client was built with


def _get_client():
    """Return the OpenAI client for the current key, (re)building it on change.

    Cheap: only reconstructs when ``settings.openai_api_key`` actually differs
    from the key the cached client was built with (e.g. first connect via Setup,
    or a key rotation), so hot-path callers pay nothing on the common case."""
    global _client, _client_key
    key = (settings.openai_api_key or "").strip()
    if key != _client_key:
        _client_key = key
        try:
            _client = _OpenAI(api_key=key) if (key and _OpenAI is not None) else None
        except Exception:  # pragma: no cover - construction guard
            _client = None
    return _client


def is_live() -> bool:
    return _get_client() is not None


def complete(prompt: str, *, system: str = "You are a helpful assistant.", temperature: float = 0.7) -> str:
    """Return a free-text completion, or a stub when no API key is configured."""
    client = _get_client()
    if client is None:
        return f"[stub output — set OPENAI_API_KEY to generate]\n{prompt[:200]}"
    try:
        resp = client.chat.completions.create(
            model=settings.openai_model,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        )
        return resp.choices[0].message.content or ""
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("OpenAI completion failed: %s", exc)
        return f"[error generating content: {exc}]"


def complete_json(prompt: str, *, system: str = "You output only valid JSON.") -> dict | list:
    """Return parsed JSON from the model, or an empty structure on failure."""
    client = _get_client()
    if client is None:
        return {}
    try:
        resp = client.chat.completions.create(
            model=settings.openai_model,
            temperature=0.4,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        )
        return json.loads(resp.choices[0].message.content or "{}")
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("OpenAI JSON completion failed: %s", exc)
        return {}


def transcribe(audio: bytes, filename: str = "call.mp3") -> str | None:
    """Transcribe a call recording (mp3/wav bytes) via Whisper. None when offline."""
    client = _get_client()
    if client is None or not audio:
        return None
    try:
        import io
        buf = io.BytesIO(audio)
        buf.name = filename
        resp = client.audio.transcriptions.create(model="whisper-1", file=buf)
        return getattr(resp, "text", None) or None
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("OpenAI transcription failed: %s", exc)
        return None


def embed(text: str) -> list[float] | None:
    """Return an embedding vector for the text, or None when offline/unavailable.

    Used by the memory/knowledge layer for semantic recall. Callers must handle
    None and fall back to keyword search.
    """
    client = _get_client()
    if client is None or not text:
        return None
    try:
        resp = client.embeddings.create(
            model=settings.embedding_model, input=text[:8000])
        return resp.data[0].embedding
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("OpenAI embedding failed: %s", exc)
        return None


def speech(text: str, *, voice: str | None = None, instructions: str | None = None) -> bytes | None:
    """Synthesize speech with a real neural voice and return MP3 bytes, or None
    when offline. Used to give the Jennifer assistant a warm, natural voice instead
    of the robotic built-in browser TTS."""
    client = _get_client()
    if client is None or not text:
        return None
    try:
        kwargs = {
            "model": settings.voice_tts_model,
            "voice": voice or settings.voice_tts_voice,
            "input": text[:4000],
            "response_format": "mp3",
        }
        # gpt-4o-mini-tts supports a free-text style instruction; older tts-1 doesn't.
        instr = instructions or settings.voice_tts_instructions
        if instr and "gpt-4o" in settings.voice_tts_model:
            kwargs["instructions"] = instr
        resp = client.audio.speech.create(**kwargs)
        return resp.read() if hasattr(resp, "read") else getattr(resp, "content", None)
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("OpenAI TTS failed: %s", exc)
        return None


def generate_image(prompt: str, *, size: str = "1024x1024") -> bytes | None:
    """Generate a social image and return raw PNG bytes, or None when offline.

    Used by the Instagram auto-publisher (Instagram requires real media)."""
    client = _get_client()
    if client is None or not prompt:
        return None
    try:
        import base64

        resp = client.images.generate(model=settings.image_model, prompt=prompt[:4000], size=size)
        item = resp.data[0]
        b64 = getattr(item, "b64_json", None)
        if b64:
            return base64.b64decode(b64)
        url = getattr(item, "url", None)
        if url:
            import httpx
            r = httpx.get(url, timeout=30.0)
            return r.content if r.status_code == 200 else None
        return None
    except Exception as exc:  # pragma: no cover - network guard
        log.warning("OpenAI image generation failed: %s", exc)
        return None
