"""Execution control — the Emergency Stop kill-switch API."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import control
from ..database import get_db
from ..security import require_role

router = APIRouter(prefix="/control", tags=["control"])
_read = require_role("admin", "operator", "viewer")
_write = require_role("admin", "operator")


@router.get("/status")
def status(db: Session = Depends(get_db), _=Depends(_read)):
    return {"paused": control.is_paused_safe(db), "mode": control.get_mode(db),
            "outreach_autopilot": control.outreach_autopilot(db),
            "insurance_relay": control.insurance_relay_via_personal(db),
            "auto_apply_mode": control.auto_apply_mode(db)}


class AutoApplyIn(BaseModel):
    mode: str  # off | compliant | aggressive


@router.post("/auto-apply")
def set_auto_apply(body: AutoApplyIn, db: Session = Depends(get_db), _=Depends(_write)):
    """Set the auto-apply mode: 'off' (prepare only), 'compliant' (auto-submit on
    company ATS pages), or 'aggressive' (also LinkedIn/Indeed Easy Apply via your
    stored session — violates their ToS, account risk)."""
    return {"auto_apply_mode": control.set_auto_apply_mode(db, body.mode)}


class OutreachIn(BaseModel):
    on: bool


@router.post("/outreach-autopilot")
def set_outreach_autopilot(body: OutreachIn, db: Session = Depends(get_db), _=Depends(_write)):
    """Toggle Outreach Autopilot: when ON, cold sales outreach + follow-ups
    auto-send (even in semi mode); content still drafts for approval."""
    return {"outreach_autopilot": control.set_outreach_autopilot(db, body.on)}


@router.get("/businesses")
def get_businesses(db: Session = Depends(get_db), _=Depends(_read)):
    """Which businesses (insurance / B&B / SavoryMind / Music / job-apply / content)
    are switched on — each runs its own agents + scheduled jobs when on."""
    from .. import businesses, runtime_config
    runtime_config.apply_to_settings(db)
    return {"businesses": businesses.status()}


class BusinessIn(BaseModel):
    key: str
    on: bool


@router.post("/businesses")
def set_business(body: BusinessIn, db: Session = Depends(get_db), _=Depends(_write)):
    """Turn one business on or off. Takes effect on the next scheduled run — no
    redeploy. Pass key='all' to flip every business at once."""
    from .. import businesses, runtime_config
    keys = businesses.ALL if body.key == "all" else [body.key]
    if body.key != "all" and body.key not in businesses.ALL:
        from fastapi import HTTPException
        raise HTTPException(400, f"Unknown business '{body.key}'.")
    for k in keys:
        runtime_config.save(db, f"biz_{k}_enabled", "true" if body.on else "false")
    runtime_config.apply_to_settings(db)
    return {"businesses": businesses.status()}


@router.post("/insurance-relay")
def set_insurance_relay(body: OutreachIn, db: Session = Depends(get_db), _=Depends(_write)):
    """Toggle: send insurance outreach through your personal mailbox with the
    Thrust address as Reply-To — so it sends without separate Thrust credentials."""
    return {"insurance_relay": control.set_insurance_relay_via_personal(db, body.on)}


class ModeIn(BaseModel):
    mode: str  # manual | semi | auto


@router.post("/mode")
def set_mode(body: ModeIn, db: Session = Depends(get_db), _=Depends(_write)):
    """Set automation mode: 'semi' (agents draft, you approve to send — default),
    'auto' (full autopilot), or 'manual' (draft only)."""
    return {"mode": control.set_mode(db, body.mode)}


@router.post("/pause")
def pause(db: Session = Depends(get_db), _=Depends(_write)):
    """Emergency stop: immediately halt all autonomous posting, sending and agent runs."""
    return {"paused": control.set_paused(db, True)}


@router.post("/resume")
def resume(db: Session = Depends(get_db), _=Depends(_write)):
    """Release the emergency stop — agents resume on their normal schedule."""
    return {"paused": control.set_paused(db, False)}


def _autopilot_readiness(db: Session) -> dict:
    """Is the daily machine actually set up to EMAIL, TEXT and CALL on its own?
    For each channel: whether automation is switched on, whether a channel is
    connected to send through, and — if not — exactly what's blocking. So 'set up
    my daily outreach' becomes a green/blocked checklist, not a guess."""
    from .. import outreach, runtime_config, sms_followups
    from ..config import settings
    from ..integrations import sms as sms_integ
    from ..integrations import telco
    from ..integrations import voice as vdispatch
    runtime_config.apply_to_settings(db)

    paused = control.is_paused_safe(db)
    autosend_on = control.get_mode(db) == "auto" or control.outreach_autopilot(db)
    acct = "insurance"

    # EMAIL — auto-sends drafts hourly 8am-8pm when autopilot is on and a channel
    # (Resend / Gmail) is connected.
    email_conn = outreach.can_deliver(acct)
    email_block = ([] if not paused else ["autopilot is paused (hit Resume)"])
    if not autosend_on:
        email_block.append("Outreach Autopilot is off")
    if not email_conn:
        email_block.append("connect an email channel (Resend / Gmail) in Setup")

    # SMS — the warm/opt-in texting drafts auto-send in the same pass; the cold
    # emailed-but-silent follow-up is a separate opt-in (needs A2P).
    sms_conn = sms_integ.is_configured()
    sms_block = list(email_block[:1])  # shares the pause gate
    if not autosend_on:
        sms_block.append("Outreach Autopilot is off")
    if not sms_conn:
        sms_block.append(f"connect a texting carrier ({telco.label('sms')}) in Setup")

    # CALL — the auto-dialer works the Call List every minute 8am-8pm when enabled
    # and a voice carrier + callback are set.
    dial_on = bool(settings.auto_dial_enabled)
    call_conn = vdispatch.is_configured()
    call_diag = telco.diagnose("voice")
    call_block = list(email_block[:1])
    if not dial_on:
        call_block.append("auto-dialer is off (auto_dial_enabled)")
    if not call_conn:
        call_block.extend(call_diag.get("missing") or ["connect a voice carrier in Setup"])
    if call_conn and not (settings.producer_callback or "").strip():
        call_block.append("your cell / callback number (Setup → Calling)")

    def _row(enabled, connected, blockers, schedule):
        return {"enabled": bool(enabled), "connected": bool(connected),
                "ready": bool(enabled) and bool(connected) and not blockers,
                "blockers": blockers, "schedule": schedule}

    return {
        "paused": paused,
        "mode": control.get_mode(db),
        "outreach_autopilot": control.outreach_autopilot(db),
        "email": _row(autosend_on and not paused, email_conn, email_block,
                      "hourly 8am–8pm"),
        "sms": _row(autosend_on and not paused, sms_conn, sms_block,
                    "with outreach + 1:45pm follow-ups"),
        "call": _row(dial_on and not paused, call_conn, call_block,
                     "every minute 8am–8pm"),
        "sms_followup_optin": sms_followups.is_enabled(),
    }


@router.get("/autopilot")
def autopilot_status(db: Session = Depends(get_db), _=Depends(_read)):
    """Daily-automation readiness across all three channels (email / SMS / call)."""
    return _autopilot_readiness(db)


@router.post("/autopilot/on")
def autopilot_on(db: Session = Depends(get_db), _=Depends(_write)):
    """One click to arm the daily machine: release any pause and turn Outreach
    Autopilot on (the two runtime gates on auto-sending). The auto-dialer is on by
    default already. Reports back the readiness so any still-missing connection
    (email channel, texting carrier, voice creds) is named — flipping the switches
    can't invent credentials that aren't connected."""
    control.set_paused(db, False)
    control.set_outreach_autopilot(db, True)
    return _autopilot_readiness(db)
