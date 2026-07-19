"""Leads routes (insurance + BnB Global consulting)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from .. import outreach
from ..database import get_db
from ..models import Lead
from ..schemas import LeadOut, StatusUpdate
from ..security import require_role

router = APIRouter(prefix="/leads", tags=["insurance"])


class IntakeIn(BaseModel):
    quote_type: str
    answers: dict[str, str] = {}


@router.get("/{lead_id}/intake")
def get_intake(lead_id: str, db: Session = Depends(get_db),
               _=Depends(require_role("admin", "operator", "viewer"))):
    """This lead's quote-intake profile — chosen quote type, its fields, saved
    answers, and how many of the requirements have actually been collected."""
    from .. import lead_profile
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(404, "Lead not found")
    return lead_profile.profile_for(lead)


@router.post("/{lead_id}/intake")
def set_intake(lead_id: str, body: IntakeIn, db: Session = Depends(get_db),
               _=Depends(require_role("admin", "operator"))):
    """Pick this lead's quote type and save what's been collected so far."""
    from .. import lead_profile
    result = lead_profile.save_intake(db, lead_id, body.quote_type, body.answers)
    if result is None:
        if not db.query(Lead).filter(Lead.id == lead_id).first():
            raise HTTPException(404, "Lead not found")
        raise HTTPException(400, "Unknown quote type")
    return result


class EverQuoteImportIn(BaseModel):
    csv_text: str


@router.post("/import-everquote")
def import_everquote(body: EverQuoteImportIn, db: Session = Depends(get_db),
                     _=Depends(require_role("admin", "operator"))):
    """Import an EverQuote CSV export — parses every field (incl. the JSON detail),
    creates personal-auto leads with a pre-filled quote intake, dedupes by email."""
    from .. import everquote
    rows = everquote.parse_csv(body.csv_text or "")
    if not rows:
        raise HTTPException(400, "No rows parsed — is this an EverQuote CSV export?")
    return everquote.import_rows(db, rows)


class BatchPersonalizeIn(BaseModel):
    lead_ids: list[str] | None = None


@router.post("/everquote/personalize-batch")
def everquote_personalize_batch(body: BatchPersonalizeIn, db: Session = Depends(get_db),
                                _=Depends(require_role("admin", "operator"))):
    """Personalize + queue an email draft for every EverQuote lead not yet
    contacted (or a given set) — 500 leads in one click, all queued for review."""
    from .. import everquote
    return everquote.personalize_batch(db, lead_ids=body.lead_ids)


@router.get("/everquote/return-candidates")
def everquote_return_candidates(db: Session = Depends(get_db),
                                _=Depends(require_role("admin", "operator", "viewer"))):
    """EverQuote leads eligible for a VALID return (invalid/disconnected phone,
    invalid email, duplicate, out-of-footprint) with a prepared return reason —
    NOT the internal no-reply revive queue, and NOT 'consumer didn't request'."""
    from .. import everquote_returns
    return everquote_returns.return_candidates(db)


@router.get("/coverage")
def lead_coverage(source: str = "everquote", db: Session = Depends(get_db),
                  _=Depends(require_role("admin", "operator", "viewer"))):
    """Outreach coverage for a lead source (default EverQuote): how many leads have
    actually been emailed / texted / called, how many aren't reachable, and the list
    of leads not yet emailed — so 'did they all get an email?' is a number, not a hunt."""
    from ..models import Message
    q = db.query(Lead)
    if source == "everquote":
        q = q.filter(Lead.intake["source"].astext == "everquote")
    leads = q.all()
    ids = [l.id for l in leads]
    emailed, texted, called = set(), set(), set()
    if ids:
        rows = (db.query(Message.entity_id, Message.channel, Message.status)
                .filter(Message.entity_type == "lead", Message.entity_id.in_(ids),
                        Message.direction == "outbound").all())
        for eid, ch, st in rows:
            if ch == "email" and st == "Sent":
                emailed.add(eid)
            elif ch in ("sms", "whatsapp") and st == "Sent":
                texted.add(eid)
            elif ch == "call":
                called.add(eid)  # a logged call = contacted by phone

    def _reachable(l: Lead) -> bool:
        return outreach.is_real_email(l.email) or bool((l.phone or "").strip())

    def _st(l: Lead):
        return ((l.intake or {}).get("everquote") or {}).get("state")

    unreachable = [l for l in leads if not _reachable(l)]
    # "Not yet emailed" = has a real email but no SENT email on file — the stragglers
    # to finish. Hot (highest score) first so the best ones surface at the top.
    not_emailed = sorted(
        [l for l in leads if outreach.is_real_email(l.email) and l.id not in emailed],
        key=lambda l: l.score or 0, reverse=True)
    return {
        "source": source,
        "total": len(leads),
        "emailed": len(emailed),
        "texted": len(texted),
        "called": len(called),
        "unreachable": len(unreachable),
        "not_emailed_count": len(not_emailed),
        "not_emailed": [{"id": str(l.id), "name": l.owner_name or l.company_name or l.email,
                         "email": l.email, "phone": l.phone, "state": _st(l),
                         "score": l.score or 0} for l in not_emailed[:100]],
    }


