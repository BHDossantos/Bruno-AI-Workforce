"""Live system self-test — pings every configured service and reports what
actually works, so real-API problems surface on demand (not at 6 AM).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from .ai import client
from .config import settings
from .integrations import (facebook_api, gmail, instagram_api, linkedin_api,
                           medium_api, spotify_api, storage, tiktok_api,
                           twitter_api, youtube_api)


def _ok(ok: bool, detail: str = "") -> dict:
    return {"ok": ok, "detail": detail}


def run(db: Session) -> dict:
    checks: dict[str, dict] = {}

    # AI
    checks["openai"] = _ok(client.is_live(), "key set" if client.is_live() else "no OPENAI_API_KEY")

    # Mailboxes
    for acct in ("personal", "insurance"):
        checks[f"gmail_{acct}"] = _ok(gmail.is_configured(acct),
                                      "configured" if gmail.is_configured(acct) else "not configured")

    # Jobs sourcing
    checks["jobs_api"] = _ok(bool(settings.jobs_api_key),
                             "JSearch key set" if settings.jobs_api_key else "free boards only (no JOBS_API_KEY)")

    # Media hosting
    checks["gcs_bucket"] = _ok(storage.is_configured(),
                               settings.gcs_bucket or "no GCS_BUCKET (auto-images off)")

    # Social — do a REAL read against each connected account.
    def social(name, is_conn, probe):
        if not is_conn(db):
            checks[name] = _ok(False, "not connected")
            return
        try:
            checks[name] = _ok(bool(probe()), "live" if probe() else "connected but read failed — check token")
        except Exception as exc:
            checks[name] = _ok(False, f"error: {exc}")

    social("instagram", instagram_api.is_connected, lambda: instagram_api.get_account(db))
    social("facebook", facebook_api.is_connected, lambda: facebook_api.get_page(db))
    social("linkedin", linkedin_api.is_connected, lambda: linkedin_api.get_profile(db))
    social("spotify", spotify_api.is_connected, lambda: spotify_api.overview(db).get("name"))
    social("tiktok", tiktok_api.is_connected, lambda: tiktok_api.verify(db))
    social("youtube", youtube_api.is_connected, lambda: youtube_api.verify(db))
    social("medium", medium_api.is_connected, lambda: medium_api.verify(db))
    checks["x"] = _ok(twitter_api.is_connected(db), "connected" if twitter_api.is_connected(db) else "not connected")

    # Video pipeline (voiceover + cover + render + hosting).
    try:
        from . import video_pipeline
        v = video_pipeline.available()
        can_render = v.get("voiceover") and v.get("hosting") and v.get("render")
        checks["video_pipeline"] = _ok(bool(can_render),
                                       "can produce video" if can_render else f"partial: {v}")
    except Exception as exc:  # pragma: no cover
        checks["video_pipeline"] = _ok(False, f"error: {exc}")

    # Daily-cycle readiness (external cron auth + scheduler config).
    checks["cron_auth"] = _ok(bool(settings.cron_secret),
                              "CRON_SECRET set" if settings.cron_secret else "no CRON_SECRET (cron endpoints open/disabled)")

    ready = sum(1 for c in checks.values() if c["ok"])
    return {"ready": ready, "total": len(checks), "checks": checks}
