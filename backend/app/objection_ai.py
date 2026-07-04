"""Objection AI — read a prospect's objection, hand back the best rebuttal.

A curated library of the objections insurance buyers actually raise, each with a
proven, compliant rebuttal and the concrete next move. ``handle`` matches the
prospect's words to the closest objection (keyword overlap — works fully offline,
no AI key needed); when the OpenAI key IS connected it additionally tailors the
rebuttal to this exact message + lead, but the proven script is always returned
so a rep is never left empty-handed.

Advisory by default. When a ``lead_id`` is passed it also logs an
``objection_coached`` event to that lead's AI timeline so the coaching history is
visible alongside every other action.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from .models import ActionLog, Lead

log = logging.getLogger("bruno.objection")

# Each objection: the trigger words that signal it, the rebuttal script, and the
# next move. Rebuttals stay honest + compliant — reframe value, offer a no-
# obligation comparison, never disparage or promise a specific price.
OBJECTIONS: list[dict] = [
    {
        "key": "price",
        "label": "Too expensive / price",
        "triggers": ["expensive", "too much", "cost", "afford", "cheaper", "price", "high", "money", "budget"],
        "rebuttal": ("Totally fair — nobody wants to overpay. Let's make it apples-to-apples: "
                     "I'll match your exact coverage and limits so we compare the same thing. "
                     "Most of the time I can hold your protection and lower the monthly, and if I "
                     "can't beat it, I'll tell you straight — no pressure to move."),
        "move": "Offer a same-coverage comparison and break the premium down monthly.",
    },
    {
        "key": "have_insurance",
        "label": "Already have insurance",
        "triggers": ["already have", "already insured", "current", "have insurance", "covered", "with someone"],
        "rebuttal": ("Perfect — you're clearly responsible about it. I'm not asking you to switch "
                     "blindly; I'm offering a free second opinion. I'll review what you have and "
                     "either confirm you're in great shape or show you where you can get the same "
                     "coverage for less. Either way you win."),
        "move": "Position a free coverage review / second opinion — zero obligation.",
    },
    {
        "key": "think_about_it",
        "label": "Need to think about it",
        "triggers": ["think about", "think it over", "get back to you", "not sure", "maybe later", "consider"],
        "rebuttal": ("Makes sense — it's your money. Can I ask what specifically you'd want to think "
                     "through? Rates shift week to week, so let's at least lock today's number — it's "
                     "good for 30 days with no obligation, so you can decide from real figures instead "
                     "of a guess."),
        "move": "Surface the real hesitation, then lock the quote (good 30 days, no obligation).",
    },
    {
        "key": "send_info",
        "label": "Just send me information",
        "triggers": ["send me", "send info", "email me", "some information", "brochure", "details"],
        "rebuttal": ("Happy to. The thing is, generic info won't tell you your price — a quote is "
                     "personalized. Give me literally three quick details and I'll send back numbers "
                     "that actually mean something to you instead of a pamphlet."),
        "move": "Trade the brochure for 3 quick intake answers so the info is a real quote.",
    },
    {
        "key": "not_interested",
        "label": "Not interested",
        "triggers": ["not interested", "no thanks", "no thank", "leave me", "stop", "don't want"],
        "rebuttal": ("Completely fair, and I won't hound you. Most folks are set right up until they "
                     "see a gap they didn't know they had. One question and I'll leave it there: when "
                     "did you last actually compare your rate? If it's been a year, it's usually worth "
                     "60 seconds."),
        "move": "Respectful one-question close: when did you last compare? Then step back.",
    },
    {
        "key": "spouse",
        "label": "Need to talk to spouse / partner",
        "triggers": ["spouse", "wife", "husband", "partner", "talk to", "discuss with", "family"],
        "rebuttal": ("Smart — this is a decision you make together. Let's get the actual numbers in "
                     "front of you both so you're deciding from facts, not a ballpark. I can do a quick "
                     "3-way call, or send a clean one-pager you can walk them through tonight."),
        "move": "Get the numbers to both decision-makers — offer a 3-way call or a one-pager.",
    },
    {
        "key": "bad_timing",
        "label": "Bad timing / call me later",
        "triggers": ["bad time", "busy", "later", "next week", "next month", "call me", "not now", "timing"],
        "rebuttal": ("No problem at all. The quote itself takes about five minutes and stays valid for "
                     "30 days, so we can get it done now and you decide whenever you're ready — nothing "
                     "expires on you. What's genuinely better, later today or tomorrow morning?"),
        "move": "Shrink the ask (5 min, valid 30 days) and pin a specific next time.",
    },
    {
        "key": "trust",
        "label": "Who are you / is this legit",
        "triggers": ["who are you", "scam", "legit", "real", "trust", "how did you get", "spam"],
        "rebuttal": ("Great question — you should ask. I'm a licensed insurance agent local to your "
                     "area; I'm happy to share my license number and you can verify it with the state. "
                     "There's no cost and no obligation to get a quote — worst case you get a free "
                     "benchmark of what you're paying."),
        "move": "Establish credibility (license #, local, verifiable) and reassure no-obligation.",
    },
    {
        "key": "loyal_agent",
        "label": "Happy with my current agent",
        "triggers": ["my agent", "happy with", "loyal", "been with", "years with", "like my"],
        "rebuttal": ("Loyalty is worth a lot and I respect it. Think of me as a second set of eyes at "
                     "renewal — it costs you nothing and usually does one of two things: confirms your "
                     "agent's taking care of you, or catches a gap or a saving they missed. Both are "
                     "good outcomes for you."),
        "move": "Frame yourself as a free renewal second-opinion, not a replacement.",
    },
    {
        "key": "renewal_hike",
        "label": "Renewal just went up",
        "triggers": ["went up", "increase", "raised", "renewal", "higher this year", "jumped", "more expensive"],
        "rebuttal": ("That's exactly the moment a re-shop pays off — carriers raise their books "
                     "unevenly, so when yours jumps, someone else is usually competitive on the same "
                     "coverage. Let's see who's sharpest for your profile right now before you just "
                     "accept the increase."),
        "move": "Turn the rate hike into urgency — re-shop the same coverage now.",
    },
]

_DEFAULT = {
    "key": "general",
    "label": "General hesitation",
    "triggers": [],
    "rebuttal": ("I hear you. Help me understand what's really holding you back and I'll be straight "
                 "with you about whether I can help — there's no cost and no obligation to see the "
                 "numbers, so the worst case is you get a free benchmark of what you're paying today."),
    "move": "Ask an open question to surface the real objection, keep it no-obligation.",
}


def _score(text: str, triggers: list[str]) -> int:
    t = f" {text.lower()} "
    return sum(1 for kw in triggers if kw in t)


def match(text: str) -> dict:
    """Best-matching objection for the prospect's words, with a confidence."""
    text = text or ""
    best, best_score = _DEFAULT, 0
    for obj in OBJECTIONS:
        s = _score(text, obj["triggers"])
        if s > best_score:
            best, best_score = obj, s
    return {"objection": best, "confidence": "high" if best_score >= 2
            else "medium" if best_score == 1 else "low"}