@router.get("/{lead_id}/personalized-outreach")
def personalized_outreach(lead_id: str, db: Session = Depends(get_db),
                          _=Depends(require_role("admin", "operator", "viewer"))):
    """Per-lead personalized email + SMS + voicemail + call notes, built from the
    lead's actual EverQuote fields (vehicle, current carrier, discounts)."""
    from .. import everquote
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(404, "Lead not found")
    result = everquote.personalize(lead)
    if not result.get("ok"):
        raise HTTPException(400, result.get("reason", "Cannot personalize this lead"))
    return result


@router.post("/{lead_id}/personalized-outreach/queue")
def queue_personalized_outreach(lead_id: str, db: Session = Depends(get_db),
                                _=Depends(require_role("admin", "operator"))):
    """Save the personalized email as a Drafted message for one-click review/send."""
    from .. import everquote, outreach
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(404, "Lead not found")
    if not lead.email:
        raise HTTPException(400, "This lead has no email on file")
    pack = everquote.personalize(lead)
    if not pack.get("ok"):
        raise HTTPException(400, pack.get("reason", "Cannot personalize this lead"))
    body = pack["email"]["tailored"] or pack["email"]["body"]
    msg = outreach.dispatch_email(db, entity_type="lead", entity_id=lead.id,
                                  to_email=lead.email, subject=pack["email"]["subject"],
                                  body=body, account="insurance", actor="everquote",
                                  force_draft=True)
    return {"ok": True, "message_id": str(msg.id), "status": msg.status,
            "subject": pack["email"]["subject"]}


# ── CRM lead profile: one place to see + work a single lead ────────────────────
def _touch_counts(db: Session, lead_id) -> dict:
    """How many times we OUTBOUND-touched this lead per channel — the CRM counters
    (📧 emails · 💬 texts · 📞 calls). Inbound replies aren't counted as touches."""
    from ..models import Message
    counts = {"email": 0, "sms": 0, "call": 0}
    rows = (db.query(Message.channel, func.count()).filter(
            Message.entity_type == "lead", Message.entity_id == lead_id,
            Message.direction == "outbound").group_by(Message.channel).all())
    for ch, n in rows:
        key = ch if ch in counts else ("email" if ch not in ("sms", "call", "whatsapp") else None)
        if ch == "whatsapp":
            counts["sms"] += n  # WhatsApp counts as a text touch
        elif key:
            counts[key] += n
    return counts


@router.get("/{lead_id}/profile")
def lead_profile_full(lead_id: str, db: Session = Depends(get_db),
                      _=Depends(require_role("admin", "operator", "viewer"))):
    """Full CRM profile for ONE lead: contact + EverQuote detail, per-channel touch
    counters, the AI-drafted email/text/voicemail/call script, and the complete
    activity timeline (every email/text/call in order). The single place to work
    the lead — email, text, and log calls without hunting across pages."""
    from .. import everquote, insurance_commander
    tl = insurance_commander.lead_timeline(db, lead_id)
    if not tl.get("ok"):
        raise HTTPException(404, "Lead not found")
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    pack = everquote.personalize(lead)
    return {
        "lead": tl["lead"],
        "counts": _touch_counts(db, lead.id),
        "timeline": tl["timeline"],
        "everquote": (lead.intake or {}).get("everquote"),
        "outreach": pack if pack.get("ok") else None,
    }


@router.get("/{lead_id}/templates")
def lead_templates(lead_id: str, db: Session = Depends(get_db),
                   _=Depends(require_role("admin", "operator", "viewer"))):
    """The pickable sales templates (email / text / call scripts), each already
    personalized for THIS lead — powers the 'choose a template' dropdown on the
    profile so a touch is one pick + send."""
    from .. import sales_templates
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(404, "Lead not found")
    return sales_templates.for_lead(lead)


