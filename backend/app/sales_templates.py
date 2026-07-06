"""Sales conversation templates — email, text, and call scripts.

The Bruno Method: CONNECT → DISCOVER → EDUCATE → RECOMMEND → CLOSE. These are
named, pickable templates (a dropdown per channel on the lead profile), with
tokens filled from the lead's real data (first name, vehicle) and the producer's
settings (name, callback number). The customer should feel like they're talking
to their future advisor, not a salesperson.
"""
from __future__ import annotations

from .config import settings
from .models import Lead


def _producer() -> str:
    return settings.producer_name or "Bruno Dos Santos"


def _first_name(lead: Lead) -> str:
    eq = (lead.intake or {}).get("everquote") or {}
    if eq.get("first_name"):
        return eq["first_name"]
    return ((lead.owner_name or "there").split() or ["there"])[0]


def _vehicle(lead: Lead) -> str:
    eq = (lead.intake or {}).get("everquote") or {}
    parts = [str(eq.get("vehicle_year") or "").strip(),
             (eq.get("vehicle_make") or "").title(),
             (eq.get("vehicle_model") or "").title()]
    return " ".join(p for p in parts if p) or "vehicle"


def _fill(text: str, lead: Lead) -> str:
    num = (settings.producer_callback or "").strip()
    for token, value in {
        "{first}": _first_name(lead),
        "{producer}": _producer(),
        "{vehicle}": _vehicle(lead),
        "{callback}": f" at {num}" if num else "",
    }.items():
        text = text.replace(token, value)
    return text


# ── Email templates (subject + body) ──────────────────────────────────────────
EMAIL_TEMPLATES = [
    {"id": "first_contact", "name": "Email 1 — First contact",
     "subject": "Your insurance quote request",
     "body": (
         "Hi {first},\n\n"
         "Thank you for requesting an insurance quote.\n\n"
         "My name is {producer}, and I'll personally be assisting you.\n\n"
         "I've already started reviewing your request and may have found additional "
         "discounts that could improve your pricing and coverage.\n\n"
         "Before I finalize everything, I'd just like to verify a few details to make "
         "sure your quote is as accurate as possible.\n\n"
         "You can simply reply to this email, call me, or text me.\n\n"
         "Most reviews take less than five minutes.\n\n"
         "I look forward to helping you.\n\n"
         "Sincerely,\n{producer}\nLicensed Insurance Producer")},
    {"id": "quote", "name": "Email 2 — Quote / options",
     "subject": "Your personalized insurance options",
     "body": (
         "Hi {first},\n\n"
         "Thank you for taking the time to speak with me.\n\n"
         "I've attached your personalized insurance proposal.\n\n"
         "Rather than simply giving you the lowest possible price, I focused on finding "
         "the best balance between protection, value, and affordability.\n\n"
         "Inside you'll find:\n"
         "  ✓ Coverage recommendations\n"
         "  ✓ Monthly premium\n"
         "  ✓ Optional savings\n"
         "  ✓ Additional protection available\n\n"
         "I'd be happy to answer any questions before you make a decision.\n\n"
         "You can reply to this email, call me, or text me directly.\n\n"
         "Thank you,\n{producer}")},
    {"id": "value", "name": "Email 3 — Value",
     "subject": "Before you choose your insurance...",
     "body": (
         "Hi {first},\n\n"
         "Many people compare insurance based only on price. That's understandable.\n\n"
         "However, after helping many clients, I've learned something important. "
         "Everyone wants the lowest premium until they have an accident. That's when "
         "coverage matters most.\n\n"
         "My goal isn't simply to help you spend less. It's to make sure you're properly "
         "protected if something unexpected happens.\n\n"
         "If you'd like to review your options together, I'd be happy to help.\n\n"
         "Best,\n{producer}")},
    {"id": "follow_up", "name": "Email 4 — Follow-up",
     "subject": "Any questions?",
     "body": (
         "Hi {first},\n\n"
         "I just wanted to check in regarding the insurance proposal I prepared for you.\n\n"
         "If anything needs to be adjusted — coverage, deductibles, payment options, or "
         "simply if you have questions — please let me know.\n\n"
         "I'm here to help.\n\n"
         "Have a wonderful day.\n{producer}")},
    {"id": "welcome", "name": "Email 5 — Welcome (won)",
     "subject": "Welcome to the family!",
     "body": (
         "Hi {first},\n\n"
         "Thank you for choosing me to help with your insurance. I truly appreciate your "
         "trust.\n\n"
         "My commitment doesn't end once your policy starts. If you ever need assistance "
         "with:\n"
         "  • Claims\n  • Billing\n  • Coverage changes\n  • Additional vehicles\n"
         "  • Homeowners\n  • Umbrella\n  • Life changes\n\n"
         "I'm only a phone call, text message, or email away.\n\n"
         "Thank you again.\n{producer}")},
]


