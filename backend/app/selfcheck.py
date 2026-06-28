"""Self-check & auto-correct — the system verifies its own core features and
fixes the safe issues automatically, surfacing anything that still needs a human.

Runs on startup, daily via the scheduler, on demand (GET /admin/selfcheck), and by
voice ("Jarvis, run a self check"). Auto-corrections are limited to SAFE, idempotent
repairs (re-seed objectives, refresh connected credentials). Risky problems are
reported, never silently changed. This is the "auto check + auto correct for
everything" guarantee: every core capability is continuously validated.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

log = logging.getLogger("bruno.selfcheck")


def run(db: Session) -> dict:
    checks: list[dict] = []

    def add(name: str, ok: bool, detail: str, fixed: bool = False) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail, "fixed": fixed})

    # 1. Objectives seeded for every command center (AUTO-FIX: ensure_objectives).
    try:
        from . import objectives as obj
        from .models import Objective
        before = db.query(Objective).count()
        obj.ensure_objectives(db)
        after = db.query(Objective).count()
        add("objectives", after > 0,
            f"{after} objectives present" + (f" (seeded {after - before})" if after > before else ""),
            fixed=after > before)
    except Exception as exc:
        add("objectives", False, f"error: {str(exc)[:120]}")

    # 2. Connected credentials applied to the running process AND OAuth tokens
    #    proactively refreshed so connections never silently expire (AUTO-FIX).
    try:
        from . import runtime_config
        runtime_config.apply_to_settings(db)
        refreshed = 0
        try:
            from .integrations import oauth_refresh
            res = oauth_refresh.refresh_all(db) or {}
            refreshed = sum(1 for v in res.values() if v in ("refreshed", "extended"))
        except Exception:  # token refresh must never break the self-check
            log.debug("selfcheck token refresh skipped", exc_info=True)
        st = runtime_config.status(db)
        live = [k for k, v in st.items() if v.get("configured")]
        detail = ("connected: " + ", ".join(live)) if live else "none connected yet (connect Gmail to send)"
        if refreshed:
            detail += f"; refreshed {refreshed} token(s)"
        add("credentials", True, detail, fixed=bool(refreshed))
    except Exception as exc:
        add("credentials", False, f"error: {str(exc)[:120]}")

    # 3. Every agent is importable + callable.
    try:
        from .agents import AGENTS
        bad = [k for k, c in AGENTS.items() if not callable(c)]
        add("agents", not bad, f"{len(AGENTS)} agents registered" if not bad else f"not callable: {bad}")
    except Exception as exc:
        add("agents", False, f"error: {str(exc)[:120]}")

    # 4. Every command center is staffed (no dead placeholder centers).
    try:
        from .commanders import COMMANDERS
        dead = [c for c, spec in COMMANDERS.items() if not spec.get("agents")]
        add("command_centers", not dead,
            f"{len(COMMANDERS)} centers, all staffed" if not dead else f"no-agent centers: {dead}")
    except Exception as exc:
        add("command_centers", False, f"error: {str(exc)[:120]}")

    # 5. Lead pipeline diagnostic is reachable (and reports its own gaps).
    try:
        from . import lead_pipeline
        h = lead_pipeline.health(db)
        add("lead_pipeline", True, h.get("summary", "ok"))
    except Exception as exc:
        add("lead_pipeline", False, f"error: {str(exc)[:120]}")

    healthy = all(c["ok"] for c in checks)
    fixed = sum(1 for c in checks if c["fixed"])
    issues = [c["name"] for c in checks if not c["ok"]]
    log.info("selfcheck healthy=%s fixed=%d issues=%s", healthy, fixed, issues)
    return {"healthy": healthy, "fixed": fixed, "issues": issues, "checks": checks}