@router.get("/{lead_id}/sequence")
def lead_sequence_view(lead_id: str, db: Session = Depends(get_db),
                       _=Depends(require_role("admin", "operator", "viewer"))):
    """This lead's multi-touch cadence — each step's channel (email/sms/call), when
    it's due, and whether it's done. Shows how the lead is being worked over time."""
    from .. import lead_sequence
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(404, "Lead not found")
    return {"lead_id": lead_id, "steps": lead_sequence.steps_for(db, lead.id)}


@router.post("/{lead_id}/sequence/enroll")
def lead_sequence_enroll(lead_id: str, db: Session = Depends(get_db),
                         _=Depends(require_role("admin", "operator"))):
    """Manually enroll one lead into the multi-touch cadence now (idempotent — a
    lead already in a sequence is left as-is)."""
    from .. import lead_sequence
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(404, "Lead not found")
    created = lead_sequence.enroll(db, lead)
    db.commit()
    return {"lead_id": lead_id, "steps_created": created,
            "steps": lead_sequence.steps_for(db, lead.id)}


class LogCallIn(BaseModel):
    outcome: str = "Called"          # Reached · Left voicemail · No answer · Busy
    notes: str | None = None


@router.post("/{lead_id}/log-call")
def log_call(lead_id: str, body: LogCallIn, db: Session = Depends(get_db),
             _=Depends(require_role("admin", "operator"))):
    """Log a call attempt on this lead. Since the app doesn't auto-dial, this is
    how the 📞 counter and timeline stay real — one row per call, with the outcome
    and any notes. Also bumps the contact count/last-touched."""
    from datetime import datetime, timezone

    from ..models import Message
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(404, "Lead not found")
    now = datetime.now(timezone.utc)
    detail = body.outcome + (f" — {body.notes}" if body.notes else "")
    db.add(Message(channel="call", direction="outbound", entity_type="lead",
                   entity_id=lead.id, from_account="insurance", body=detail,
                   status="Logged", sent_at=now))
    lead.times_contacted = (lead.times_contacted or 0) + 1
    lead.last_contacted_at = now
    db.commit()
    return {"ok": True, "counts": _touch_counts(db, lead.id)}


class NoteIn(BaseModel):
    note: str


@router.post("/{lead_id}/note")
def add_lead_note(lead_id: str, body: NoteIn, db: Session = Depends(get_db),
                  _=Depends(require_role("admin", "operator"))):
    """Save a free-text note on this lead — a standalone note (NOT tied to logging a
    call). Shows in the lead's timeline. Doesn't count as an outreach touch."""
    from datetime import datetime, timezone

    from ..models import Message
    text = (body.note or "").strip()
    if not text:
        raise HTTPException(400, "Note is empty")
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(404, "Lead not found")
    db.add(Message(channel="note", direction="internal", entity_type="lead",
                   entity_id=lead.id, from_account="insurance", body=text,
                   status="Logged", sent_at=datetime.now(timezone.utc)))
    db.commit()
    return {"ok": True}


class SendNowIn(BaseModel):
    message: str | None = None       # override the AI-drafted body
    subject: str | None = None       # email only


@router.post("/{lead_id}/send-email")
def send_lead_email(lead_id: str, body: SendNowIn, db: Session = Depends(get_db),
                    _=Depends(require_role("admin", "operator"))):
    """Send this lead an email NOW from their profile. Uses the typed message if
    given, else the AI-personalized EverQuote email (or the lead's stored cold
    email). Delivers via the app's SendGrid-first path."""
    from .. import everquote
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(404, "Lead not found")
    if not lead.email:
        raise HTTPException(400, "This lead has no email on file")
    subject, text = body.subject, body.message
    if not text:
        pack = everquote.personalize(lead)
        if pack.get("ok"):
            subject = subject or pack["email"]["subject"]
            text = pack["email"]["tailored"] or pack["email"]["body"]
        elif lead.cold_email:
            text = lead.cold_email
            subject = subject or f"A quick note for {lead.owner_name or 'you'}"
        else:
            raise HTTPException(400, "No email content — type a message or personalize first")
    msg = outreach.dispatch_email(db, entity_type="lead", entity_id=lead.id,
                                  to_email=lead.email, subject=subject or "", body=text,
                                  account="insurance", actor="crm", autonomous=False)
    return {"ok": True, "sent": msg.status == "Sent", "status": msg.status,
            "counts": _touch_counts(db, lead.id)}


