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


def _company(lead: Lead) -> str:
    return (lead.company_name or "your company").strip() or "your company"


def _fill(text: str, lead: Lead) -> str:
    num = (settings.producer_callback or "").strip()
    for token, value in {
        "{first}": _first_name(lead),
        "{producer}": _producer(),
        "{vehicle}": _vehicle(lead),
        "{company}": _company(lead),
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

    # ── Commercial trucking (DOT / motor carriers). Fill the bracketed values with
    # the real operation/quote details before sending. ─────────────────────────────
    {"id": "truck_email_first", "name": "Trucking Email 1 — First contact",
     "subject": "Truck insurance for {company}",
     "body": (
         "Hi {first},\n\n"
         "Congratulations on getting {company} started.\n\n"
         "I'm {producer} with Thrust Insurance. I can help review truck insurance around "
         "what you haul, where you operate, and when you need coverage to begin.\n\n"
         "My goal is to give you a clear picture of the coverage, upfront payment, and total "
         "cost before you decide.\n\n"
         "Are you still arranging insurance, or have you already handled it?")},
    {"id": "truck_email_followup", "name": "Trucking Email 2 — First follow-up",
     "subject": "Start date for {company}?",
     "body": (
         "Hi {first},\n\n"
         "Is {company} aiming to start hauling this month, or are you still planning ahead?\n\n"
         "If insurance is still open, reply with the truck type, the state where it will be "
         "based, and your target start date.\n\n"
         "I'll check whether our available insurance markets fit the operation before asking "
         "you to complete a full application.\n\n"
         "{producer}")},
    {"id": "truck_email_compare", "name": "Trucking Email 3 — Competing-quote review",
     "subject": "A clear comparison for {company}",
     "body": (
         "Hi {first},\n\n"
         "Already have a truck insurance quote?\n\n"
         "I can help review it alongside any option we're able to offer, including coverage "
         "limits, exclusions, deductibles, upfront payment, installment terms, and total "
         "cost.\n\n"
         "I won't call it a better deal just because the first payment is lower.\n\n"
         "Would a written comparison help you decide?\n\n"
         "{producer}")},
    {"id": "truck_email_docs", "name": "Trucking Email 4 — Quote + document collection",
     "subject": "Your truck insurance quote: next steps",
     "body": (
         "Hi {first},\n\n"
         "To prepare a quote for {company}, please confirm your target start date, what you "
         "haul, where you operate, and whether you run under your own authority or lease onto "
         "another carrier.\n\n"
         "Please use [Approved secure upload link] for the documents we discussed: business "
         "and DOT/authority details where applicable, garaging information, truck/trailer "
         "details and VINs, driver information, and any required loss history.\n\n"
         "Please also include the insurance requirements in your lease, lender agreement, or "
         "shipper/broker contract.\n\n"
         "I'll confirm the exact documents and any report authorizations needed. Please don't "
         "email or text license photos, bank/card details, passwords, or FMCSA login codes.\n\n"
         "Is [Date] still your target start date?\n\n"
         "{producer}")},
    {"id": "truck_email_present", "name": "Trucking Email 5 — Present the quote",
     "subject": "{company}: truck insurance quote and payment breakdown",
     "body": (
         "Hi {first},\n\n"
         "Based on the operation we reviewed — [Truck(s)], [Cargo], [Territory], and "
         "[Authority/lease arrangement] — here is the proposal from [Insurer].\n\n"
         "COVERAGE\n"
         "  [Coverage A]: [Limit] | [Deductible, if applicable]\n"
         "  [Coverage B]: [Limit] | [Deductible, if applicable]\n"
         "  Other selected coverages: [Details]\n"
         "  Important exclusions / not included: [Actual details]\n\n"
         "COST AND PAYMENT TERMS\n"
         "  Policy term: [Start/end]\n"
         "  Policy premium: $[Amount]\n"
         "  Taxes and fees: [Itemized or confirmed included]\n"
         "  Finance charge, if applicable: $[Amount]\n"
         "  Total payable under the selected plan: $[Amount]\n"
         "  Due initially: $[Amount]\n"
         "  Remaining payments: [Number] x $[Amount] on [Schedule]\n"
         "  Pay-in-full alternative, if available: $[Amount]\n"
         "  Cancellation / minimum-earned-premium terms: [Actual terms]\n\n"
         "REQUESTED START AND REMAINING REQUIREMENTS\n"
         "  Requested effective date/time/time zone: [Details]\n"
         "  Outstanding underwriting or binding conditions: [Actual conditions]\n"
         "  Required insurance filings and status, where applicable: [Details]\n\n"
         "Please review the full proposal at [Approved secure link]. This is a quote, not "
         "confirmation of coverage; the policy terms and endorsements govern.\n\n"
         "Would you like to review it at [Time A] or [Time B] [Their time zone]?\n\n"
         "{producer}")},
    {"id": "truck_email_decide", "name": "Trucking Email 6 — Ask for a decision",
     "subject": "{company}: what would help you decide?",
     "body": (
         "Hi {first},\n\n"
         "You mentioned that [Customer's stated priority] was important.\n\n"
         "The proposal we reviewed offers [Verified relevant feature] at a total payable of "
         "$[Amount] under [Payment plan]. The main limitation to keep in mind is "
         "[Actual limitation].\n\n"
         "What do we need to resolve before you decide: the coverage, the payment terms, or "
         "the start date?\n\n"
         "If the proposal meets your needs, would you like us to submit the coverage request "
         "for [Date/time/time zone]?\n\n"
         "Coverage is not active until it has been properly confirmed.\n\n"
         "{producer}")},
    {"id": "truck_email_close_followups", "name": "Trucking Email 7 — Final unanswered follow-up",
     "subject": "Closing my follow-ups for {company}",
     "body": (
         "Hi {first},\n\n"
         "I haven't heard back, so I'll close out my follow-ups rather than keep filling your "
         "inbox.\n\n"
         "When truck insurance becomes a priority, you can reply with your truck type, home "
         "state, and target start date, and we can see whether we're a fit.\n\n"
         "Thank you,\n{producer}")},
]


