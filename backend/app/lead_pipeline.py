"""Lead pipeline health — why aren't hot/warm leads showing up, and what to do.

Warm/hot leads are *earned* through a chain: source prospects → send outreach →
replies sync back and flip status to Replied/Interested. If any link is broken,
the funnel stays cold. This module inspects each link with the system's real
state and returns a plain-English diagnosis + the next action, so "I don't see
leads" becomes "connect Gmail" or "approve the drafts" — something actionable.
"""
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from .config import settings
from .integrations import apollo, gmail, places
from .lead_temperature import classify
from .models import Lead, Message


def _seg_counts(db: Session, segments: list[str]) -> dict:
    rows = db.query(Lead.status).filter(Lead.segment.in_(segments)).all()
    warm = sum(1 for (s,) in rows if classify(s) == "warm")
    hot = sum(1 for (s,) in rows if classify(s) == "hot")
    return {"total": len(rows), "warm": warm, "hot": hot}


def health(db: Session) -> dict:
    gmail_personal = gmail.is_configured(gmail.PERSONAL)
    gmail_insurance = gmail.is_configured(gmail.INSURANCE)
    any_gmail = gmail_personal or gmail_insurance
    # Replies sync whenever EITHER the in-process scheduler is on (default) OR an
    # external cron is wired (cron_secret). cron_secret alone was too strict — it
    # showed red even though the in-process scheduler was syncing.
    scheduler_on = bool(settings.enable_scheduler or settings.cron_secret)
    external_cron = bool(settings.cron_secret)

    sent_total = int(db.query(func.count()).select_from(Message).filter(
        Message.direction == "outbound", Message.status == "Sent").scalar() or 0)
    drafted = int(db.query(func.count()).select_from(Message).filter(
        Message.direction == "outbound", Message.status == "Drafted").scalar() or 0)
    replies_total = int(db.query(func.count()).select_from(Message).filter(
        Message.direction == "inbound").scalar() or 0)

    insurance = _seg_counts(db, ["commercial", "personal"])
    bnb = _seg_counts(db, ["consulting"])
    leads_total = insurance["total"] + bnb["total"]
    warm_total = insurance["warm"] + bnb["warm"]
    hot_total = insurance["hot"] + bnb["hot"]

    # ── The chain, link by link ──────────────────────────────────────────────
    sources = [
        {"name": "OpenStreetMap (free)", "ok": True,
         "detail": "Real local businesses with published emails — always on, no key."},
        {"name": "Google Places", "ok": places.is_configured(),
         "detail": "More businesses + contact data." if not places.is_configured()
                   else "Connected."},
        {"name": "Apollo", "ok": apollo.is_configured(),
         "detail": "High-volume B2B contacts + firmographics (best for BnB Global)."
                   if not apollo.is_configured() else "Connected."},
    ]

    steps = [
        {"key": "source", "label": "Source prospects", "ok": leads_total > 0,
         "detail": (f"{leads_total} leads sourced." if leads_total
                    else "No leads yet — run the agents or Work the pipeline.")},
        {"key": "send", "label": "Send outreach (Gmail connected)", "ok": any_gmail,
         "detail": ("Connected: " + ", ".join(
                        [m for m, c in (("personal", gmail_personal), ("insurance", gmail_insurance)) if c])
                    if any_gmail else
                    "No mailbox connected — nothing can send and no replies come back.")},
        {"key": "sent", "label": "Outreach actually going out", "ok": sent_total > 0,
         "detail": (f"{sent_total} sent." + (f" {drafted} waiting for approval." if drafted else "")
                    if sent_total else
                    (f"{drafted} drafted, waiting for your approval." if drafted
                     else "Nothing sent yet."))},
        {"key": "replies", "label": "Replies sync (warm/hot come from here)", "ok": scheduler_on,
         "detail": (("Auto-syncing" + ("" if external_cron else " (in-app scheduler; set CRON_SECRET "
                     "for scale-to-zero reliability)") + ". Use “Sync replies now” anytime.")
                    if scheduler_on else
                    "Replies aren't syncing — hit “Sync replies now”, or enable the scheduler so "
                    "leads warm up automatically.")},
    ]

    # ── The single most important next action ────────────────────────────────
    blockers: list[str] = []
    if not any_gmail:
        blockers.append("Connect a Gmail mailbox (Connections) — without it nothing sends "
                        "and no replies sync, so you'll never get warm or hot leads.")
    if leads_total == 0:
        blockers.append("Source your first leads — run the insurance and BnB Global agents "
                        "(or hit 'Work the pipeline').")
    if any_gmail and sent_total == 0 and drafted > 0:
        blockers.append(f"You have {drafted} drafted email(s) waiting — approve them in the "
                        "Approval Queue (or switch Jarvis to autopilot) so they actually send.")
    if any_gmail and not scheduler_on:
        blockers.append("Turn on the scheduler (ENABLE_SCHEDULER + CRON_SECRET) so replies "
                        "sync automatically — warm/hot leads are created when prospects reply.")
    if bnb["total"] == 0:
        blockers.append("No BnB Global leads yet: BnB sources worldwide — run the BnB Global "
                        "agent; add an Apollo key for high-volume, high-quality B2B contacts.")
    if not apollo.is_configured() and not places.is_configured():
        blockers.append("For more + higher-quality leads, add an Apollo or Google Places API "
                        "key (the free OpenStreetMap source alone is limited).")

    healthy = any_gmail and scheduler_on and leads_total > 0 and sent_total > 0
    return {
        "healthy": healthy,
        "summary": ("Pipeline is live — warm/hot leads will accrue as prospects reply."
                    if healthy else "Pipeline has gaps — see what to fix below."),
        "counts": {"leads": leads_total, "warm": warm_total, "hot": hot_total,
                   "sent": sent_total, "drafted": drafted, "replies": replies_total},
        "by_brand": {"insurance": insurance, "bnbglobal": bnb},
        "sources": sources,
        "steps": steps,
        "blockers": blockers,
    }
