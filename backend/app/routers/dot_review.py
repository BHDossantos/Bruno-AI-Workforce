"""Authenticated DOT review workspace. No provider calls or outreach enqueueing."""
from dataclasses import asdict
from datetime import datetime, timezone
from itertools import combinations
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, File, Form, UploadFile
from pydantic import AwareDatetime, EmailStr, BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import DotReviewCase, Lead, Message, DoNotContact
from ..security import require_role
from .. import compliance
from ..dot_review import (Snapshot, normalize_usdot, build_call_hooks, compare_observations,
                          registry_research_status, safer_research_status)

router = APIRouter(prefix="/dot-review", tags=["DOT research review"])
_operator = require_role("admin", "operator")
TEMPLATE = ("Hi! This is Lucas with Trust Insurance. We’re here to help you find insurance "
            "for your trucking business. Which language do you prefer: English, português ou español?")


class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_kind: Literal["vendor", "ma_registry", "safer"]
    source_name: str = Field(min_length=1, max_length=200)
    source_ref: str = Field(min_length=1, max_length=1000)
    source_record_id: str = Field(min_length=1, max_length=200)
    fetched_at: AwareDatetime
    posted_at: AwareDatetime | None = None
    fields: dict[str, str] = Field(max_length=30)

    @field_validator("fields")
    @classmethod
    def bounded_fields(cls, fields):
        allowed = {"usdot", "legal_name", "dba", "physical_address", "ma_entity_id",
                   "lookup_status", "cargo", "operation_scope", "service_type", "email", "phone"}
        if set(fields) - allowed or any(len(v) > 2000 for v in fields.values()):
            raise ValueError("unsupported or oversized evidence field")
        return fields

    @model_validator(mode="after")
    def valid_snapshot(self):
        self.snapshot()
        return self

    def snapshot(self):
        return Snapshot(self.source_kind, self.source_name, self.source_ref,
                        self.source_record_id, self.fetched_at, tuple(self.fields.items()))


class Intake(BaseModel):
    model_config = ConfigDict(extra="forbid")
    observations: list[Observation] = Field(min_length=1, max_length=100)
    posted_from: AwareDatetime
    posted_through: AwareDatetime


class ReviewEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str = Field(min_length=1, max_length=100)
    kind: Literal["contact_reported", "opt_out", "language_preference", "next_action", "outcome"]
    occurred_at: AwareDatetime
    evidence_ref: str = Field(min_length=1, max_length=1000)
    note: str = Field(min_length=1, max_length=2000)
    language: Literal["en", "es", "pt"] | None = None
    due_at: AwareDatetime | None = None
    outcome: Literal["answered", "voicemail_left", "voicemail_unavailable", "no_answer", "busy", "wrong_number"] | None = None


def _dot(raw):
    try:
        dot = normalize_usdot(raw)
        if len(dot) > 20:
            raise ValueError("USDOT exceeds storage limit")
        return dot
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


def _case(db, usdot, lock=False):
    query = select(DotReviewCase).where(DotReviewCase.usdot == _dot(usdot))
    row = db.scalar(query.with_for_update() if lock else query)
    if row is None:
        raise HTTPException(404, "Research case not found")
    return row


def _suppress_contacts(db, observations):
    for observation in observations:
        fields = observation["fields"]
        for kind, normalizer in (("email", compliance._email_key), ("phone", compliance._phone_key)):
            value = normalizer(fields.get(kind))
            if value and not db.scalar(select(DoNotContact).where(
                DoNotContact.kind == kind, DoNotContact.value == value)):
                db.add(DoNotContact(kind=kind, value=value, reason="DOT review opt-out", source="dot_review"))
                db.flush()


def _append_observation(db, usdot, observation):
    # Unique identity + row lock prevents concurrent imports overwriting evidence.
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    elif dialect == "sqlite":  # isolated tests only
        from sqlalchemy.dialects.sqlite import insert
    else:
        raise HTTPException(503, "Unsupported research storage")
    db.execute(insert(DotReviewCase).values(usdot=usdot, payload={"observations": [], "events": []})
               .on_conflict_do_nothing(index_elements=["usdot"]))
    row = _case(db, usdot, lock=True)
    data = dict(row.payload)
    observations = list(data["observations"])
    candidate = observation.model_dump(mode="json")
    if candidate not in observations:
        if len(observations) >= 500:
            raise HTTPException(409, "Evidence capacity reached; archive review required")
        observations.append(candidate)
        if data.get("prepared_draft"):
            data["prepared_draft"] = {**data["prepared_draft"], "status": "evidence_changed_requires_review"}
    if any(e["kind"] == "opt_out" for e in data["events"]):
        _suppress_contacts(db, observations)
    row.payload = {**data, "observations": observations}
    db.flush()
    return row