# ── Text templates ────────────────────────────────────────────────────────────
SMS_TEMPLATES = [
    {"id": "missed_call", "name": "Text 1 — After missed call",
     "body": (
         "Hi {first}, this is {producer}, your licensed insurance producer. I just tried "
         "reaching you regarding the insurance quote you requested. I already have most of "
         "your information and may have found additional discounts for you. Whenever you "
         "have a few minutes, simply reply to this text or call me{callback}. Looking "
         "forward to helping you. Reply STOP to opt out.")},
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

    # ── Commercial trucking (DOT / motor carriers) — progression: reply → qualify
    # → collect → quote → close. Keep {company}/placeholders filled with real values;
    # only send to leads with documented, agency-approved consent. ──────────────────
    {"id": "truck_open_new_dot", "name": "Trucking: Opener — new DOT",
     "body": ("Hi {first}, {producer} with Thrust Insurance. Congrats on the new DOT! Are you "
              "still comparing truck insurance, or already covered? Reply STOP to opt out.")},
    {"id": "truck_open_start_date", "name": "Trucking: Opener — start date (A/B test)",
     "body": ("Hi {first}, {producer} with Thrust Insurance. Is {company} planning to start "
              "hauling this month or later? I can help review truck insurance options. Reply "
              "STOP to opt out.")},
    {"id": "truck_open_quote_request", "name": "Trucking: Opener — actual quote request",
     "body": ("Hi {first}, {producer} with Thrust Insurance. Thanks for requesting a truck "
              "insurance quote through [Source]. What date do you need coverage to start? "
              "Reply STOP to opt out.")},
    {"id": "truck_followup_1", "name": "Trucking: Follow-up 1 — no response",
     "body": ("Hi {first}, {producer} at Thrust Insurance. Is insurance still on your startup "
              "checklist, or have you already taken care of it? Reply STOP to opt out.")},
    {"id": "truck_followup_2", "name": "Trucking: Follow-up 2 — offer value",
     "body": ("Hi {first}, {producer} at Thrust Insurance. I can help review coverage, the "
              "upfront payment and total cost. Would that be useful before you choose a truck "
              "policy? Reply STOP to opt out.")},
    {"id": "truck_followup_final", "name": "Trucking: Follow-up — final (then stop)",
     "body": ("Hi {first}, {producer} at Thrust Insurance. I'll close out my follow-ups for "
              "now. If truck insurance is still on your list, reply QUOTE and we can pick it "
              "up. Reply STOP to opt out.")},
    {"id": "truck_reply_yes_1", "name": "Trucking: Reply YES — qualify (state/truck)",
     "body": ("Absolutely, {first}. What state will the truck be based in, and what type of "
              "truck will you run? — {producer}, Thrust Insurance. Reply STOP to opt out.")},
    {"id": "truck_reply_yes_2", "name": "Trucking: Reply YES — qualify (cargo/authority)",
     "body": ("Thanks, {first}. What will you haul, and will you run under your own authority "
              "or lease onto another carrier? — {producer}, Thrust Insurance. Reply STOP to "
              "opt out.")},
    {"id": "truck_book_call", "name": "Trucking: Move to a call",
     "body": ("{first}, can we review this while you're parked? I have [Time A] or [Time B] "
              "[Their time zone]. Which works? — {producer}, Thrust Insurance. Reply STOP to "
              "opt out.")},
    {"id": "truck_secure_docs", "name": "Trucking: Secure document request",
     "body": ("{first}, here's the secure upload link we discussed: [Approved secure link]. "
              "Please don't text license photos or payment details. — {producer}, Thrust "
              "Insurance. Reply STOP to opt out.")},
    {"id": "truck_missing_info", "name": "Trucking: Missing-information follow-up",
     "body": ("Hi {first}, {producer} at Thrust Insurance. I still need [Specific item] to "
              "move your quote forward. Can you upload it through our secure link today? Reply "
              "STOP to opt out.")},
    {"id": "truck_competing_quote", "name": "Trucking: They already have a quote",
     "body": ("{first}, I can compare the written quotes for coverage, exclusions, deductibles "
              "and total cost. Shall I send our secure upload link? — {producer}, Thrust "
              "Insurance. Reply STOP to opt out.")},
    {"id": "truck_quote_ready", "name": "Trucking: Quote ready",
     "body": ("Hi {first}, {producer} at Thrust Insurance. Your written truck insurance quote "
              "is ready. Can we review it at [Time A] or [Time B] [Their time zone]? Reply "
              "STOP to opt out.")},
    {"id": "truck_quote_followup", "name": "Trucking: Quote follow-up — find the blocker",
     "body": ("Hi {first}, {producer} at Thrust Insurance. What's the main thing you need to "
              "resolve: the upfront payment, the coverage, or the start date? Reply STOP to "
              "opt out.")},
    {"id": "truck_close", "name": "Trucking: Direct close",
     "body": ("{first}, shall we request coverage with [Insurer] for [Date/time/time zone]? "
              "Coverage is not active until confirmed. — {producer}, Thrust Insurance. Reply "
              "STOP to opt out.")},
    {"id": "truck_pending", "name": "Trucking: Yes — coverage still pending",
     "body": ("{first}, your coverage request is with [Insurer]. Coverage is NOT confirmed "
              "yet. I'll update you by [Agreed time]. — {producer}, Thrust Insurance. Reply "
              "STOP to opt out.")},
    {"id": "truck_confirmed", "name": "Trucking: Coverage confirmed",
     "body": ("{first}, [Insurer] confirmed policy [Number], effective [Date/time/time zone]. "
              "Your documents are in [Approved portal]. — {producer}, Thrust Insurance. Reply "
              "STOP to opt out.")},
    {"id": "truck_not_ready", "name": "Trucking: Not ready yet",
     "body": ("Understood, {first}. What month are you aiming to start? With your permission, "
              "I can check back closer to that date. — {producer}, Thrust Insurance. Reply "
              "STOP to opt out.")},
    {"id": "truck_renewal", "name": "Trucking: Renewal",
     "body": ("Hi {first}, {producer} at Thrust Insurance. Your truck policy renews on "
              "[Verified date]. Shall we review any changes to your trucks, drivers or routes? "
              "Reply STOP to opt out.")},
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

    # ── Commercial trucking (DOT / motor carriers) ──────────────────────────────────
    {"id": "truck_first_call", "name": "Trucking Call 1 — First live call",
     "framework": ["Safety", "Status", "Qualify"],
     "script": (
         "SAFETY\n"
         "“Hi {first}, this is {producer} with Thrust Insurance. This is a trucking-insurance "
         "sales call. Are you parked somewhere safe to talk?”\n"
         "  If driving: “I'll let you focus on the road. Please call me when you're safely "
         "parked.” (End the call — do not start the pitch.)\n\n"
         "STATUS\n"
         "“I'm calling about truck insurance for {company}. Are you still arranging coverage, "
         "or is it already handled?”\n\n"
         "QUALIFY (if still looking)\n"
         "“What type of truck will you run, and what date are you hoping to start?”\n"
         "“Let me check whether our insurance markets fit your operation. May I ask a few "
         "questions?”")},
    {"id": "truck_quote_request_call", "name": "Trucking Call 2 — Actual quote request",
     "framework": ["Confirm", "Qualify", "Priorities"],
     "script": (
         "“Hi {first}, {producer} with Thrust Insurance. You requested a truck insurance quote "
         "through [Actual source]. Are you safely parked and available to talk?”\n\n"
         "“Before I ask for documents, I want to make sure we can help. Where will the truck "
         "be based, what will you haul, and when do you need coverage to start?”\n\n"
         "“Are you starting under your own authority or leasing onto another carrier?”\n\n"
         "“What matters most in your decision: the coverage, the upfront payment, the total "
         "cost, or the timing?”")},
    {"id": "truck_discovery_call", "name": "Trucking Call 3 — Discovery",
     "framework": ["Garaging", "Equipment", "Cargo", "Authority", "Routes", "Drivers",
                   "Requirements", "Timeline"],
     "script": (
         "Work these conversationally — not all at once:\n\n"
         "“Let's make sure the quote reflects the business you'll actually run.”\n"
         "— Where will the truck normally be garaged?\n"
         "— What trucks and trailers will you operate?\n"
         "— What cargo will you haul, including specialized loads?\n"
         "— Own authority, lease onto another carrier, or your own business's goods?\n"
         "— Which states or routes will you run, and how far from home?\n"
         "— How many drivers, and what relevant experience?\n"
         "— What insurance does your lease, lender, or customer contract require?\n"
         "— Existing coverage or another quote we should review?\n"
         "— Target start date, and who else needs to approve the decision?\n\n"
         "SUMMARIZE\n"
         "“So the operation is [Accurate recap], your priority is [Priority], and your target "
         "is [Date]. Have I got that right? The next step is [Specific action]. Shall we set a "
         "follow-up for [Time/time zone]?”")},
    {"id": "truck_quote_call", "name": "Trucking Call 4 — Quote presentation",
     "framework": ["Confirm operation", "Coverage", "Cost", "Payments", "Conditions", "Ask"],
     "script": (
         "“Before we look at price, let's confirm this is based on [Trucks], hauling [Cargo], "
         "in [Territory], under [Authority/lease arrangement]. Is that accurate?”\n\n"
         "“The proposal includes [Selected coverages and limits]. The main exclusions or "
         "restrictions you need to understand are [Actual details]. The deductibles are "
         "[Details].”\n\n"
         "“The policy premium is $[Amount]. With [Taxes/fees/finance charges], the total "
         "payable under this plan is $[Amount]. You would pay $[Initial] initially, then "
         "[Number] payments of $[Amount].”\n\n"
         "“The requested start is [Date/time/time zone], subject to [Actual conditions].”\n\n"
         "“How does this compare with what you needed? What would you like me to explain "
         "before you decide?”")},
    {"id": "truck_close_call", "name": "Trucking Call 5 — Closing",
     "framework": ["Fit check", "Ask for the sale", "Next steps"],
     "script": (
         "“Based on what we reviewed, does this proposal meet your needs?” (Pause and "
         "listen.)\n\n"
         "“Would you like us to submit the request to [Insurer] for [Date/time/time zone]?”\n\n"
         "If yes: “Great. We need [Actual remaining steps]. I'll send the approved application "
         "and payment process. Coverage is not active until it is confirmed through the "
         "authorized process, and I'll give you the exact effective date and time in "
         "writing.”\n\n"
         "If they hesitate: “What's the one issue we still need to resolve?”")},
    {"id": "truck_voicemail", "name": "Trucking — Voicemail (live-agent)",
     "framework": ["Voicemail"],
     "script": (
         "“Hi {first}, {producer} with Thrust Insurance, calling about truck insurance for "
         "{company}. Are you still comparing coverage, or already set? You can reach me"
         "{callback}. Again, {producer}{callback}. Thank you.”\n\n"
         "(Live-agent script only — not approval for a prerecorded, ringless, or AI-voice "
         "campaign.)")},
]


