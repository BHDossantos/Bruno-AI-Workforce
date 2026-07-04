"""Insurance Commander — the sales operating system view.

Turns the raw pipeline into an EverQuote-style ops cockpit: the day's tiles
(new leads, need-immediate-response, engaged/waiting-on-quote, follow-ups due,
policies bound, commission), a SPEED scoreboard (first-response time vs the
60-second target — the one thing that wins), a pipeline stage funnel, and a
per-lead AI timeline of everything the workforce did, in order.

Pure aggregation over data the system already captures (leads, messages,
follow-ups, clients, action logs) — no new tables.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from . import lead_temperature
from .config import settings
from .models import Client, FollowUp, Lead, Message

# Insurance is commercial + personal + the referral partners who feed personal lines.
INSURANCE_SEGMENTS = ("commercial", "personal", "referral_partner")

_WON = {"closed won", "won", "bound", "policy bound", "client", "customer", "signed"}
_LOST = {"closed lost", "lost", "dead", "do_not_contact", "unsubscribed", "bounced"}

# EverQuote-style stages, in order. Every lead maps to exactly one.
PIPELINE = ["New", "Attempting Contact", "Reached", "Quote Sent",
            "Needs Follow-up", "Negotiation", "Policy Bound", "Lost"]


def _today_start() -> datetime:
    return datetime.combine(date.today(), datetime.min.time(), tzinfo=timezone.utc)


def stage_for(status: str | None, times_contacted: int) -> str:
    """Map a lead's raw status + contact count to a canonical pipeline stage."""
    s = (status or "").strip().lower()
    if s in _WON:
        return "Policy Bound"
    if s in _LOST:
        return "Lost"
    if s in ("quoted", "quote sent", "proposal", "proposal sent"):
        return "Quote Sent"
    if s in ("negotiation", "negotiating"):
        return "Negotiation"
    if s in ("interested", "meeting", "meeting booked", "demo", "booked"):
        return "Needs Follow-up"
    if lead_temperature.classify(status) in (lead_temperature.WARM, lead_temperature.HOT):
        return "Reached"
    if (times_contacted or 0) > 0 or s in ("sent", "drafted", "contacted"):
        return "Attempting Contact"
    return "New"


def _first_response_seconds(db: Session, since: datetime, limit: int = 500) -> list[float]:
    """Seconds between a lead being received and its FIRST outbound touch — the
    speed metric EverQuote drills. Only leads that actually got a first touch."""
    leads = (db.query(Lead.id, Lead.created_at)
             .filter(Lead.segment.in_(INSURANCE_SEGMENTS), Lead.created_at >= since)
             .limit(limit).all())
    out: list[float] = []
    for lead_id, created in leads:
        if not created:
            continue
        first = (db.query(func.min(Message.created_at))
                 .filter(Message.entity_type == "lead", Message.entity_id == lead_id,
                         Message.direction == "outbound").scalar())
        if first and first >= created:
            out.append((first - created).total_seconds())
    return out


def speed(db: Session, days: int = 7) -> dict:
    """First-response speed scoreboard vs the target (red when over)."""
    from datetime import timedelta
    since = datetime.now(timezone.utc) - timedelta(days=days)
    secs = _first_response_seconds(db, since)
    target = int(settings.lead_response_target_seconds or 60)
    if not secs:
        return {"measured": 0, "avg_seconds": None, "best_seconds": None,
                "worst_seconds": None, "target_seconds": target, "over_target": False}
    avg = sum(secs) / len(secs)
    return {"measured": len(secs), "avg_seconds": round(avg),
            "best_seconds": round(min(secs)), "worst_seconds": round(max(secs)),
            "target_seconds": target, "over_target": avg > target}


