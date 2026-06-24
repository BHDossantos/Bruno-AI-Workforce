"""Generate-and-host media for social posting.

Ties AI image generation to public hosting so an agent can turn a text idea into
a publicly-fetchable image URL (required by the Instagram Graph API). Returns
None at any failure point (offline, no bucket, no key) — callers must handle it.
"""
from __future__ import annotations

import logging

from .ai import client
from .integrations import storage

log = logging.getLogger("bruno.media")


def can_generate() -> bool:
    """True only when both image generation and public hosting are available."""
    return client.is_live() and storage.is_configured()


def generate_and_host(prompt: str, name: str) -> str | None:
    """Generate an image from the prompt, host it publicly, return the URL."""
    if not prompt or not storage.is_configured():
        return None
    data = client.generate_image(
        f"High-quality, on-brand Instagram post image. {prompt}. "
        "Clean, modern, professional; no text overlays.")
    if not data:
        return None
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in name)[:60]
    return storage.upload_public(data, f"ig/{safe}.png", "image/png")