# ── Objection responses (quick reference while on a call or replying) ──────────
OBJECTION_RESPONSES = [
    {"id": "obj_too_expensive", "name": "“Your quote is too expensive.”",
     "body": ("Understood. Is the bigger issue the amount needed upfront, or the total cost "
              "over the policy term? Let's review the available payment options and coverage "
              "choices without changing the facts about your operation or hiding a gap.")},
    {"id": "obj_cheaper_elsewhere", "name": "“Someone else gave me a cheaper quote.”",
     "body": ("That may be a good option. Before you decide, let's make sure we're comparing "
              "the same operation, coverage limits, deductibles, exclusions, and total payment "
              "cost. If their proposal is genuinely the better fit, I'll tell you.")},
    {"id": "obj_have_agent", "name": "“I already have an agent.”",
     "body": ("That's good. I'm not asking you to replace someone who's doing a good job. "
              "Would a second review at renewal be useful, or would you prefer I leave it "
              "here?")},
    {"id": "obj_think_about_it", "name": "“I need to think about it.”",
     "body": ("Of course. Which part would you like to think through: the coverage, the "
              "payment terms, or whether the timing is right? I can clarify that, and then the "
              "decision is yours.")},
    {"id": "obj_lower_down", "name": "“I need a lower down payment.”",
     "body": ("Let me check the payment plans actually available for this proposal. I'll show "
              "you the initial payment, every remaining payment, and any finance charges, so a "
              "lower upfront amount doesn't disguise a higher total cost.")},
    {"id": "obj_are_you_dot", "name": "“Are you with DOT?”",
     "body": ("I'm {producer} with Thrust Insurance, a private insurance agency. We're not DOT "
              "or FMCSA, and this is an insurance sales conversation — not a government notice. "
              "I can give you our agency contact and licensing information so you can verify us "
              "independently before sharing documents.")},
    {"id": "obj_how_got_number", "name": "“How did you get my number?”",
     "body": ("Your business contact information came from [Actual recorded source]. I'm "
              "contacting you about trucking insurance, not on behalf of DOT. Would you prefer "
              "that I stop contacting you?")},
    {"id": "obj_activate_authority", "name": "“Can you activate my authority so I can haul today?”",
     "body": ("I can check the insurer's requirements and the insurance filing status, but I "
              "can't promise same-day coverage or authority activation. We need confirmed "
              "coverage and all applicable operating permissions in place before you haul. "
              "Let's identify what's actually outstanding.")},
    {"id": "obj_stop", "name": "“Stop contacting me.”",
     "body": ("You're opted out of marketing texts from Thrust Insurance. No further marketing "
              "texts will be sent. (Then suppress the contact — do not switch channel or number "
              "to continue the pitch.)")},
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
        "objections": [{"id": t["id"], "name": t["name"], "body": _fill(t["body"], lead)}
                       for t in OBJECTION_RESPONSES],
    }