def handle(db: Session, text: str, lead_id: str | None = None) -> dict:
    """Match the objection, return the proven rebuttal (+ an AI-tailored version
    when the key is connected), and log it to the lead's timeline if given."""
    from .ai import client

    m = match(text)
    obj = m["objection"]
    rebuttal = obj["rebuttal"]
    tailored = None

    lead = db.query(Lead).filter(Lead.id == lead_id).first() if lead_id else None
    if client.is_live():
        try:
            who = (lead.company_name or lead.owner_name) if lead else "the prospect"
            tailored = client.complete(
                f'A prospect ({who}) raised this objection: "{text}".\n'
                f'The proven angle is: {obj["move"]}\n'
                "Write a warm, specific, compliant 2-3 sentence spoken reply an insurance agent "
                "could say next. No greeting, no placeholders, never promise an exact price.",
                system="You are a top insurance sales coach. Honest, warm, never pushy.")
            if tailored and tailored.startswith("["):
                tailored = None  # offline stub marker → ignore
        except Exception:  # AI is a bonus; the proven script always stands
            log.debug("objection AI tailoring skipped", exc_info=True)

    if lead is not None:
        db.add(ActionLog(
            actor="objection_ai", action="objection_coached", entity="lead",
            entity_id=str(lead.id),
            detail={"objection": obj["label"],
                    "summary": f"Objection coached: {obj['label']}"}))
        db.commit()

    return {
        "ok": True,
        "objection": obj["label"], "objection_key": obj["key"],
        "confidence": m["confidence"],
        "rebuttal": rebuttal, "tailored": tailored,
        "move": obj["move"],
        "ai_used": bool(tailored),
    }


def catalog() -> list[dict]:
    """The full objection playbook — label, rebuttal and move, for browsing."""
    return [{"key": o["key"], "label": o["label"], "rebuttal": o["rebuttal"],
             "move": o["move"]} for o in OBJECTIONS]
