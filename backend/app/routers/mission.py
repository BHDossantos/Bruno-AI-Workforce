"""Mission Control — the single morning command screen.

Aggregates today's real activity, the goal-vs-actual scoreboard, pending
approvals and the emergency-stop state into one payload so the home screen can
answer "what's happening and what needs me right now?".
"""
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import control
from ..database import get_db
from ..security import require_role as _rr
from ..models import (Application, ContentItem, Job, Lead, Message, Restaurant)
from ..security import require_role

router = APIRouter(prefix="/mission", tags=["mission"])
_read = require_role("admin", "operator", "viewer")

# Daily targets per area (sensible defaults; the goal score is target vs today).
_TARGETS = {
    "Social posts": 9, "Insurance leads": 50, "BnB Global leads": 50,
    "SavoryMind leads": 50, "Outreach sent": 50, "Replies": 10, "Job applications": 10,
}


def _today_start() -> datetime:
    return datetime.combine(date.today(), datetime.min.time(), tzinfo=timezone.utc)


@router.get("/control")
def mission_control(db: Session = Depends(get_db), _=Depends(_read)):
    start = _today_start()

    def c(model, *filters) -> int:
        return int(db.query(func.count()).select_from(model).filter(*filters).scalar() or 0)

    posts = c(ContentItem, ContentItem.created_at >= start,
              ContentItem.status.in_(["scheduled", "needs_approval", "ready", "generated", "published"]))
    ins_leads = c(Lead, Lead.created_at >= start, Lead.segment.in_(["commercial", "personal"]))
    bnb_leads = c(Lead, Lead.created_at >= start, Lead.segment == "consulting")
    restaurants = c(Restaurant, Restaurant.kind == "prospect", Restaurant.created_at >= start)
    # Count what ACTUALLY went out today (sent_at set), not drafts created today —
    # otherwise this disagrees with the recap and overstates outreach.
    sent = c(Message, Message.direction == "outbound", Message.sent_at >= start)
    replies = c(Message, Message.direction == "inbound", Message.created_at >= start)
    apps = c(Application, Application.created_at >= start)
    jobs_found = c(Job, Job.found_at >= start)

    today = {
        "posts": posts, "insurance_leads": ins_leads, "bnb_leads": bnb_leads,
        "savorymind_leads": restaurants, "outreach_sent": sent, "replies": replies,
        "applications": apps, "jobs_found": jobs_found,
    }
    actuals = {
        "Social posts": posts, "Insurance leads": ins_leads, "BnB Global leads": bnb_leads,
        "SavoryMind leads": restaurants, "Outreach sent": sent, "Replies": replies,
        "Job applications": apps,
    }
    goals = [{
        "area": area, "target": target, "today": actuals.get(area, 0),
        "status": "on track" if actuals.get(area, 0) >= target else "behind",
    } for area, target in _TARGETS.items()]

    # Pending approvals (mirror /approvals/count). With Outreach Autopilot ON, cold
    # lead/restaurant emails auto-send and are NOT counted as needing you — only
    # content + replies do. The auto-send backlog is reported separately.
    auto = control.outreach_autopilot(db)
    draft_leads = c(Lead, Lead.status == "Drafted", Lead.email.isnot(None))
    draft_rests = c(Restaurant, Restaurant.kind == "prospect", Restaurant.status == "Drafted",
                    Restaurant.email.isnot(None))
    pending = (c(ContentItem, ContentItem.status == "needs_approval")
               + c(Message, Message.entity_type == "reply", Message.direction == "outbound",
                   Message.status == "Drafted", Message.to_email.isnot(None)))
    if not auto:
        pending += draft_leads + draft_rests

    # Honest sending status: a big backlog of drafted outreach with ~nothing
    # actually sent means sending is BLOCKED (mailbox can't send, or the engine
    # isn't running) — don't reassure the user that it's "sending automatically".
    from ..integrations import gmail
    backlog = draft_leads + draft_rests
    mailbox_connected = gmail.is_configured(gmail.PERSONAL) or gmail.is_configured(gmail.INSURANCE)
    sending_stalled = bool(auto and backlog >= 25 and sent == 0)
    if not mailbox_connected:
        sending_reason = ("No mailbox is connected to SEND — connect your Gmail on the "
                          "Connect page (and hit Test sending), or nothing goes out.")
    elif sending_stalled:
        sending_reason = ("Outreach is queued but not going out — your mailbox may not be "
                          "authorized to send. Open Connect → Test sending to confirm.")
    else:
        sending_reason = None

    return {
        "paused": control.is_paused_safe(db),
        "today": today,
        "goals": goals,
        "approvals_pending": pending,
        # Only call it "sending" when sends are actually happening today; otherwise
        # report the backlog as stalled so the UI can warn instead of reassure.
        "auto_sending": backlog if (auto and not sending_stalled) else 0,
        "outreach_backlog": backlog,
        "sent_today": sent,
        "mailbox_connected": mailbox_connected,
        "sending_stalled": sending_stalled,
        "sending_reason": sending_reason,
    }


