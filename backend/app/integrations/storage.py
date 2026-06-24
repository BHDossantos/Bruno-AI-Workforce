"""Public object hosting on Google Cloud Storage.

Uploads bytes to the configured public bucket and returns a public URL. Used to
host AI-generated images so the Instagram Graph API (which fetches media from a
public URL) can publish them. No-ops (returns None) when no bucket is set or the
library/credentials are unavailable, so nothing breaks offline or in CI.
"""
from __future__ import annotations

import logging

from ..config import settings

log = logging.getLogger("bruno.storage")


def is_configured() -> bool:
    return bool(settings.gcs_bucket)


def upload_public(data: bytes, name: str, content_type: str = "image/png") -> str | None:
    """Upload bytes to the public bucket; return the public URL or None."""
    if not data or not settings.gcs_bucket:
        return None
    try:
        from google.cloud import storage  # imported lazily — optional dependency

        client = storage.Client()
        blob = client.bucket(settings.gcs_bucket).blob(name)
        blob.upload_from_string(data, content_type=content_type)
        return f"https://storage.googleapis.com/{settings.gcs_bucket}/{name}"
    except Exception as exc:  # pragma: no cover - network/credentials guard
        log.warning("GCS upload failed (%s): %s", name, exc)
        return None