@router.post("/{lead_id}/send-text")
def send_lead_text(lead_id: str, body: SendNowIn, db: Session = Depends(get_db),
                   _=Depends(require_role("admin", "operator"))):
    """Send this lead a text NOW from their profile. Uses the typed message if
    given, else the AI-personalized SMS. Compliance-gated (opt-out/hours/cap)."""
    from .. import everquote, sms_engine
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(404, "Lead not found")
    if not lead.phone:
        raise HTTPException(400, "This lead has no phone on file")
    text = body.message
    if not text:
        pack = everquote.personalize(lead)
        if pack.get("ok"):
            text = pack["sms"]["tailored"] or pack["sms"]["body"]
        else:
            raise HTTPException(400, "No text content — type a message first")
    sid = sms_engine.send_text(db, entity_type="lead", entity_id=lead.id,
                               phone=lead.phone, body=text, account="insurance")
    if not sid:
        reason = sms_engine.sms_block_reason(db, lead.phone) or (
            "No texting channel configured — connect Twilio on Setup")
        raise HTTPException(400, f"Not sent — {reason}")
    return {"ok": True, "sent": True, "counts": _touch_counts(db, lead.id)}


class TwoWayTestIn(BaseModel):
    email: str | None = None
    phone: str | None = None
    name: str | None = None


@router.post("/two-way-test")
def two_way_test(body: TwoWayTestIn, db: Session = Depends(get_db),
                 _=Depends(require_role("admin", "operator"))):
    """Create (or reuse) a CRM profile for yourself and send it a REAL test email +
    text. Reply to both — inbound email sync + the Twilio SMS webhook should save
    your replies onto THIS profile, proving two-way works. Returns each channel's
    result (sent, or the real reason it couldn't) so a failure is self-diagnosing."""
    import re
    from datetime import datetime, timezone

    from .. import sms_engine
    from ..integrations import sms as sms_int
    from ..models import Message
    email = (body.email or "").strip().lower() or None
    phone = (body.phone or "").strip() or None
    if not (email or phone):
        raise HTTPException(400, "Give an email and/or phone to test")

    # Upsert ONE profile so both channels' replies link back to the same lead.
    lead = db.query(Lead).filter(Lead.email == email).first() if email else None
    if not lead and phone:
        key = re.sub(r"\D", "", phone)[-10:]
        lead = next((l for l in db.query(Lead).filter(Lead.phone.isnot(None)).all()
                     if re.sub(r"\D", "", l.phone or "")[-10:] == key), None)
    if not lead:
        lead = Lead(segment="personal", category="Two-Way Test",
                    owner_name=body.name or "Two-Way Test", email=email, phone=phone,
                    status="New", score=90,
                    reason="Self-test profile — verifying two-way email + SMS")
        db.add(lead)
        db.flush()
    else:  # fill in any missing channel so we can test both
        lead.email = lead.email or email
        lead.phone = lead.phone or phone
    db.commit()

    result: dict = {"lead_id": str(lead.id), "email": None, "sms": None}

    if lead.email:
        subject = "Bruno two-way test — please reply to this email"
        emsg = ("This is an automated two-way test from your Bruno insurance app.\n\n"
                "Please REPLY to this email. Once your reply syncs, it should appear on "
                "this test profile in the app — confirming inbound email works.\n\n— Bruno AI")
        try:
            m = outreach.dispatch_email(db, entity_type="lead", entity_id=lead.id,
                                        to_email=lead.email, subject=subject, body=emsg,
                                        account="insurance", actor="two_way_test", autonomous=False)
            result["email"] = ({"sent": True, "status": m.status} if m.status == "Sent"
                               else {"sent": False, "status": m.status,
                                     "reason": "Drafted, not sent — connect a Gmail mailbox or "
                                               "SendGrid, and confirm auto-send is on."})
        except Exception as exc:  # never 500 — report the reason
            result["email"] = {"sent": False, "reason": str(exc)[:200]}

    if lead.phone:
        smsg = ("Bruno two-way test: please reply YES to this text. Your reply should show on "
                "your test profile in the app — confirming inbound texting works.")
        block = sms_engine.sms_block_reason(db, lead.phone, enforce_hours=False)
        if block:
            result["sms"] = {"sent": False, "reason": block}
        else:
            # Use send_with_error so a real provider failure (e.g. Twilio 20003
            # 'authenticate') surfaces here instead of being silently logged as sent.
            sid, err = sms_int.send_with_error(lead.phone, smsg, account="insurance")
            db.add(Message(channel="sms", direction="outbound", entity_type="lead",
                           entity_id=lead.id, to_email=lead.phone, from_account="insurance",
                           body=smsg, status="Sent" if sid else "Failed", provider_id=sid,
                           sent_at=datetime.now(timezone.utc) if sid else None))
            db.commit()
            result["sms"] = {"sent": True} if sid else {
                "sent": False, "reason": err or "No texting channel configured — connect a provider on Setup."}

    return {"ok": True, **result,
            "message": "Test profile ready. Reply to the email and the text — your replies "
                       "should land on this profile. Inbound texts also need the Twilio "
                       "number's webhook set to <app>/sms/inbound; inbound email needs Gmail "
                       "connected via OAuth."}


