"""AI Manager — turns the pipeline into plain-English coaching, not just numbers.

Instead of "you made N calls", it says "you lost ~$X because N leads got a first
touch after the 60-second goal" or "12 quotes are sent but not bound — those are
your closest dollars." Rule-based over data the sales OS already tracks (speed
breaches, stages, follow-ups, EverQuote return credits, per-state conversion) —
no AI key needed. Every insight only appears when the data actually supports it.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from . import lead_temperature
from .config import settings
from .insurance_commander import INSURANCE_SEGMENTS, _LOST, _WON, stage_for
from .models import ActionLog, Client, FollowUp, Lead

log = logging.getLogger("bruno.aimanager")

# Assumptions behind the dollar estimates (kept transparent in the detail text).
_ASSUMED_ANNUAL_PREMIUM = 1500.0   # typical personal-auto annual premium
_SLOW_CONVERSION_PENALTY = 0.10    # ~1 in 10 slow-contacted leads would've closed if fast


def _commission_per_policy() -> float:
    return round(_ASSUMED_ANNUAL_PREMIUM * float(settings.insurance_commission_rate or 0.12))


def _c(db: Session, *filters) -> int:
    return int(db.query(func.count()).select_from(Lead)
               .filter(Lead.segment.in_(INSURANCE_SEGMENTS), *filters).scalar() or 0)


def _speed_loss(db: Session) -> dict | None:
    breaches = int(db.query(func.count()).select_from(ActionLog).filter(
        ActionLog.action == "speed_breach", ActionLog.entity == "lead").scalar() or 0)
    if not breaches:
        return None
    lost = round(breaches * _SLOW_CONVERSION_PENALTY * _commission_per_policy())
    return {"key": "speed_loss", "severity": "high",
            "headline": f"You likely lost ~${lost:,} because {breaches} lead(s) got a first "
                        f"touch after the {settings.lead_response_target_seconds}s goal.",
            "detail": f"Estimate: {breaches} slow leads × ~{int(_SLOW_CONVERSION_PENALTY*100)}% "
                      f"that would have closed if contacted fast × ~${_commission_per_policy()} "
                      "commission/policy. Speed is the #1 controllable factor — work the "
                      "'Need Immediate Response' tile first.",
            "value": lost, "count": breaches}


def _uncontacted(db: Session) -> dict | None:
    n = _c(db, Lead.times_contacted == 0, func.lower(Lead.status).notin_(_WON | _LOST))
    if not n:
        return None
    return {"key": "uncontacted", "severity": "high" if n >= 5 else "medium",
            "headline": f"{n} lead(s) are sitting untouched right now.",
            "detail": "Every minute past 60 seconds cuts your odds — these are the fastest wins "
                      "on the board. Call or queue outreach for them today.",
            "count": n}


def _overdue_followups(db: Session) -> dict | None:
    today = date.today()
    ins_ids = {str(i) for (i,) in db.query(Lead.id).filter(
        Lead.segment.in_(INSURANCE_SEGMENTS)).all()}
    overdue = sum(1 for (etype, fid) in db.query(FollowUp.entity_type, FollowUp.entity_id).filter(
        FollowUp.entity_type == "lead", FollowUp.completed.is_(False),
        FollowUp.due_date < today).all() if str(fid) in ins_ids)
    if not overdue:
        return None
    return {"key": "overdue_followups", "severity": "medium",
            "headline": f"{overdue} follow-up(s) are past due.",
            "detail": "Most deals are won on the 2nd–6th touch, not the 1st. Clearing the overdue "
                      "follow-ups is the cheapest pipeline you have.",
            "count": overdue}


def _quotes_open(db: Session) -> dict | None:
    rows = db.query(Lead.status, Lead.times_contacted).filter(
        Lead.segment.in_(INSURANCE_SEGMENTS)).all()
    n = sum(1 for s, tc in rows if stage_for(s, tc or 0) == "Quote Sent")
    if not n:
        return None
    est = n * _commission_per_policy()
    return {"key": "quotes_open", "severity": "high" if n >= 3 else "medium",
            "headline": f"{n} quote(s) are sent but not bound — ~${est:,} in commission on the table.",
            "detail": "These are your closest dollars. Follow up on each, handle the objection "
                      "(Objection AI), and ask for the bind.",
            "value": est, "count": n}


def _returns_reclaim(db: Session) -> dict | None:
    from . import everquote_returns
    cands = everquote_returns.return_candidates(db, limit=10_000)
    if not cands:
        return None
    return {"key": "returns_reclaim", "severity": "info",
            "headline": f"{len(cands)} lead(s) are eligible for a valid EverQuote return.",
            "detail": "Invalid phone/email, duplicate, or out-of-footprint — reclaim the credit "
                      "instead of eating the cost. See the EverQuote Return Assistant.",
            "count": len(cands)}


def _state_conversion(db: Session) -> dict | None:
    """Compare bind rate by state where there's enough volume to be meaningful."""
    # Denominator: EverQuote leads per state. Numerator: bound insurance clients per state.
    by_state: dict[str, int] = {}
    for (intake,) in db.query(Lead.intake).filter(Lead.segment.in_(INSURANCE_SEGMENTS)).all():
        st = ((intake or {}).get("everquote") or {}).get("state") if isinstance(intake, dict) else None
        if st:
            by_state[st] = by_state.get(st, 0) + 1
    if len(by_state) < 2:
        return None
    bound: dict[str, int] = {}
    for (st,) in db.query(Client.state).filter(Client.business == "insurance",
                                               Client.status != "Cancelled").all():
        if st:
            bound[st.upper()] = bound.get(st.upper(), 0) + 1
    rates = {st: (bound.get(st, 0) / n) for st, n in by_state.items() if n >= 5}
    if len(rates) < 2:
        return None
    best = max(rates, key=rates.get)
    worst = min(rates, key=rates.get)
    if best == worst or rates[best] <= rates[worst]:
        return None
    lift = round((rates[best] - rates[worst]) * 100)
    if lift < 5:
        return None
    return {"key": "state_conversion", "severity": "info",
            "headline": f"{best} leads convert ~{lift}% higher than {worst} — consider shifting spend.",
            "detail": f"{best}: {round(rates[best]*100)}% bind rate vs {worst}: "
                      f"{round(rates[worst]*100)}% on comparable volume. Lean your lead budget "
                      "toward the state that's actually closing.",
            "count": by_state.get(best, 0)}


def insights(db: Session) -> dict:
    """The AI Manager's read on the business right now — ordered, most urgent first."""
    builders = [_speed_loss, _uncontacted, _quotes_open, _overdue_followups,
                _state_conversion, _returns_reclaim]
    out = []
    for b in builders:
        try:
            r = b(db)
        except Exception:  # one insight failing must not blank the whole panel
            log.debug("AI Manager insight %s failed", getattr(b, "__name__", "?"), exc_info=True)
            r = None
        if r:
            out.append(r)
    order = {"high": 0, "medium": 1, "info": 2}
    out.sort(key=lambda i: order.get(i["severity"], 3))
    if not out:
        out.append({"key": "all_clear", "severity": "info",
                    "headline": "Nothing on fire — the pipeline is being worked.",
                    "detail": "No slow-response, untouched, or overdue backlog right now. Keep "
                              "the speed under 60 seconds and the follow-ups on cadence.",
                    "count": 0})
    return {"insights": out, "generated_at": datetime.now(timezone.utc).isoformat()}