# ── Text templates ────────────────────────────────────────────────────────────
SMS_TEMPLATES = [
    {"id": "missed_call", "name": "Text 1 — After missed call",
     "body": (
         "Hi {first}, this is {producer}, your licensed insurance producer. I just tried "
         "reaching you regarding the insurance quote you requested. I already have most of "
         "your information and may have found additional discounts for you. Whenever you "
         "have a few minutes, simply reply to this text or call me{callback}. Looking "
         "forward to helping you.")},
    {"id": "after_quote", "name": "Text 2 — After quote",
     "body": (
         "Hi {first}, I finished reviewing your insurance options. I have your quote ready "
         "and would love to walk you through it. There are a couple of coverage options and "
         "potential discounts I'd like to explain before you make a decision. Call or text "
         "me whenever you're available. — {producer}")},
    {"id": "follow_up", "name": "Text 3 — Follow-up",
     "body": (
         "Hi {first}, just checking in to see if you had any questions about the quote I "
         "prepared. I'm happy to explain anything or make adjustments if needed. No "
         "pressure — just let me know how I can help. Have a great day.")},
    {"id": "last_attempt", "name": "Text 4 — Last attempt",
     "body": (
         "Hi {first}, I haven't heard back, so I wanted to check in one last time. If you're "
         "still interested in reviewing your insurance options, I'd be happy to help. "
         "Otherwise, I'll close your file for now. Just reply: Interested or Already "
         "Covered. Either way, thank you. — {producer}")},
]


# ── Call scripts (read while dialing; log the outcome after) ───────────────────
CALL_SCRIPTS = [
    {"id": "first_call", "name": "Call 1 — First call (Bruno Method)",
     "framework": ["Connect", "Discover", "Educate", "Recommend", "Close"],
     "script": (
         "CONNECT\n"
         "“Hi, may I speak with {first}, please?”\n"
         "“Hi {first}, my name is {producer}, and I'm a licensed insurance producer. I'm "
         "calling because you recently requested an insurance quote online. Did I catch you "
         "at an okay time?”\n"
         "  If no: “No problem at all — I want to respect your time. Is later today or "
         "tomorrow better for a quick five-minute conversation?”\n\n"
         "BUILD TRUST\n"
         "“Before we get started, my goal today isn't to pressure you into buying anything. "
         "My job is simply to make sure you're getting the best protection at the best value "
         "possible — and if I can save you money or improve your coverage, that's a bonus.”\n\n"
         "DISCOVER\n"
         "“What made you start shopping for insurance today?” (Listen.)\n"
         "“I understand. Besides price, what matters most to you?” "
         "(Better coverage / service / lower premium / faster claims / bundle discounts.)\n"
         "— Tell me about your {vehicle}.\n"
         "— Is this your only vehicle? Anyone else drive it?\n"
         "— Do you rent or own your home?\n"
         "— Any claims recently?\n"
         "— How long with your current company?\n\n"
         "TRANSITION\n"
         "“Based on everything you've shared, I think I have a good understanding of what "
         "you're looking for. Let me put together the best options available for you.”\n\n"
         "EDUCATE / RECOMMEND (present the quote)\n"
         "“Here's what I found. The policy I recommend gives you:\n"
         "  ✓ Better liability protection\n  ✓ Rental reimbursement\n"
         "  ✓ Roadside assistance\n  ✓ Optional uninsured motorist\n"
         "  ✓ Competitive pricing”\n"
         "“Your monthly investment would be around…” (NOW talk price.)\n\n"
         "CLOSE (assumptive)\n"
         "“Everything looks good. Would you like your coverage to begin today, or would you "
         "prefer to start on your current renewal date?”")},
]


def for_lead(lead: Lead) -> dict:
    """All templates, rendered for this lead (tokens filled)."""
    return {
        "email": [{"id": t["id"], "name": t["name"],
                   "subject": _fill(t["subject"], lead), "body": _fill(t["body"], lead)}
                  for t in EMAIL_TEMPLATES],
        "sms": [{"id": t["id"], "name": t["name"], "body": _fill(t["body"], lead)}
                for t in SMS_TEMPLATES],
        "call": [{"id": t["id"], "name": t["name"], "framework": t["framework"],
                  "script": _fill(t["script"], lead)} for t in CALL_SCRIPTS],
    }
