"""Shared lead save → enrich → outreach pipeline used by the specialized
insurance lead agents (commercial, homeowner, referral-partner).

Phase 1 saves every NEW lead fast (no AI/network) and commits, so leads are never
lost if enrichment times out. Phase 2 enriches + sends per-lead, failure-isolated.
"""
from __future__ import annotations

import logging

from .. import memory
from ..ai import client, skills
from ..models import Lead

log = logging.getLogger("bruno.agents.leadgen")


def _as_text(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, dict)):
        import json
        return json.dumps(value, indent=2)
    return str(value)


def _score(p: dict) -> int:
    score = 40
    if p.get("email"):
        score += 20
    if p.get("phone"):
        score += 15
    if p.get("website"):
        score += 15
    if p.get("segment") in ("commercial", "referral_partner"):
        score += 10
    return min(score, 100)


def run_batch(agent, prospects: list[dict], *, account: str, build_prompt,
              default_segment: str, subject_for) -> dict:
    """Save + enrich + dispatch a batch. `build_prompt(p)` returns the OpenAI prompt;
    `subject_for(p, artifacts)` returns the email subject."""
    db = agent.db
    existing = {e for (e,) in db.query(Lead.email).filter(Lead.email.isnot(None)).all()}

    # Focus the agent's effort on the strongest prospects first: highest fit gets
    # enriched + reached out to before the batch's weaker rows, with a learned
    # boost for categories that actually convert (reply data).
    from .. import lead_fit, lead_intel
    boosts = lead_intel.category_boosts(db)
    prospects = sorted(
        prospects, key=lambda p: lead_fit.score(p) + boosts.get(p.get("category"), 0),
        reverse=True)

    pairs: list[tuple[Lead, dict]] = []
    seen: set[str] = set()
    for p in prospects:
        email = (p.get("email") or "").lower()
        if not email or email in existing or email in seen:
            continue
        seen.add(email)
        row = Lead(
            segment=p.get("segment") or default_segment,
            category=p.get("category") or "Business",
            company_name=p.get("company_name") or p.get("owner_name"),
            owner_name=p.get("owner_name"), email=p.get("email"), phone=p.get("phone"),
            website=p.get("website"), linkedin=p.get("linkedin"), industry=p.get("industry"),
            reason=p.get("reason"), score=_score(p), status="New")
        db.add(row)
        pairs.append((row, p))
    db.commit()
    saved = len(pairs)

    enriched = sent = 0
    for row, p in pairs:
        try:
            sysp = skills.system_prompt("cold-email", "marketing-psychology", "offers")
            from .. import lead_intel, outreach_analytics
            for hint in (outreach_analytics.whats_working(db), lead_intel.whats_working(db)):
                if hint:
                    sysp = f"{sysp}\n\n{hint}"
            mem_ctx = memory.context_block(db, p.get("company_name") or "")
            if mem_ctx:
                sysp = f"{sysp}\n\n{mem_ctx}"
            art = client.complete_json(build_prompt(p), system=sysp)
            art = art if isinstance(art, dict) else {}
            body = art.get("cold_email_body")
            row.cold_email = body
            row.call_script = _as_text(art.get("call_script"))
            row.linkedin_msg = art.get("linkedin_msg")
            row.status = "Drafted"
            agent.schedule_follow_ups("lead", row.id)
            msg = agent.dispatch_email(entity_type="lead", entity_id=row.id,
                                       to_email=p.get("email"), subject=subject_for(p, art),
                                       body=body, account=account)
            if msg.status == "Sent":
                row.status = "Sent"
                sent += 1
            enriched += 1
            db.commit()
        except Exception:  # one bad lead must not drop the rest
            log.exception("leadgen enrichment failed for %s", p.get("company_name"))
            db.rollback()
    return {"saved": saved, "enriched": enriched, "emailed": sent}