@router.get("/{lead_id}/call-coach")
def call_coach(lead_id: str, db: Session = Depends(get_db),
               _=Depends(require_role("admin", "operator", "viewer"))):
    """The pre-call brief for this lead — line, coverage, score, stage, the call's
    goal, what to ask for next, an opener, and the objections most likely for
    their profile with rebuttals. Rule-based; AI sharpens the opener if connected."""
    from .. import call_coach as cc
    result = cc.brief(db, lead_id)
    if not result.get("ok"):
        raise HTTPException(404, "Lead not found")
    return result


@router.get("/{lead_id}/quote")
def build_quote(lead_id: str, db: Session = Depends(get_db),
                _=Depends(require_role("admin", "operator", "viewer"))):
    """Auto-build this lead's quote packet — line, recommended coverages, a
    fitting carrier shortlist, a ballpark premium estimate, and what's still
    missing before a real quote can be run. Rule-based, no AI key needed."""
    from .. import quote_builder
    result = quote_builder.build(db, lead_id)
    if not result.get("ok"):
        raise HTTPException(404, "Lead not found")
    return result


@router.post("/{lead_id}/quote/sent")
def mark_quote_sent(lead_id: str, db: Session = Depends(get_db),
                    _=Depends(require_role("admin", "operator"))):
    """Mark this lead's quote as sent — advances it to the Quote Sent stage and
    logs it to the lead's AI timeline."""
    from .. import quote_builder
    result = quote_builder.mark_sent(db, lead_id)
    if not result.get("ok"):
        raise HTTPException(404, "Lead not found")
    return result


class IntakeSendIn(BaseModel):
    quote_type: str
    channel: str  # "sms" | "whatsapp"
    lang: str = "en"


@router.post("/{lead_id}/quote-intake/send")
def send_quote_intake(lead_id: str, body: IntakeSendIn, db: Session = Depends(get_db),
                      _=Depends(require_role("admin", "operator"))):
    """Text or WhatsApp this lead the short version of the quote-intake ask
    (the same info the email template collects, phrased for a text thread)."""
    from datetime import datetime, timezone

    from .. import quote_intake, sms_engine
    from ..integrations import sms
    from ..models import Message
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(404, "Lead not found")
    if not lead.phone:
        raise HTTPException(400, "This lead has no phone number on file")
    template = quote_intake.get(body.quote_type)
    if not template:
        raise HTTPException(400, "Unknown quote type")
    text = template.get(f"text_body_{body.lang}") or template.get("text_body_en")
    if not text:
        raise HTTPException(400, "No text template for this quote type")

    if body.channel == "sms":
        # A human operator chose to send this quote-intake ask right now, so it's
        # exempt from the AUTOMATED texting-window/cap (same as the /sms/send
        # thread reply). Opt-out (STOP) is still always enforced inside send_text.
        result = sms_engine.send_text(db, entity_type="lead", entity_id=lead.id,
                                      phone=lead.phone, body=text, account="insurance",
                                      enforce_hours=False)
        if not result:
            raise HTTPException(400, "No texting channel configured — connect Twilio or the "
                                "iMessage bridge on Setup first")
    elif body.channel == "whatsapp":
        if not sms.whatsapp_configured():
            raise HTTPException(400, "WhatsApp isn't connected — add Meta Cloud API or Twilio "
                                "WhatsApp credentials on Setup first")
        sid = sms.send_whatsapp(lead.phone, text)
        if not sid:
            raise HTTPException(400, "WhatsApp send failed")
        db.add(Message(channel="whatsapp", direction="outbound", entity_type="lead",
                       entity_id=lead.id, to_email=lead.phone, from_account="insurance",
                       body=text, status="Sent", provider_id=sid,
                       sent_at=datetime.now(timezone.utc)))
        lead.times_contacted = (lead.times_contacted or 0) + 1
        lead.last_contacted_at = datetime.now(timezone.utc)
        db.commit()
    else:
        raise HTTPException(400, "channel must be 'sms' or 'whatsapp'")
    return {"ok": True, "channel": body.channel, "text": text}


