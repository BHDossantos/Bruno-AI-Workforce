"""Marketing & sales funnel planner.

Given a connected account (provider + capabilities + goal), this builds the
concrete, automated funnel the platform will run for it — mapping each funnel
stage (Attract → Capture → Nurture → Convert → Retain) to real actions the
platform can perform with that account's capabilities.

The plan is what the dashboard shows ("here's exactly what Bruno will do for this
account") and what the scheduler executes. Actions are tagged `auto` (runs with
no human step) or `assist` (drafted & queued for one-click approval, used where a
platform's ToS forbids automation).
"""
from __future__ import annotations

from .integrations import registry

STAGE_LABELS = {
    "attract": "Attract — get in front of the right audience",
    "capture": "Capture — turn attention into known leads",
    "nurture": "Nurture — build trust with sequenced follow-up",
    "convert": "Convert — drive the booking / sale",
    "retain": "Retain — repeat business & referrals",
}

# Capability → the funnel action(s) it unlocks, per stage.
# Each action: (stage, title, mode, description)
_CAPABILITY_ACTIONS: dict[str, list[tuple]] = {
    "publish_auto": [
        ("attract", "Auto-publish content", "auto",
         "AI writes on-brand posts using your marketing skills and publishes them on schedule."),
    ],
    "publish_assist": [
        ("attract", "Draft & queue content", "assist",
         "AI writes on-brand posts and queues them for one-click publishing (ToS-safe)."),
    ],
    "dm_assist": [
        ("nurture", "One-click outreach DMs", "assist",
         "AI drafts personalized DMs to warm prospects; you send with one click."),
    ],
    "email_auto": [
        ("capture", "Lead-magnet & opt-in emails", "auto",
         "Sends value-first emails to new leads, with CAN-SPAM footer and daily caps."),
        ("nurture", "Automated email sequence", "auto",
         "Runs the multi-step follow-up cadence (days 3/6/9/12/15/29/43), pausing on reply."),
        ("convert", "Booking / offer email", "auto",
         "Sends the call-to-action email with your scheduling link when a lead warms up."),
    ],
    "sms_auto": [
        ("nurture", "Two-way SMS on warm leads", "auto",
         "After a lead replies, auto-texts them and chats back and forth (opt-in / TCPA-safe)."),
    ],
    "ads_auto": [
        ("attract", "Managed ad campaigns", "auto",
         "Creates audiences, monitors performance, pauses losers and shifts budget to winners."),
    ],
    "crm_sync": [
        ("capture", "CRM contact sync", "auto",
         "Every captured lead is pushed to your CRM with source, score and next step."),
        ("retain", "Pipeline hygiene", "auto",
         "Keeps deal stages and last-touch dates in sync so nothing goes cold."),
    ],
    "commerce_sync": [
        ("convert", "Abandoned-cart recovery", "auto",
         "Detects abandoned checkouts and triggers recovery emails/SMS."),
        ("retain", "Post-purchase & win-back", "auto",
         "Sends thank-you, review-request, cross-sell and win-back flows after orders."),
    ],
    "lead_capture": [
        ("capture", "Inbound lead ingest", "auto",
         "Form fills, replies and bookings are captured, scored and routed automatically."),
    ],
    "analytics": [
        ("retain", "Performance tracking", "auto",
         "Pulls reach/clicks/conversions into the CEO dashboard daily."),
    ],
}


def build_plan(provider_key: str, goal: str | None = None) -> dict:
    """Return the funnel plan for a provider, optionally tailored to a goal."""
    prov = registry.get_provider(provider_key)
    if not prov:
        return {"provider": provider_key, "stages": [], "unsupported": True}

    caps = prov.get("capabilities", [])
    # Collect actions unlocked by this account's capabilities.
    by_stage: dict[str, list[dict]] = {s: [] for s in registry.STAGES}
    for cap in caps:
        for stage, title, mode, desc in _CAPABILITY_ACTIONS.get(cap, []):
            by_stage[stage].append(
                {"title": title, "mode": mode, "description": desc, "capability": cap}
            )

    stages = []
    for stage in registry.STAGES:
        actions = by_stage[stage]
        if not actions:
            continue
        stages.append({
            "stage": stage,
            "label": STAGE_LABELS[stage],
            "actions": actions,
        })

    auto_count = sum(1 for s in stages for a in s["actions"] if a["mode"] == "auto")
    assist_count = sum(1 for s in stages for a in s["actions"] if a["mode"] == "assist")

    return {
        "provider": provider_key,
        "provider_name": prov.get("name"),
        "icon": prov.get("icon"),
        "goal": goal or (prov.get("goals", ["leads"])[0]),
        "stages": stages,
        "auto_actions": auto_count,
        "assist_actions": assist_count,
        "summary": _summarize(prov.get("name"), stages, auto_count, assist_count),
    }


def _summarize(name, stages, auto_count, assist_count) -> str:
    covered = ", ".join(s["stage"] for s in stages) or "no"
    return (f"{name}: {auto_count} automated + {assist_count} one-click actions across "
            f"the {covered} stages of your funnel.")


def overview(connections: list) -> dict:
    """Aggregate funnel coverage across all of a user's connections.

    `connections` is an iterable of objects/dicts with `provider` and `goal`.
    """
    stage_cov = {s: 0 for s in registry.STAGES}
    plans = []
    for c in connections:
        pk = c.provider if hasattr(c, "provider") else c.get("provider")
        goal = c.goal if hasattr(c, "goal") else c.get("goal")
        plan = build_plan(pk, goal)
        plans.append(plan)
        for s in plan["stages"]:
            stage_cov[s["stage"]] += 1
    gaps = [s for s, n in stage_cov.items() if n == 0]
    return {
        "connected": len(plans),
        "stage_coverage": stage_cov,
        "gaps": gaps,
        "plans": plans,
    }
