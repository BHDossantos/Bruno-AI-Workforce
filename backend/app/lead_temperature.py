"""Lead temperature — cold / warm / hot — derived from a lead's pipeline status.

One definition shared by every business (insurance, BnB Global consulting,
SavoryMind) so "cold, warm and hot leads" means the same thing everywhere:

  cold — sourced/contacted but no engagement yet (New, Drafted, Sent, imported)
  warm — they engaged (opened/replied/needs follow-up)
  hot  — buying signals (interested, demo/meeting, proposal, negotiation, won)
  dead — closed lost / opted out (kept separate so it doesn't pollute the funnel)
"""
from __future__ import annotations

_HOT = {
    "interested", "meeting", "meeting requested", "meeting booked", "booked",
    "demo", "demo booked", "demo requested", "proposal", "proposal sent",
    "negotiation", "closed won", "won",
}
_WARM = {"replied", "opened", "follow-up needed", "reply", "engaged"}
_DEAD = {"closed lost", "lost", "do_not_contact", "unsubscribed", "bounced"}

COLD, WARM, HOT, DEAD = "cold", "warm", "hot", "dead"

# In-market inbound leads (EverQuote quote requests, opt-in web leads) are HOT by
# SOURCE the moment they arrive — they raised their hand — even before they reply.
# We tag those with a high score on import, so a score at/above this floors the
# temperature to hot (unless they've since gone dead). This is what makes a fresh
# EverQuote lead sort and get worked FIRST instead of being treated as cold.
HOT_SCORE = 80


def classify(status: str | None, score: int | None = None) -> str:
    """Map a pipeline status (and optional lead score) to a temperature bucket.

    Dead/lost always wins. Then explicit hot/warm statuses. Then a high score
    (in-market inbound leads) floors to hot even at a still-'New' status. `score`
    is optional so every existing status-only caller keeps its exact behavior."""
    s = (status or "").strip().lower()
    if s in _DEAD:
        return DEAD
    if s in _HOT:
        return HOT
    if s in _WARM:
        return WARM
    if score is not None and score >= HOT_SCORE:
        return HOT  # freshly-imported EverQuote / opt-in lead — hot by source
    return COLD  # New, Drafted, Sent, contact, insurance_emailed, unknown → cold


def statuses_for(temperature: str) -> set[str] | None:
    """The lowercase statuses belonging to hot/warm/dead, so a temperature filter
    can be pushed into SQL instead of applied after an unrelated row LIMIT
    (which would silently starve it once other statuses dominate the sort order).
    Returns None for 'cold' — it's everything NOT in the other three buckets,
    including unknown/blank statuses, so callers need a NOT-IN instead."""
    return {HOT: _HOT, WARM: _WARM, DEAD: _DEAD}.get((temperature or "").strip().lower())


def all_classified_statuses() -> set[str]:
    """Every status that is NOT cold — the complement defines 'cold'."""
    return _HOT | _WARM | _DEAD


def send_priority_order(Lead, Message):
    """ORDER BY clauses for the auto-send queue — the operator's stated priority:

        new HOT & uncontacted → HOT needing follow-up → WARM → COLD  (dead last)

    Within a tier: uncontacted first, then hottest score, then the oldest draft
    (fair pacing). Pass the Lead + Message models. Lead may be OUTER-joined, so its
    columns can be NULL for non-lead drafts → those fall into the cold tier.
    Splat into a query: ``.order_by(*send_priority_order(Lead, Message))``."""
    from sqlalchemy import case, func
    score = func.coalesce(Lead.score, 0)
    status = func.lower(func.coalesce(Lead.status, ""))
    band = case(
        (status.in_(list(_DEAD)), 4),                          # dead / closed lost → last
        (status.in_(list(_HOT)) | (score >= HOT_SCORE), 0),    # hot (status OR in-market score)
        (status.in_(list(_WARM)), 1),                          # warm (engaged/replied)
        else_=2,                                               # cold / new / unknown
    )
    contacted = func.coalesce(Lead.times_contacted, 0)
    # band → uncontacted-first → hottest score → oldest draft.
    return [band.asc(), contacted.asc(), score.desc(), Message.created_at.asc()]