@router.get("", response_model=list[LeadOut])
def list_leads(segment: str | None = None, status: str | None = None,
               temperature: str | None = None, line: str | None = None,
               state: str | None = None, sort: str | None = None, limit: int = 200,
               db: Session = Depends(get_db), _=Depends(require_role("admin", "operator", "viewer"))):
    from .. import lead_temperature
    from ..insurance_lines import COMMERCIAL, HOME, LIFE, line_for
    q = db.query(Lead)
    if segment:
        q = q.filter(Lead.segment == segment)
    if status:
        q = q.filter(Lead.status == status)
    if state:
        # EverQuote leads carry their state in the intake detail (leads have no
        # state column). Match on that so "MA/NH/FL" actually narrows the list.
        st = state.strip().upper()
        q = q.filter(Lead.intake["everquote"]["state"].astext == st)
    # Temperature maps to a fixed, known set of statuses — push it into SQL so
    # it never gets starved by an unrelated row LIMIT (whichever bucket
    # dominates the sort order would otherwise silently crowd out the rest).
    if temperature:
        temp = (temperature or "").strip().lower()
        wanted = lead_temperature.statuses_for(temperature)
        hot_by_score = Lead.score >= lead_temperature.HOT_SCORE  # in-market inbound → hot
        if temp == lead_temperature.HOT:
            # Hot = hot statuses OR a high score (freshly-imported EverQuote leads),
            # but never something already gone dead.
            q = q.filter(or_(func.lower(Lead.status).in_(wanted), hot_by_score),
                         ~func.lower(Lead.status).in_(lead_temperature.statuses_for(lead_temperature.DEAD)))
        elif wanted is not None:
            q = q.filter(func.lower(Lead.status).in_(wanted))
        else:  # cold = NOT hot/warm/dead by status AND not hot-by-score
            q = q.filter(or_(Lead.status.is_(None),
                             ~func.lower(Lead.status).in_(lead_temperature.all_classified_statuses())),
                         ~hot_by_score)
    # Commercial-line leads only ever come from segment="commercial", and
    # home/life leads only ever come from everything else — narrow by segment
    # first so the (much larger) commercial volume can't bloat the scan below.
    # Auto is the one line that spans both (a personal driver OR a vehicle-
    # centric commercial prospect like an auto shop/trucker), so it can't take
    # that shortcut.
    ln = (line or "").lower()
    if ln == COMMERCIAL:
        q = q.filter(Lead.segment == "commercial")
    elif ln in (HOME, LIFE):
        q = q.filter(Lead.segment != "commercial")
    # Sort order the user picked. "fit" re-ranks in Python below; the rest are SQL.
    _name = func.lower(func.coalesce(Lead.owner_name, Lead.company_name, Lead.email))
    _orders = {
        "recent": (Lead.created_at.desc(),),                     # newest leads first
        "oldest": (Lead.created_at.asc(),),                      # oldest first
        "name": (_name.asc(),),                                  # A→Z
        "stale": (Lead.last_contacted_at.asc().nullsfirst(),),   # least-recently-contacted first
        # hottest first (default) — unscored leads sort LAST, not first (Postgres
        # floats NULLs to the top of a DESC order otherwise, burying real hot leads).
        "score": (Lead.score.desc().nullslast(), Lead.created_at.desc()),
    }
    q = q.order_by(*_orders.get((sort or "").lower(), _orders["score"]))
    if line:
        # `line` needs category/industry keyword matching, which isn't a real
        # column — so it can't be a SQL WHERE clause. Applying it AFTER a row
        # LIMIT would silently starve it once other rows fill the page first
        # (exactly what happened once the table passed a few thousand leads),
        # so fetch every candidate row (already narrowed by segment above) and
        # only limit AFTER the line filter has actually run.
        rows = [l for l in q.all() if line_for(l.category, l.segment, l.industry) == ln]
    else:
        rows = q.limit(limit).all()
    if sort == "fit":  # surface the strongest prospects first
        from ..lead_fit import score as _fit
        rows = sorted(rows, key=_fit, reverse=True)
    return rows[:limit]


