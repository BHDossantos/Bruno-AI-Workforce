"""Thin OpenAI wrapper with a deterministic offline fallback.

When ``OPENAI_API_KEY`` is unset the helpers return clearly-marked stub content
so the whole pipeline (agents, scheduler, dashboard) runs end-to-end without
external credentials. Wire a real key to get production output.
"""
from __future__ import annotations

import json
import logging

from ..config import settings

log = logging.getLogger("bruno.ai")

try:  # OpenAI is optional at import time so the app boots without it.
    from openai import OpenAI

    _client: OpenAI | None = OpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None
except Exception:  # pragma: no cover - import guard
    _client = None


def is_live() -> bool:
    return _client is not None


def complete(prompt: str, *, system: str = "You are a helpful assistant.", temperature: float = 0.7) -> str:
    """Return a free-text completion, or a stub when no API key is configured."""
    if _client is None:
        return f"[stub output — set OPENAI_API_KEY to generate]\n{prompt[:200]}"
    try:
        resp = _client.chat.completions.create(
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
    if _client is None:
        return {}
    try:
        resp = _client.chat.completions.create(
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
