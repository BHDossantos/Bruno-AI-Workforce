"""Dry-run policy for one post-bind insurance check-in. No I/O, provider or scheduler."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
UTC = timezone.utc


class Action(str, Enum):
    WAIT = "wait"
    SUPPRESS = "suppress"
    INVITE = "invite"
    CALLBACK = "callback"
    REVIEW = "manual_review"
    COMPLETE = "complete"


@dataclass(frozen=True)
class CheckIn:
    # Stable agency household + service cycle ID. Persist one case per distinct sale
    # cycle after coalescing simultaneously bound policies for the same household.
    case_key: str
    state: str
    bound_at: datetime
    owner_id: str | None = None
    booking_url: str | None = None
    preferred: str | None = None
    sms_allowed: bool = False
    email_allowed: bool = False
    call_allowed: bool = False
    opted_out: bool = False
    replied: bool = False
    booked: bool = False
    policy_active: bool = True
    dispatch: str = "new"  # new, queued, accepted, failed, uncertain
    accepted_at: datetime | None = None
    callback_created: bool = False
    # Adapter supplies authenticated, ordered booking state only.
    cancelled_booking_id: str | None = None
    booking_cancelled_at: datetime | None = None
    reopened_for_booking_id: str | None = None


@dataclass(frozen=True)
class Decision:
    action: Action
    reason: str
    key: str | None = None
    channel: str | None = None
    due_at: datetime | None = None


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("use an aware timestamp")
    return value.astimezone(UTC)


def _staffed(value: datetime, closed_dates: frozenset[str]) -> bool:
    local = value.astimezone(ET)
    return local.weekday() < 5 and 9 <= local.hour < 17 and local.date().isoformat() not in closed_dates


def _next_staffed(value: datetime, closed_dates: frozenset[str]) -> datetime:
    if _staffed(value, closed_dates):
        return value
    local = value.astimezone(ET)
    candidate = local.replace(hour=9, minute=0, second=0, microsecond=0)
    if candidate < local:
        candidate += timedelta(days=1)
    # Fail closed on unexpectedly long outage/calendar misconfiguration.
    for _ in range(32):
        if _staffed(candidate, closed_dates):
            return candidate.astimezone(UTC)
        candidate += timedelta(days=1)
    raise ValueError("no staffed window in the next 32 days")


def _booking_url_allowed(url: str | None, allowed_hosts: frozenset[str]) -> bool:
    if not url or not allowed_hosts or any(c.isspace() for c in url):
        return False
    try:
        parsed = urlsplit(url)
        return (parsed.scheme == "https" and parsed.hostname in allowed_hosts
                and parsed.username is None and parsed.password is None
                and parsed.port in (None, 443) and bool(parsed.path.strip("/")))
    except ValueError:
        return False


def plan(case: CheckIn, now: datetime, *, approved_booking_hosts: frozenset[str] = frozenset(),
         closed_dates: frozenset[str] = frozenset()) -> Decision:
    """Return a proposed action; caller must never treat it as authorization to send.

    The adapter must claim the action key atomically and re-check opt-outs and
    contact permissions against live state at dispatch. No historical backfill.
    """
    moment = _aware(now)
    bound = _aware(case.bound_at)
    if not case.case_key or case.state.upper() not in {"MA", "NH"}:
        return Decision(Action.SUPPRESS, "out of pilot scope")
    if case.opted_out or not case.policy_active:
        return Decision(Action.SUPPRESS, "opt-out or inactive policy")
    if case.replied or case.booked:
        return Decision(Action.COMPLETE, "reply or current booking already recorded")
    base = f"insurance-day10:{case.case_key}"
    if case.cancelled_booking_id:
        if case.reopened_for_booking_id == case.cancelled_booking_id:
            return Decision(Action.COMPLETE, "this cancelled booking was already assigned")
        if not case.call_allowed:
            return Decision(Action.SUPPRESS, "no permitted callback")
        if (not case.owner_id or case.dispatch != "accepted" or case.accepted_at is None
                or case.booking_cancelled_at is None
                or not bound <= _aware(case.accepted_at) <= _aware(case.booking_cancelled_at) <= moment):
            return Decision(Action.REVIEW, "cancellation lacks a valid original send, time or assignee",
                            key=f"{base}:cancellation-review")
        due = _next_staffed(_aware(case.booking_cancelled_at), closed_dates)
        if moment < due or not _staffed(moment, closed_dates):
            return Decision(Action.WAIT, "defer cancellation follow-up until staffed",
                            due_at=_next_staffed(max(moment, due), closed_dates))
        return Decision(Action.CALLBACK, "booking cancelled without replacement; reopen existing callback",
                        key=f"{base}:cancel:{case.cancelled_booking_id}", due_at=due)
    if case.callback_created:
        return Decision(Action.COMPLETE, "callback already recorded")
    if case.dispatch in {"failed", "uncertain"}:
        return Decision(Action.REVIEW, "failed or uncertain delivery; no automatic resend or callback",
                        key=f"{base}:delivery-review")
    if case.dispatch == "queued":
        return Decision(Action.WAIT, "awaiting confirmed dispatch result")
    if case.dispatch == "accepted":
        if case.accepted_at is None or _aware(case.accepted_at) < bound or _aware(case.accepted_at) > moment:
            return Decision(Action.REVIEW, "invalid or missing accepted timestamp", key=f"{base}:delivery-review")
        if not case.call_allowed:
            return Decision(Action.SUPPRESS, "no permitted callback")
        if not case.owner_id:
            return Decision(Action.REVIEW, "no callback assignee", key=f"{base}:owner-review")
        due = _next_staffed(_aware(case.accepted_at) + timedelta(hours=24), closed_dates)
        if moment < due:
            return Decision(Action.WAIT, "24 hours or next staffed window not reached", due_at=due)
        if not _staffed(moment, closed_dates):
            return Decision(Action.WAIT, "defer callback task until staffed", due_at=_next_staffed(moment, closed_dates))
        return Decision(Action.CALLBACK, "one human callback task; recheck before dialing",
                        key=f"{base}:callback", due_at=due)
    if case.dispatch != "new":
        return Decision(Action.REVIEW, "unexpected dispatch state", key=f"{base}:delivery-review")
    # No implicit SMS permission or automatic fallback from a declined/unknown preference.
    choice = {"sms": case.sms_allowed, "email": case.email_allowed}
    if not choice.get(case.preferred or "", False):
        return Decision(Action.SUPPRESS, "preferred channel not permitted")
    if not case.owner_id or not _booking_url_allowed(case.booking_url, approved_booking_hosts):
        return Decision(Action.REVIEW, "missing assignee or verified booking route", key=f"{base}:input-review")
    first_date = case.bound_at.astimezone(ET).date() + timedelta(days=10)
    due = _next_staffed(datetime(first_date.year, first_date.month, first_date.day, 9, tzinfo=ET), closed_dates)
    if moment < due:
        return Decision(Action.WAIT, "day 10 or next staffed window not reached", due_at=due)
    if not _staffed(moment, closed_dates):
        return Decision(Action.WAIT, "defer invite until staffed", due_at=_next_staffed(moment, closed_dates))
    return Decision(Action.INVITE, "one preferred-channel booking invitation",
                    key=f"{base}:invite", channel=case.preferred, due_at=due)
