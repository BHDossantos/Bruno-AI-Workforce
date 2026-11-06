"""Research-only DOT intake primitives. No database, scheduler or sender integration.

Keep these records outside the existing Lead importer: that importer schedules
outreach. Source access and review permissions must be established by the future
adapter before supplying snapshots here. Differences are questions, not findings
of misrepresentation, underwriting decisions or corrections to official records.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
from typing import Literal, Mapping

SourceKind = Literal["vendor", "ma_registry", "safer"]
STAGES = ("new", "verified", "contacted", "qualified", "documents_pending",
          "quote_presented", "policy_issued")


def _aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must include a timezone")


def normalize_usdot(value: str) -> str:
    value = value.strip()
    if not value or not value.isascii() or not value.isdecimal() or int(value) <= 0:
        raise ValueError("USDOT must be a positive ASCII digit identifier")
    return str(int(value))


@dataclass(frozen=True)
class Snapshot:
    source_kind: SourceKind
    source_name: str
    source_ref: str  # URL or authorized export/batch reference, never credentials
    source_record_id: str
    fetched_at: datetime
    fields: tuple[tuple[str, str], ...]
    applicant_at: datetime | None = None  # vendor event date; never inferred from import

    def __post_init__(self) -> None:
        if self.source_kind not in ("vendor", "ma_registry", "safer"):
            raise ValueError("unsupported source kind")
        if not all(v.strip() for v in (self.source_name, self.source_ref, self.source_record_id)):
            raise ValueError("source identity and reference are required")
        _aware(self.fetched_at)
        if self.applicant_at:
            _aware(self.applicant_at)
        if len(dict(self.fields)) != len(self.fields):
            raise ValueError("duplicate field names")
        if any(not isinstance(k, str) or not isinstance(v, str) for k, v in self.fields):
            raise ValueError("snapshot fields must be text pairs")
        object.__setattr__(self, "fields", tuple(sorted(self.fields)))

    @property
    def digest(self) -> str:
        payload = [self.source_kind, self.source_name, self.source_ref,
                   self.source_record_id, self.fetched_at.isoformat(), sorted(self.fields),
                   self.applicant_at.isoformat() if self.applicant_at else None]
        return sha256(json.dumps(payload, ensure_ascii=False).encode()).hexdigest()


@dataclass(frozen=True)
class ResearchCase:
    key: str
    usdot: str | None
    observations: tuple[Snapshot, ...]
    review_required: bool = True
    outreach_enabled: bool = False


def prepare_vendor_batch(
    snapshots: list[Snapshot], existing: Mapping[str, ResearchCase] | None = None,
) -> dict[str, ResearchCase]:
    """Deduplicate company identities; retain differing source observations.

    Missing USDOT stays in quarantine by vendor record identity. Do not collapse
    different companies merely because they share a phone, agent or email.
    Returned mapping is a copy; callers must persist atomically in a future layer.
    """
    cases = dict(existing or {})
    for observation in snapshots:
        if observation.source_kind != "vendor":
            raise ValueError("registry snapshots cannot substitute for the vendor feed")
        raw_dot = dict(observation.fields).get("usdot", "").strip()
        usdot = normalize_usdot(raw_dot) if raw_dot else None
        key = f"usdot:{usdot}" if usdot else "vendor:" + json.dumps(
            [observation.source_name, observation.source_record_id], separators=(",", ":"))
        previous = cases.get(key)
        observations = previous.observations if previous else ()
        if observation.digest not in {s.digest for s in observations}:
            observations += (observation,)
        cases[key] = ResearchCase(key, usdot, observations)
    return cases


def is_fresh_applicant(snapshot: Snapshot, since: datetime) -> bool:
    _aware(since)
    return (snapshot.source_kind == "vendor" and snapshot.applicant_at is not None
            and since <= snapshot.applicant_at <= snapshot.fetched_at)


@dataclass(frozen=True)
class Discrepancy:
    field: str
    left: str | None
    right: str | None
    left_evidence: str
    right_evidence: str
    reason: str


def compare_observations(left: Snapshot, right: Snapshot) -> tuple[Discrepancy, ...]:
    """Compare only semantically matching fields, with conservative normalization.

    Adapters must separate legal name from DBA and physical from mailing/agent
    address. Entity status and carrier authority are deliberately not compared.
    A case stays in review even if this comparison finds no differences. An empty
    result never proves identity, freshness, authority, or outreach eligibility.
    """
    a, b = dict(left.fields), dict(right.fields)
    evidence = (left.digest, right.digest)
    result: list[Discrepancy] = []
    for field in ("legal_name", "dba", "physical_address"):
        av, bv = a.get(field), b.get(field)
        if not av and not bv:
            continue
        def norm(v: str | None) -> str:
            return " ".join((v or "").split()).casefold()
        if not av or not bv or norm(av) != norm(bv):
            result.append(Discrepancy(field, av, bv, *evidence,
                                      "missing_evidence" if not av or not bv else "client_clarification"))
    for field in ("usdot", "ma_entity_id"):
        if not a.get(field) or not b.get(field):
            continue
        av, bv = a[field].strip(), b[field].strip()
        if field == "usdot":
            try:
                av, bv = normalize_usdot(av), normalize_usdot(bv)
            except ValueError:
                result.append(Discrepancy(field, a[field], b[field], *evidence, "identity_review"))
                continue
        if av != bv:
            result.append(Discrepancy(field, a[field], b[field], *evidence, "identity_review"))
    return tuple(result)


@dataclass(frozen=True)
class NextAction:
    owner_id: str
    due_at: datetime
    description: str

    def __post_init__(self) -> None:
        if not self.owner_id.strip() or not self.description.strip():
            raise ValueError("next action needs an owner and description")
        _aware(self.due_at)

    def overdue(self, now: datetime) -> bool:
        _aware(now)
        return self.due_at < now


@dataclass(frozen=True)
class Attempt:
    event_id: str
    case_key: str
    occurred_at: datetime
    owner_id: str
    outcome: Literal["answered", "voicemail", "no_answer", "busy", "wrong_number"]

    def __post_init__(self) -> None:
        _aware(self.occurred_at)
        if not all((self.event_id, self.case_key, self.owner_id)):
            raise ValueError("attempt identity and owner are required")
        if self.outcome not in ("answered", "voicemail", "no_answer", "busy", "wrong_number"):
            raise ValueError("unsupported attempt outcome")


@dataclass(frozen=True)
class IssuedPolicy:
    case_key: str
    evidence_ref: str
    verified_by: str
    verified_at: datetime

    def __post_init__(self) -> None:
        _aware(self.verified_at)
        if not all(v.strip() for v in (self.case_key, self.evidence_ref, self.verified_by)):
            raise ValueError("policy conversion requires recorded human verification")


def conversion_metrics(attempts: list[Attempt], policies: list[IssuedPolicy]) -> dict:
    """Counts for one caller-selected cohort/window, not revenue estimates.

    Input must come from an authorized event store; this helper cannot validate
    a producer's license or a carrier document. Conflicting retry IDs fail closed.
    """
    unique: dict[str, Attempt] = {}
    for attempt in attempts:
        if attempt.event_id in unique and unique[attempt.event_id] != attempt:
            raise ValueError("conflicting attempt id")
        unique[attempt.event_id] = attempt
    rows = list(unique.values())
    cases = {a.case_key for a in rows}
    converted = {p.case_key for p in policies} & cases
    answered = sum(a.outcome == "answered" for a in rows)
    return {"attempts": len(rows), "voicemails": sum(a.outcome == "voicemail" for a in rows),
            "answered_attempts": answered, "unique_cases_attempted": len(cases),
            "policy_issued_cases": len(converted),
            "answer_rate": answered / len(rows) if rows else None,
            "attempted_case_conversion_rate": len(converted) / len(cases) if cases else None}