@router.post("/intake")
def intake(body: Intake, db: Session = Depends(get_db), user=Depends(_operator)):
    if body.posted_from > body.posted_through:
        raise HTTPException(422, "Invalid date-posted interval")
    accepted = []
    for obs in body.observations:
        if obs.source_kind != "vendor" or obs.posted_at is None:
            raise HTTPException(422, "Intake requires vendor observations with actual date posted")
        if obs.posted_at > obs.fetched_at:
            raise HTTPException(422, "Date posted cannot follow observation time")
        if body.posted_from <= obs.posted_at <= body.posted_through:
            accepted.append((_dot(obs.fields.get("usdot", "")), obs))
    # Lock in stable order to avoid cross-batch deadlocks.
    for dot, obs in sorted(accepted, key=lambda item: item[0]):
        _append_observation(db, dot, obs)
    db.commit()
    return {"usdots": sorted({dot for dot, _ in accepted}), "observations_in_range": len(accepted),
            "outreach_enqueued": 0}


@router.post("/import-csv")
async def import_csv(file: UploadFile = File(...), source_ref: str = Form(...),
                     posted_from: AwareDatetime = Form(...), posted_through: AwareDatetime = Form(...),
                     db: Session = Depends(get_db), user=Depends(_operator)):
    """Explicit normalized export contract, not an assumed vendor API/schema."""
    import csv
    import io
    from pydantic import ValidationError
    raw = await file.read(1_000_001)
    if len(raw) > 1_000_000:
        raise HTTPException(413, "CSV exceeds 1 MB")
    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
        required = {"usdot", "source_record_id", "posted_at"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("CSV needs usdot, source_record_id and timezone-aware posted_at columns")
        observations = []
        for row in reader:
            if len(observations) >= 100:
                raise ValueError("Import at most 100 observations per batch")
            fields = {k: v for k, v in row.items() if k not in required - {"usdot"} and v}
            observations.append(Observation(source_kind="vendor", source_name="DOT Leads New Ventures",
                source_ref=source_ref, source_record_id=row["source_record_id"],
                fetched_at=datetime.now(timezone.utc), posted_at=row["posted_at"], fields=fields))
        body = Intake(observations=observations, posted_from=posted_from, posted_through=posted_through)
    except (ValueError, UnicodeError, ValidationError, TypeError) as exc:
        # Do not echo contact data from validation errors.
        raise HTTPException(422, "Invalid CSV; check normalized headers, timestamps and batch size") from exc
    return intake(body, db, user)


@router.post("/{usdot}/evidence")
def evidence(usdot: str, body: Observation, db: Session = Depends(get_db), user=Depends(_operator)):
    dot = _dot(usdot)
    _case(db, dot)
    # Identity mismatches remain review evidence; never silently re-key the case.
    _append_observation(db, dot, body)
    db.commit()
    return {"recorded": True, "outreach_enqueued": 0}


@router.post("/{usdot}/events")
def event(usdot: str, body: ReviewEvent, db: Session = Depends(get_db), user=Depends(_operator)):
    if body.kind == "language_preference" and body.language is None:
        raise HTTPException(422, "Record the actual expressed language choice")
    if body.kind == "next_action" and body.due_at is None:
        raise HTTPException(422, "Next action requires a due date")
    if body.kind == "outcome" and body.outcome is None:
        raise HTTPException(422, "Outcome required")
    row = _case(db, usdot, lock=True)
    data = dict(row.payload)
    events = list(data["events"])
    candidate = {**body.model_dump(mode="json"), "owner_id": str(user.id)}
    prior = next((e for e in events if e["event_id"] == body.event_id), None)
    if prior and prior != candidate:
        raise HTTPException(409, "Conflicting event retry")
    if not prior:
        if len(events) >= 500:
            raise HTTPException(409, "Event capacity reached; archive review required")
        events.append(candidate)
    row.payload = {**data, "events": events}
    if body.kind == "opt_out":
        _suppress_contacts(db, data["observations"])
    if data.get("prepared_draft"):
        row.payload = {**row.payload, "prepared_draft": {**data["prepared_draft"], "status": "event_changed_requires_review"}}
    db.commit()
    return {"recorded": True, "status": "operator_reported", "outreach_enqueued": 0}


@router.get("")
def cases(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
          db: Session = Depends(get_db), user=Depends(_operator)):
    rows = db.execute(select(DotReviewCase.usdot, DotReviewCase.updated_at,
        DotReviewCase.payload["observations"][0]["fields"]["legal_name"].as_string().label("legal_name"))
        .order_by(DotReviewCase.updated_at.desc(), DotReviewCase.usdot).offset(offset).limit(limit))
    return [{"usdot": r.usdot, "updated_at": r.updated_at, "legal_name": r.legal_name} for r in rows]



@router.get("/{usdot}")
def detail(usdot: str, db: Session = Depends(get_db), user=Depends(_operator)):
    row = _case(db, usdot)
    observations = [Observation.model_validate(o) for o in row.payload["observations"]]
    snapshots = tuple(o.snapshot() for o in observations)
    emails = {o.fields["email"].strip().lower() for o in observations if o.fields.get("email")}
    phones = {o.fields["phone"].strip() for o in observations if o.fields.get("phone")}
    # Exact email and normalized phone matches are warnings, not company merges.
    conditions = [Lead.intake["usdot"].as_string() == row.usdot,
                  Lead.intake["answers"]["usdot"].as_string() == row.usdot]
    if emails:
        conditions.append(func.lower(func.trim(Lead.email)).in_(emails))
    phone_keys = {compliance._phone_key(p) for p in phones if compliance._phone_key(p)}
    if phone_keys:
        # PostgreSQL regexp_replace matches formatting variants; SQLite tests use email matching.
        if db.get_bind().dialect.name == "postgresql":
            conditions.append(func.right(func.regexp_replace(Lead.phone, "[^0-9]", "", "g"), 10).in_(phone_keys))
        else:
            conditions.append(Lead.phone.in_(phones))
    leads = db.scalars(select(Lead).where(or_(*conditions)).limit(101)).all() if conditions else []
    message_conditions = []
    if emails:
        message_conditions.append(func.lower(func.trim(Message.to_email)).in_(emails))
    if leads:
        message_conditions.append((Message.entity_type == "lead") & Message.entity_id.in_([lead.id for lead in leads]))
    messages = db.scalars(select(Message).where(or_(*message_conditions)).order_by(
        Message.created_at.desc()).limit(101)).all() if message_conditions else []
    from ..sms_engine import is_opted_out
    suppressed = any(is_opted_out(db, p) for p in phones) or any(compliance.is_dnc(db, email=e) for e in emails) or any(
        compliance.is_dnc(db, phone=p) for p in phones)
    blocked = suppressed or any(e["kind"] == "opt_out" for e in row.payload["events"])
    events = row.payload["events"]
    latest = tuple(max((s for s in snapshots if s.source_kind == kind), key=lambda s: s.fetched_at)
                   for kind in ("vendor", "ma_registry", "safer") if any(s.source_kind == kind for s in snapshots))
    hooks = [asdict(h) for h in build_call_hooks(latest)]
    return {"usdot": row.usdot, **row.payload, "registry_status": registry_research_status(snapshots),
            "safer_status": safer_research_status(snapshots), "hooks": hooks,
            "differences": [asdict(d) for a, b in combinations(latest, 2)
                            if a.source_kind != b.source_kind for d in compare_observations(a, b)],
            "crm_matches": [{"id": str(l.id), "status": l.status, "times_contacted": l.times_contacted,
                             "last_contacted_at": l.last_contacted_at} for l in leads],
            "message_history": [{"id": str(m.id), "channel": m.channel, "direction": m.direction,
                                 "status": m.status, "provider_id": m.provider_id, "sent_at": m.sent_at}
                                for m in messages],
            "history_truncated": len(leads) > 100 or len(messages) > 100,
            "suppressed": blocked, "prior_contact_review": bool(messages or events or any(
                l.times_contacted or l.last_contacted_at for l in leads)),
            "sending_enabled": False,
            "draft": {"status": "local_review_only", "template_version": "lucas_unknown_language_intro:1",
                      "body": None if blocked else TEMPLATE, "provider": "gmail_only_requested",
                      "bcc": [], "bcc_status": "verified Bruno/Lucas addresses required; optional",
                      "dispatch_gates": ["human review", "authorized Gmail identity", "cross-channel dedup",
                                         "consent/suppression", "contact window", "daily limits"]}}


class DraftPreparation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    to: EmailStr
    bcc: list[EmailStr] = Field(default_factory=list, max_length=2)
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=10000)
    evidence_digests: list[str] = Field(min_length=1, max_length=10)

    @field_validator("subject")
    @classmethod
    def no_header_newline(cls, value):
        if "\n" in value or "\r" in value:
            raise ValueError("Subject must be one line")
        return value


@router.post("/{usdot}/draft")
def prepare_draft(usdot: str, body: DraftPreparation, db: Session = Depends(get_db), user=Depends(_operator)):
    row = _case(db, usdot, lock=True)
    review = detail(usdot, db, user)
    if review["suppressed"] or review["prior_contact_review"] or review["history_truncated"]:
        raise HTTPException(409, "Suppression or contact history requires review; no new draft prepared")
    observations = [Observation.model_validate(o) for o in row.payload["observations"]]
    recipients = {o.fields.get("email", "").strip().lower() for o in observations}
    digests = {o.snapshot().digest for o in observations}
    if str(body.to).lower() not in recipients or not set(body.evidence_digests) <= digests:
        raise HTTPException(422, "Recipient and source references must match recorded evidence")
    draft = {**body.model_dump(mode="json"), "status": "local_review_only", "provider": "gmail",
             "account": "personal", "prepared_by": str(user.id),
             "prepared_at": datetime.now(timezone.utc).isoformat(),
             "bcc_requires_identity_verification": bool(body.bcc), "sent_at": None, "provider_id": None}
    row.payload = {**row.payload, "prepared_draft": draft}
    db.commit()
    return draft