@router.get("/digest/preview")
def digest_preview(db: Session = Depends(get_db), _=Depends(_read)):
    """Preview the daily outreach digest content (what gets emailed)."""
    from .. import outreach_digest
    return outreach_digest.build(db)


@router.post("/digest/send")
def digest_send(db: Session = Depends(get_db),
                _=Depends(require_role("admin", "operator"))):
    """Email the daily outreach digest to the operator now."""
    from .. import outreach_digest
    return outreach_digest.send(db)


@router.get("/money-actions")
def money_actions(db: Session = Depends(get_db), _=Depends(_read)):
    """Today's highest-value actions to hit the client goal — hot leads to close,
    backlog to send, follow-ups + booking nudges due — each with a one-click CTA."""
    from .. import money_actions as ma
    return ma.actions(db)


@router.get("/insurance-commander")
def insurance_commander(db: Session = Depends(get_db), _=Depends(_read)):
    """The Insurance Sales OS cockpit — today's tiles, the SPEED scoreboard
    (first-response time vs the 60s target), and the pipeline funnel."""
    from .. import insurance_commander as ic
    return ic.overview(db)


@router.get("/lead-timeline/{lead_id}")
def lead_timeline(lead_id: str, db: Session = Depends(get_db), _=Depends(_read)):
    """One lead's full AI timeline — everything the workforce did, in order,
    plus its live score, stage and temperature."""
    from .. import insurance_commander as ic
    return ic.lead_timeline(db, lead_id)


@router.get("/objections")
def objection_catalog(_=Depends(_read)):
    """The objection-handling playbook — every common objection with its proven
    rebuttal and next move."""
    from .. import objection_ai
    return objection_ai.catalog()


class ObjectionIn(BaseModel):
    text: str
    lead_id: str | None = None


@router.post("/objection")
def objection_help(body: ObjectionIn, db: Session = Depends(get_db),
                   _=Depends(_rr("admin", "operator"))):
    """Read a prospect's objection and return the best rebuttal + next move
    (AI-tailored when the key is connected). Logs to the lead's timeline if given."""
    from .. import objection_ai
    return objection_ai.handle(db, body.text, body.lead_id)


@router.get("/return-queue")
def return_queue(db: Session = Depends(get_db), _=Depends(_read)):
    """Leads the lifecycle engine flagged return-eligible — contacted, never
    replied, sequence exhausted — each with a fresh re-engagement angle."""
    from .. import lead_return
    return lead_return.queue(db)


@router.post("/return/{lead_id}")
def return_lead(lead_id: str, db: Session = Depends(get_db),
                _=Depends(_rr("admin", "operator"))):
    """Return one dead-end lead to the active pipeline with a fresh follow-up
    cadence, logged to its AI timeline."""
    from .. import lead_return
    result = lead_return.mark_returned(db, lead_id)
    if not result.get("ok"):
        from fastapi import HTTPException
        raise HTTPException(404, "Lead not found")
    return result


