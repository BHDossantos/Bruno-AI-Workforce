"""Per-business on/off switches.

Which sales / content engines actually run their scheduled agents + jobs. Insurance
is ON by default; every other business (B&B Global consulting, SavoryMind, Music,
auto job-apply, content/social) is OFF so the app defaults to the lean insurance-only
cost profile. Flip each one on in Setup → Businesses to test it end-to-end.

Each flag is a runtime setting (biz_<name>_enabled), so toggling takes effect on the
next scheduled run — no redeploy. The maps below assign every scheduler agent + job
to a business; anything unmapped (shared infra, CEO dashboard) always runs.
"""
from __future__ import annotations

from .config import settings

# Order = how they appear in the UI.
ALL = ["insurance", "bnb", "savorymind", "music", "jobs", "content"]
LABELS = {
    "insurance": "Insurance — Thrust",
    "bnb": "B&B Global — consulting",
    "savorymind": "SavoryMind — restaurants",
    "music": "Music",
    "jobs": "Auto job-apply",
    "content": "Content & social",
}
def _default_on() -> set[str]:
    """Which businesses are on when their flag is UNSET — driven by autonomy_profile
    for back-compat: 'insurance' → just insurance; anything else → all of them."""
    prof = (settings.autonomy_profile or "all").strip().lower()
    return {"insurance"} if prof == "insurance" else set(ALL)

# agent key -> business (from app.agents.AGENTS)
_AGENTS = {
    "insurance": {"insurance", "commercial_finder", "home_finder", "auto_finder",
                  "homeowner", "referral_partner", "follow_up_agent", "review_referral"},
    "bnb": {"bnbglobal"},
    "savorymind": {"savorymind"},
    "music": {"music", "music_collab", "music_pr", "music_sync"},
    "jobs": {"job_hunter"},
    "content": {"instagram", "foundation_outreach", "grant_research", "school_partner",
                "ceo_dashboard", "life_ops"},
}
# scheduled job key -> business (from scheduler._JOBS). Kept identical to the old
# insurance-only set so toggling nothing preserves today's behavior exactly.
_JOBS = {
    "insurance": {"client_autoscale", "leads", "auto_outreach", "flush_drafts",
                  "followups", "sms_followups", "booking_nudges", "lifecycle",
                  "outreach_digest", "referrals", "auto_dial", "everquote_drafts"},
    "music": {"music_releases"},
    "jobs": {"auto_apply"},
    # Content/social + the cross-business command & analytics jobs (these were OFF in
    # insurance-only mode, so they live behind the content toggle).
    "content": {"publish_content", "publish_blog", "newsletters",
                "board_report", "ceo_daily", "content_metrics", "platform_loops"},
}
# Truly cross-cutting infrastructure — always runs (OAuth refresh, self-check).
_CORE_JOBS = {"refresh_tokens", "selfcheck"}


def _on(name: str) -> bool:
    """A business's on/off. Explicit 'true'/'false' wins; empty follows autonomy_profile."""
    s = str(getattr(settings, f"biz_{name}_enabled", "") or "").strip().lower()
    if s in ("1", "true", "yes", "on"):
        return True
    if s in ("0", "false", "no", "off"):
        return False
    return name in _default_on()


def enabled() -> set[str]:
    return {b for b in ALL if _on(b)}


def is_on(name: str) -> bool:
    return _on(name)


def status() -> list[dict]:
    """For the UI: each business with its label + on/off state, in display order."""
    return [{"key": b, "label": LABELS[b], "on": _on(b)} for b in ALL]


def _business_of(key: str, table: dict) -> str | None:
    for biz, keys in table.items():
        if key in keys:
            return biz
    return None


def agent_enabled(key: str) -> bool:
    biz = _business_of(key, _AGENTS)
    return biz is None or biz in enabled()   # unmapped (ceo_dashboard, life_ops) always on


def job_enabled(key: str) -> bool:
    if key in _CORE_JOBS:
        return True
    biz = _business_of(key, _JOBS)
    return biz is None or biz in enabled()