@router.get("/search")
def lead_finder(segment: str | None = None, temperature: str | None = None,
                industry: str | None = None, city: str | None = None,
                has_email: bool | None = None, min_score: int = 0, q: str | None = None,
                limit: int = 100, db: Session = Depends(get_db),
                _=Depends(require_role("admin", "operator", "viewer"))):
    """Lead Finder: filter leads and return each with an explainable 0-100 score.
    Filters: segment, temperature, industry, city, has_email, min_score, free-text q."""
    from .. import lead_temperature
    from ..lead_scoring import score_lead
    query = db.query(Lead)
    if segment:
        query = query.filter(Lead.segment == segment)
    if industry:
        query = query.filter(Lead.industry.ilike(f"%{industry}%"))
    if city:
        query = query.filter(Lead.city.ilike(f"%{city}%")) if hasattr(Lead, "city") else query
    if has_email is True:
        query = query.filter(Lead.email.isnot(None))
    if q:
        like = f"%{q}%"
        query = query.filter(
            (Lead.company_name.ilike(like)) | (Lead.owner_name.ilike(like))
            | (Lead.email.ilike(like)) | (Lead.industry.ilike(like)))
    # Temperature maps to a fixed, known status set — push it into SQL (same
    # fix as /leads) so it can't be starved by the row LIMIT below once one
    # temperature bucket dominates the sort order.
    if temperature:
        wanted = lead_temperature.statuses_for(temperature)
        if wanted is not None:
            query = query.filter(func.lower(Lead.status).in_(wanted))
        else:
            query = query.filter(or_(Lead.status.is_(None),
                                     ~func.lower(Lead.status).in_(lead_temperature.all_classified_statuses())))
    rows = query.order_by(Lead.score.desc(), Lead.created_at.desc()).limit(max(limit, 400)).all()
    out = []
    for lead in rows:
        sc = score_lead(lead)
        if sc["score"] < min_score:
            continue
        out.append({
            "id": str(lead.id), "company": lead.company_name, "name": lead.owner_name,
            "email": lead.email, "phone": lead.phone, "industry": lead.industry,
            "segment": lead.segment, "status": lead.status,
            "score": sc["score"], "band": sc["band"], "reasons": sc["reasons"],
        })
    out.sort(key=lambda r: r["score"], reverse=True)
    return out[:limit]


@router.get("/summary")
def leads_summary(segment: str | None = None, db: Session = Depends(get_db),
                  _=Depends(require_role("admin", "operator", "viewer"))):
    """Cold / warm / hot counts + Home / Auto / Life / Commercial line counts
    (per segment if given) — the funnel and the book of business at a glance."""
    from ..insurance_lines import LINES, line_for
    from ..lead_temperature import classify
    q = db.query(Lead.status, Lead.category, Lead.segment, Lead.industry)
    if segment:
        q = q.filter(Lead.segment == segment)
    buckets = {"cold": 0, "warm": 0, "hot": 0, "dead": 0}
    lines = {ln: 0 for ln in LINES}
    for status, category, seg, industry in q.all():
        buckets[classify(status)] = buckets.get(classify(status), 0) + 1
        lines[line_for(category, seg, industry)] += 1
    return {**buckets, "lines": lines}


@router.get("/pipeline-health")
def pipeline_health(db: Session = Depends(get_db),
                    _=Depends(require_role("admin", "operator", "viewer"))):
    """Why warm/hot leads aren't flowing yet, and the exact next action to fix it."""
    from .. import lead_pipeline
    return lead_pipeline.health(db)


