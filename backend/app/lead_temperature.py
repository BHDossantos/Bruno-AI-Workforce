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


def classify(status: str | None) -> str:
    """Map a pipeline status to a temperature bucket."""
    s = (status or "").strip().lower()
    if s in _HOT:
        return HOT
    if s in _WARM:
        return WARM
    if s in _DEAD:
        return DEAD
    return COLD  # New, Drafted, Sent, contact, insurance_emailed, unknown → cold
