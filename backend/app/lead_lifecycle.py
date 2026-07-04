"""Lead lifecycle engine — the pipeline moves itself, nobody moves cards by hand.

Rule-based (runs fully without any AI key). Every pass:

  1. Forward-only status repair — a lead that was genuinely emailed but is still
     sitting at "New"/"Drafted" is advanced to "Contacted". Never regresses a
     status; only reflects a send that already happened.
  2. Stage-transition logging — computes each active insurance lead's canonical
     pipeline stage (insurance_commander.stage_for) and, when it changed since the
     last recorded stage, writes a ``stage_change`` ActionLog. This is what makes
     the AI timeline show "→ Reached", "→ Quote Sent", "→ Policy Bound" on its own.
  3. Speed-breach flags — a first-response time over the target is flagged once
     per lead (``speed_breach``) so slow starts surface instead of hiding.
  4. Return-eligible flags — a contacted lead that never replied and has exhausted
     its whole follow-up sequence is flagged once (``return_eligible``) so
     dead-ends resurface for a fresh angle instead of rotting in the funnel.

Every mutation is forward-only and every flag is written at most once per lead,
so this can run every few hours (or overlap an external trigger) without ever
double-acting or disturbing the send pipeline.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from . import lead_temperature
from .config import settings
from .insurance_commander import INSURANCE_SEGMENTS, _LOST, _WON, stage_for
from .models import ActionLog, FollowUp, Lead, Message

log = logging.getLogger("bruno.lifecycle")

# Statuses that mean "sourced but not yet contacted" — safe to advance forward
# once a real outbound send exists for the lead.
_UNCONTACTED = {"new", "drafted", "queued", ""}
_TERMINAL = _WON | _LOST


def _latest_stage_by_lead(db: Session) -> dict[str, str]:
    """Map lead id (str) -> the most recently recorded pipeline stage."""
    rows = (db.query(ActionLog.entity_id, ActionLog.detail)
            .filter(ActionLog.action == "stage_change", ActionLog.entity == "lead")
            .order_by(ActionLog.created_at.desc()).all())
    latest: dict[str, str] = {}
    for eid, detail in rows:
        if eid and eid not in latest and isinstance(detail, dict) and detail.get("to"):
            latest[eid] = detail["to"]
    return latest


def _flagged_ids(db: Session, action: str) -> set[str]:
    """Lead ids that already carry a one-time flag of this kind."""
    return {eid for (eid,) in db.query(ActionLog.entity_id).filter(
        ActionLog.action == action, ActionLog.entity == "lead").all() if eid}


def _outbound_counts(db: Session) -> tuple[dict[str, int], dict[str, datetime]]:
    """Per-lead outbound message count and first-outbound timestamp."""
    counts: dict[str, int] = {}
    first: dict[str, datetime] = {}
    for eid, n, mn in (db.query(Message.entity_id, func.count(), func.min(Message.created_at))
                       .filter(Message.entity_type == "lead", Message.direction == "outbound")
                       .group_by(Message.entity_id).all()):
        if eid is not None:
            counts[str(eid)] = int(n or 0)
            if mn:
                first[str(eid)] = mn
    return counts, first


def _followup_state(db: Session) -> dict[str, tuple[int, int]]:
    """Per-lead (total follow-ups, open follow-ups)."""
    state: dict[str, tuple[int, int]] = {}
    open_expr = func.sum(case((FollowUp.completed.is_(False), 1), else_=0))
    for eid, total, open_ in (db.query(FollowUp.entity_id, func.count(), open_expr)
            .filter(FollowUp.entity_type == "lead").group_by(FollowUp.entity_id).all()):
        if eid is not None:
            state[str(eid)] = (int(total or 0), int(open_ or 0))
    return state


def run(db: Session, limit: int = 5000) -> dict:
    """Advance stages, log transitions, and flag breaches/returns. Idempotent."""
    now = datetime.now(timezone.utc)
    target = int(settings.lead_response_target_seconds or 60)

    leads = (db.query(Lead).filter(Lead.segment.in_(INSURANCE_SEGMENTS))
             .order_by(Lead.created_at.desc()).limit(limit).all())
    last_stage = _latest_stage_by_lead(db)
    out_counts, first_out = _outbound_counts(db)
    fu_state = _followup_state(db)
    breach_flagged = _flagged_ids(db, "speed_breach")
    return_flagged = _flagged_ids(db, "return_eligible")

    advanced = transitions = breaches = returns = 0

    for lead in leads:
        lid = str(lead.id)
        status_l = (lead.status or "").strip().lower()
        n_out = out_counts.get(lid, 0)

        # 1. Forward-only status repair: emailed but still marked uncontacted.
        if status_l in _UNCONTACTED and n_out > 0:
            lead.status = "Contacted"
            status_l = "contacted"
            advanced += 1

        # 2. Stage-transition logging (skip nothing — we want to see it reach Lost/Bound).
        stage = stage_for(lead.status, lead.times_contacted or 0)
        prev = last_stage.get(lid)
        if stage != prev:
            db.add(ActionLog(
                actor="lifecycle", action="stage_change", entity="lead", entity_id=lid,
                detail={"from": prev, "to": stage, "summary":
                        (f"Stage: {prev} → {stage}" if prev else f"Stage set to {stage}")}))
            transitions += 1

        replied = lead_temperature.classify(lead.status) in (
            lead_temperature.WARM, lead_temperature.HOT)
        terminal = status_l in _TERMINAL

        # 3. Speed breach — first outbound landed later than the target.
        if lid not in breach_flagged and lead.created_at and lid in first_out:
            secs = (first_out[lid] - lead.created_at).total_seconds()
            if secs > target:
                mins = round(secs / 60)
                db.add(ActionLog(
                    actor="lifecycle", action="speed_breach", entity="lead", entity_id=lid,
                    detail={"seconds": round(secs), "target": target,
                            "summary": f"First response took {mins}m — over the {target}s goal"}))
                breach_flagged.add(lid)
                breaches += 1

        # 4. Return-eligible — contacted, never replied, sequence exhausted.
        total_fu, open_fu = fu_state.get(lid, (0, 0))
        if (lid not in return_flagged and not terminal and not replied
                and n_out > 0 and total_fu > 0 and open_fu == 0):
            db.add(ActionLog(
                actor="lifecycle", action="return_eligible", entity="lead", entity_id=lid,
                detail={"summary": "No reply after the full follow-up sequence — "
                        "return this lead with a fresh angle"}))
            return_flagged.add(lid)
            returns += 1

    db.commit()
    result = {"scanned": len(leads), "status_advanced": advanced,
              "stage_transitions": transitions, "speed_breaches": breaches,
              "return_eligible": returns}
    log.info("Lifecycle pass: %s", result)
    return result


def summary(db: Session) -> dict:
    """Lightweight counts for the cockpit — recent transitions + open flags."""
    start = datetime.combine(date.today(), datetime.min.time(), tzinfo=timezone.utc)

    def c(action: str, *filters) -> int:
        return int(db.query(func.count()).select_from(ActionLog)
                   .filter(ActionLog.action == action, ActionLog.entity == "lead",
                           *filters).scalar() or 0)

    return {
        "stage_moves_today": c("stage_change", ActionLog.created_at >= start),
        "speed_breaches": c("speed_breach"),
        "return_eligible": c("return_eligible"),
    }