@router.post("/{lead_id}/send")
def send_outreach(lead_id: str, db: Session = Depends(get_db),
                  _=Depends(require_role("admin", "operator"))):
    """Reach out to a lead now — sends its cold email (insurance via Thrust,
    consulting/other via personal mailbox)."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    if not lead.email:
        return {"ok": False, "reason": "no email on file"}
    account = "insurance" if lead.segment == "commercial" or lead.segment == "personal" else "personal"
    subject = f"A quick idea for {lead.company_name or lead.owner_name}"
    msg = outreach.dispatch_email(db, entity_type="lead", entity_id=lead.id, to_email=lead.email,
                                  subject=subject, body=lead.cold_email, account=account,
                                  actor="manual", autonomous=False)
    if msg.status == "Sent" and lead.status in (None, "New", "Drafted"):
        lead.status = "Sent"
    db.commit()
    return {"ok": True, "status": msg.status, "to": lead.email}


@router.post("/dispatch")
def dispatch_pending(segment: str | None = None, db: Session = Depends(get_db),
                     _=Depends(require_role("admin", "operator"))):
    """Send the cold email to every pending lead at once (status New/Drafted with an
    email). Optional ?segment= for insurance (commercial/personal) or consulting."""
    from .. import bulk_outreach
    return {"ok": True, **bulk_outreach.dispatch_leads(db, segment=segment, autonomous=False)}


@router.post("/dedupe")
def dedupe(db: Session = Depends(get_db), _=Depends(require_role("admin", "operator"))):
    """Remove duplicate leads (same email), keeping the most-worked one — cleanup for a
    list that got imported more than once. Import now de-dupes automatically; this
    fixes copies made before that."""
    from .. import importer
    return importer.dedupe_leads(db)


@router.post("/sms-followup-run")
def sms_followup_run(db: Session = Depends(get_db),
                     _=Depends(require_role("admin", "operator"))):
    """Text every lead that was emailed but hasn't replied (hottest first, within the
    daily SMS cap and TCPA hours). Manual trigger — runs even if the auto follow-up
    is toggled off. Needs a texting provider + A2P; skips are reported."""
    from .. import runtime_config, sms_followups
    runtime_config.apply_to_settings(db)
    return {"ok": True, **sms_followups.run(db)}


class TestSendIn(BaseModel):
    to: str
    lead_id: str | None = None


@router.post("/test-send")
def test_send(body: TestSendIn, db: Session = Depends(get_db),
              _=Depends(require_role("admin", "operator"))):
    """Preview the real outreach: write the AI email for your hottest pending lead
    (or a specific one) and send that exact copy to YOUR inbox — so you can eyeball
    what the AI produces before firing a whole batch. Goes to the address you give,
    NOT the lead; doesn't touch the lead's contact history or the daily cap."""
    from .. import importer, lead_temperature
    from ..integrations import gmail
    to = (body.to or "").strip()
    if not outreach.is_real_email(to):
        raise HTTPException(400, "Enter a real email address to send the test to.")
    if body.lead_id:
        lead = db.query(Lead).filter(Lead.id == body.lead_id).first()
    else:
        lead = (db.query(Lead).filter(Lead.status.in_((None, "New", "Drafted")),
                                      Lead.email.isnot(None))
                .order_by(*lead_temperature.dispatch_order(Lead)).first())
    if not lead:
        raise HTTPException(400, "No pending lead to preview — import some leads first.")
    subject = importer.draft_lead_email(db, lead)  # writes the AI copy onto the lead
    db.commit()
    if not (lead.cold_email or "").strip():
        raise HTTPException(400, "Couldn't write the email — is the AI (OpenAI) connected on Setup?")
    account = gmail.account_for_segment(lead.segment)
    mid, err = outreach.deliver(to, f"[TEST] {subject}", lead.cold_email, account=account)
    if not mid:
        raise HTTPException(400, f"Couldn't send the test — {err}")
    return {"ok": True, "to": to, "subject": subject,
            "lead": lead.company_name or lead.owner_name or lead.email}


@router.post("/sync-replies")
def sync_replies(db: Session = Depends(get_db),
                 _=Depends(require_role("admin", "operator"))):
    """Pull recent inbound email replies now — anyone who replied becomes a warm/hot
    lead. This is what the scheduler does automatically; this button runs it on
    demand so leads don't stay cold while the scheduler is off."""
    from .. import inbound
    return {"ok": True, **inbound.sync_replies(db)}


@router.post("/{lead_id}/status")
def set_status(lead_id: str, body: StatusUpdate, db: Session = Depends(get_db),
               _=Depends(require_role("admin", "operator"))):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    lead.status = body.status
    db.commit()
    return {"lead_id": lead_id, "status": body.status}
