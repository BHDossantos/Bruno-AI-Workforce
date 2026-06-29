"""One-shot "work the pipeline" — source + draft everything, queue for approval.

Runs every lead-sourcing agent and the content loops in one pass so the user (or
"Hey Jennifer, work the pipeline") can fill the Approval Queue on demand. Respects
the Emergency Stop; in semi-auto everything lands as drafts to approve.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

log = logging.getLogger("bruno.pipeline_run")

# Sourcing agents across every revenue line.
_SOURCERS = ("commercial_finder", "homeowner", "insurance", "referral_partner",
             "bnbglobal", "savorymind", "grant_research", "foundation_outreach")


def work_pipeline(db: Session) -> dict:
    from . import control, platform_loops
    from .agents import AGENTS
    if control.is_paused_safe(db):
        return {"ok": False, "paused": True,
                "summary": "Agents are paused (Emergency Stop). Resume to work the pipeline."}

    sourced: dict[str, int] = {}
    for key in _SOURCERS:
        cls = AGENTS.get(key)
        if not cls:
            continue
        try:
            r = cls(db).run()
            sourced[key] = int((r.get("saved") or r.get("drafted") or r.get("emailed") or 0)) \
                if isinstance(r, dict) else 0
        except Exception:  # one agent must never stop the sweep
            log.exception("work_pipeline: agent %s failed", key)
            sourced[key] = 0

    content = 0
    try:
        content = int(platform_loops.run_all(db).get("made_total", 0))
    except Exception:
        log.exception("work_pipeline: content loops failed")

    total = sum(v for v in sourced.values() if isinstance(v, int))
    return {"ok": True, "sourced": sourced, "content": content, "total_leads": total,
            "summary": f"Worked the pipeline: ~{total} leads/prospects sourced and "
                       f"{content} content drafts — all queued for your approval."}