def overview(db: Session) -> dict:
    """The Insurance Commander homepage: today's tiles, speed, and the funnel."""
    start = _today_start()
    rate = float(settings.insurance_commission_rate or 0.12)

    def c(*filters) -> int:
        return int(db.query(func.count()).select_from(Lead)
                   .filter(Lead.segment.in_(INSURANCE_SEGMENTS), *filters).scalar() or 0)

    todays_leads = c(Lead.created_at >= start)
    # Need immediate response: received but not yet touched, and not already closed.
    need_response = c(Lead.times_contacted == 0,
                      func.lower(Lead.status).notin_(_WON | _LOST))
    # Engaged / waiting on quote: warm or hot, not yet bound.
    warm = lead_temperature.statuses_for("warm") or set()
    hot = lead_temperature.statuses_for("hot") or set()
    engaged = c(func.lower(Lead.status).in_(warm | hot))

    # Follow-ups due today, scoped to insurance leads (join via entity id).
    today = date.today()
    due_ids = {str(i) for (i,) in db.query(Lead.id).filter(
        Lead.segment.in_(INSURANCE_SEGMENTS)).all()}
    followups_due = 0
    for fu_entity, fu_id in db.query(FollowUp.entity_type, FollowUp.entity_id).filter(
            FollowUp.entity_type == "lead", FollowUp.completed.is_(False),
            FollowUp.due_date <= today).all():
        if str(fu_id) in due_ids:
            followups_due += 1

    # Policies bound today + the commission they represent.
    bound = (db.query(Client).filter(Client.business == "insurance",
             Client.status != "Cancelled", Client.signed_at == today).all())
    policies_bound = len(bound)
    commission_today = round(sum(float(cl.premium_monthly or 0) * 12 * rate for cl in bound), 2)

    # Pipeline funnel (all open + recent insurance leads).
    funnel = {stage: 0 for stage in PIPELINE}
    for status, tc in db.query(Lead.status, Lead.times_contacted).filter(
            Lead.segment.in_(INSURANCE_SEGMENTS)).all():
        funnel[stage_for(status, tc or 0)] += 1

    return {
        "tiles": {
            "todays_leads": todays_leads,
            "need_immediate_response": need_response,
            "engaged_waiting_on_quote": engaged,
            "need_follow_up_today": followups_due,
            "policies_bound_today": policies_bound,
            "commission_today": commission_today,
        },
        "speed": speed(db),
        "pipeline": [{"stage": s, "count": funnel[s]} for s in PIPELINE],
        "commission_rate": rate,
        "lifecycle": _lifecycle_summary(db),
    }


def _lifecycle_summary(db: Session) -> dict:
    """Lifecycle-engine counts for the cockpit; empty-safe if it can't run."""
    try:
        from . import lead_lifecycle
        return lead_lifecycle.summary(db)
    except Exception:  # never let the cockpit fail on the add-on metric
        return {"stage_moves_today": 0, "speed_breaches": 0, "return_eligible": 0}


def lead_timeline(db: Session, lead_id: str) -> dict:
    """Every action the workforce took on ONE lead, in order — the 'AI timeline'.
    Built from the lead itself, its messages (calls/SMS/email in + out),
    scheduled follow-ups, and agent action logs. Includes the AI score + stage."""
    from . import lead_scoring
    from .models import ActionLog

    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        return {"ok": False, "reason": "lead not found"}

    events: list[dict] = []
    if lead.created_at:
        events.append({"at": lead.created_at.isoformat(), "kind": "received",
                       "label": "Lead received", "detail": lead.category or lead.segment})
    _CH = {"sms": "SMS", "whatsapp": "WhatsApp", "email": "Email", "call": "Call"}
    for m in (db.query(Message).filter(Message.entity_type == "lead",
              Message.entity_id == lead.id).order_by(Message.created_at.asc()).all()):
        when = m.sent_at or m.created_at
        ch = _CH.get(m.channel or "email", (m.channel or "email").title())
        direction = "sent" if m.direction == "outbound" else "received"
        events.append({"at": when.isoformat() if when else None,
                       "kind": f"{m.direction}_{m.channel or 'email'}",
                       "label": f"{ch} {direction}",
                       "detail": (m.subject or (m.body or ""))[:120], "status": m.status})
    for fu in (db.query(FollowUp).filter(FollowUp.entity_type == "lead",
               FollowUp.entity_id == lead.id).order_by(FollowUp.step.asc()).all()):
        events.append({"at": fu.due_date.isoformat() if fu.due_date else None,
                       "kind": "followup",
                       "label": f"Follow-up step {fu.step}"
                       + (" ✓" if fu.completed else " (scheduled)"),
                       "detail": fu.body or ""})
    _ACTION_LABELS = {"stage_change": "📈 Stage moved", "speed_breach": "🐌 Slow first response",
                      "return_eligible": "♻️ Ready to re-engage", "quote_built": "🧮 Quote sent"}
    for a in (db.query(ActionLog).filter(ActionLog.entity.in_(["lead", "leads"]),
              ActionLog.entity_id == str(lead.id)).order_by(ActionLog.created_at.asc()).all()):
        label = _ACTION_LABELS.get(a.action, f"AI: {a.action}")
        events.append({"at": a.created_at.isoformat() if a.created_at else None,
                       "kind": a.action if a.action in _ACTION_LABELS else "ai_action",
                       "label": label,
                       "detail": (a.detail or {}).get("summary") if isinstance(a.detail, dict) else None})
    events.sort(key=lambda e: e["at"] or "")

    sc = lead_scoring.score_lead(lead)
    return {
        "ok": True,
        "lead": {
            "id": str(lead.id), "name": lead.company_name or lead.owner_name or lead.email,
            "email": lead.email, "phone": lead.phone, "source": lead.category or lead.segment,
            "status": lead.status, "stage": stage_for(lead.status, lead.times_contacted or 0),
            "temperature": lead_temperature.classify(lead.status),
            "score": sc.get("score"), "band": sc.get("band"),
            "times_contacted": lead.times_contacted or 0,
            "received_at": lead.created_at.isoformat() if lead.created_at else None,
        },
        "timeline": events,
    }
