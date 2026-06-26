"""Go-live activation — turns the system's real state into a prioritized checklist
so the path from "built" to "operating daily" is obvious. Introspects keys,
connections, the scheduler, and whether data is actually flowing; returns what's
done, what's next, and a readiness score. Required items drive the score; optional
ones are surfaced but don't block.
"""
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from .ai import client
from .config import settings
from .integrations import gmail, jobs_api, spotify_api
from .models import ContentItem, Lead, ManualContact, Restaurant


def _count(db: Session, model, *filters) -> int:
    return int(db.query(func.count()).select_from(model).filter(*filters).scalar() or 0)


def build(db: Session) -> dict:
    from . import social
    conn = social.status(db)
    ig = bool((conn.get("instagram") or {}).get("connected"))
    fb = bool((conn.get("facebook") or {}).get("connected"))

    leads = _count(db, Lead)
    rests = _count(db, Restaurant, Restaurant.kind == "prospect")
    contacts = _count(db, ManualContact, ManualContact.kind == "contact")
    content = _count(db, ContentItem)

    items = [
        # key, label, required, done, detail, action
        ("ai", "Connect the AI brain (OpenAI key)", True, client.is_live(),
         "Powers content, outreach copy, and the board report." if not client.is_live()
         else "AI is live.", "/status"),
        ("email", "Connect email for outreach", True,
         gmail.is_configured(gmail.PERSONAL) or gmail.is_configured(gmail.INSURANCE),
         "Connect at least one Gmail so the agents can send.", "/connections"),
        ("scheduler", "Turn on the autopilot scheduler", True,
         bool(settings.enable_scheduler and settings.cron_secret),
         "Set ENABLE_SCHEDULER + CRON_SECRET so daily jobs run authenticated.", "/status"),
        ("leads", "Source the first leads", True, leads > 0,
         "Run the agents to source insurance/consulting leads." if leads == 0
         else f"{leads} leads in the system.", "/insurance"),
        ("content", "Produce the first content", True, content > 0,
         "Run the content factory / platform loops." if content == 0
         else f"{content} content pieces created.", "/factory"),
        ("social", "Connect Instagram + Facebook", True, ig and fb,
         "Connect IG + FB so marketing posts publish automatically.", "/connections"),
        # Optional — valuable but not blocking
        ("jobs", "Add JOBS_API_KEY (live job feeds)", False, jobs_api.is_configured(),
         "Enables live LinkedIn/Indeed/Glassdoor job pulls.", "/jobs"),
        ("spotify", "Connect Spotify (music analytics)", False, spotify_api.is_connected(db),
         "Shows live followers + top tracks on the Music page.", "/connections"),
        ("contacts", "Import your contacts (warm leads)", False, contacts > 0,
         "Import contacts so the warm-intro engine has people to reach.", "/import"),
        ("restaurants", "Source SavoryMind prospects", False, rests > 0,
         "Run the SavoryMind agent to source restaurants.", "/savorymind"),
    ]

    checklist = [{"key": k, "label": label, "required": req,
                  "status": "done" if done else ("todo" if req else "optional"),
                  "detail": detail, "action": action}
                 for (k, label, req, done, detail, action) in items]

    required = [c for c in checklist if c["required"]]
    done_required = sum(1 for c in required if c["status"] == "done")
    ready_pct = round(100 * done_required / len(required)) if required else 100
    next_step = next((c for c in checklist if c["status"] == "todo"), None)

    return {
        "ready_pct": ready_pct,
        "live": ready_pct == 100,
        "done": done_required,
        "required_total": len(required),
        "next_step": next_step,
        "checklist": checklist,
    }