@router.post("/lifecycle/run")
def lifecycle_run(db: Session = Depends(get_db), _=Depends(_rr("admin", "operator"))):
    """Advance every lead one pass — repair contacted status, log stage moves,
    flag speed breaches and return-eligible dead-ends. Rule-based, no AI needed."""
    from .. import lead_lifecycle
    return lead_lifecycle.run(db)


@router.post("/work-pipeline")
def work_pipeline(db: Session = Depends(get_db), _=Depends(_rr("admin", "operator"))):
    """Source + draft across every revenue line and queue it all for approval."""
    from .. import pipeline_run
    return pipeline_run.work_pipeline(db)


@router.get("/brands")
def brands(db: Session = Depends(get_db), _=Depends(_read)):
    """Per-brand scoreboard — each brand's own numbers for Mission Control."""
    from ..lead_temperature import classify
    from ..models import Grant, Influencer, MusicPlaylist

    def lead_temps(*segments):
        rows = db.query(Lead.status).filter(Lead.segment.in_(segments)).all()
        cold = warm = hot = 0
        for (s,) in rows:
            t = classify(s)
            if t == "hot":
                hot += 1
            elif t == "warm":
                warm += 1
            elif t == "cold":
                cold += 1
        return {"total": len(rows), "cold": cold, "warm": warm, "hot": hot}

    out = []

    ins = lead_temps("commercial", "personal")
    out.append({"key": "insurance", "name": "Thrust Insurance", "icon": "🛡️",
                "metric": "leads", "value": ins["total"], "warm": ins["warm"], "hot": ins["hot"],
                "link": "/insurance"})

    bnb = lead_temps("consulting")
    out.append({"key": "bnbglobal", "name": "BnB Global", "icon": "💻",
                "metric": "leads", "value": bnb["total"], "warm": bnb["warm"], "hot": bnb["hot"],
                "link": "/bnbglobal"})

    rest_rows = db.query(Restaurant.status).filter(Restaurant.kind == "prospect").all()
    rw = sum(1 for (s,) in rest_rows if classify(s) == "warm")
    rh = sum(1 for (s,) in rest_rows if classify(s) == "hot")
    out.append({"key": "savorymind", "name": "SavoryMind", "icon": "🍽️",
                "metric": "restaurants", "value": len(rest_rows), "warm": rw, "hot": rh,
                "link": "/savorymind"})

    playlists = db.query(func.count()).select_from(MusicPlaylist).scalar() or 0
    influencers = db.query(func.count()).select_from(Influencer).scalar() or 0
    out.append({"key": "music", "name": "Bruno D — Music", "icon": "🎵",
                "metric": "pitches", "value": int(playlists + influencers),
                "warm": 0, "hot": 0, "link": "/music"})

    grant_pipeline = float(db.query(func.coalesce(func.sum(Grant.amount), 0))
                           .filter(Grant.status.notin_(["Lost", "Skipped"])).scalar() or 0)
    partners = lead_temps("foundation")
    out.append({"key": "foundation", "name": "Foundation", "icon": "🎓",
                "metric": "grant $ + partners", "value": int(grant_pipeline),
                "warm": partners["total"], "hot": partners["hot"], "link": "/foundation"})

    from datetime import date, datetime, timezone
    start = datetime.combine(date.today(), datetime.min.time(), tzinfo=timezone.utc)
    personal = db.query(func.count()).select_from(ContentItem).filter(
        ContentItem.business == "personal").scalar() or 0
    personal_today = db.query(func.count()).select_from(ContentItem).filter(
        ContentItem.business == "personal", ContentItem.created_at >= start).scalar() or 0
    out.append({"key": "personal", "name": "Bruno D — Personal", "icon": "👤",
                "metric": "content", "value": int(personal), "warm": int(personal_today), "hot": 0,
                "link": "/calendar"})

    return out
