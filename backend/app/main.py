"""FastAPI application entrypoint."""
import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import (
    accounts,
    activation,
    agents,
    approvals,
    bridge,
    analytics,
    auth,
    book,
    calls,
    compliance,
    connections,
    control,
    conversations,
    cron,
    decisions,
    grants,
    knowledge,
    mission,
    voice,
    executive,
    export,
    graph,
    imports,
    instagram,
    jobs,
    automations,
    browser,
    campaigns,
    clients,
    content,
    crm,
    deliverability,
    finance,
    leads,
    memory,
    messages,
    newsletters,
    social,
    music,
    opportunities,
    outreach_queue,
    planning,
    profile,
    reports,
    resend_webhook,
    restaurants,
    setup,
    sms,
    webhooks,
)
from .config import settings
from .scheduler import shutdown_scheduler, start_scheduler
from .seed import seed

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bruno")


def _post_boot() -> None:
    """ALL boot work — schema+seed, connected creds, self-check, scheduler — kept off
    the request-serving path so the port opens immediately and Cloud Run's startup
    probe passes. A synchronous seed()/Cloud SQL connect at startup blocked the port
    and timed the probe out ('container failed to become healthy'), taking the whole
    service down. None of this needs to finish before /health answers, and endpoints
    that need the schema/creds tolerate the brief warm-up (or call apply_to_settings
    themselves)."""
    try:
        seed()  # create schema + seed admin/agents/objectives
    except Exception:
        log.exception("Startup seed() failed — check DATABASE_URL / Cloud SQL connection")
    try:
        from .database import SessionLocal
        from . import client_goal, runtime_config, selfcheck
        _db = SessionLocal()
        try:
            runtime_config.apply_to_settings(_db)  # load any in-app-connected creds
            client_goal.apply_overrides(_db)        # restore autoscaled outreach volume
            selfcheck.run(_db)  # verify core features + auto-correct safe issues on boot
        finally:
            _db.close()
    except Exception:
        log.exception("Background runtime-config / self-check failed")
    try:
        start_scheduler()
    except Exception:
        log.exception("Scheduler failed to start")
    log.info("Bruno AI Workforce background boot complete.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Open the port with ZERO synchronous DB work so Cloud Run's startup probe passes
    # fast and the deploy becomes healthy even when Cloud SQL is slow — a synchronous
    # seed() here previously blocked the port and timed the probe out (deploy failed,
    # backend down). All boot work now runs in the background.
    if settings.enable_scheduler:
        threading.Thread(target=_post_boot, name="post-boot", daemon=True).start()
        log.info("Bruno AI Workforce backend started (serving; background boot running).")
    else:
        # Tests / local without the scheduler: run synchronously so seeded state
        # (schema, objectives, knowledge base, applied creds) is deterministic before use.
        _post_boot()
        log.info("Bruno AI Workforce backend started.")
    yield
    shutdown_scheduler()


app = FastAPI(title="Bruno AI Workforce", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(agents.router)
app.include_router(jobs.router)
app.include_router(leads.router)
app.include_router(restaurants.router)
app.include_router(music.router)
app.include_router(instagram.router)
app.include_router(reports.router)
app.include_router(messages.router)
app.include_router(outreach_queue.router)
app.include_router(sms.router)
app.include_router(calls.router)
app.include_router(cron.router)
app.include_router(export.router)
app.include_router(imports.router)
app.include_router(connections.router)
app.include_router(profile.router)
app.include_router(analytics.router)
app.include_router(executive.router)
app.include_router(memory.router)
app.include_router(crm.router)
app.include_router(accounts.router)
app.include_router(graph.router)
app.include_router(opportunities.router)
app.include_router(planning.router)
app.include_router(decisions.router)
app.include_router(activation.router)
app.include_router(newsletters.router)
app.include_router(bridge.router)
app.include_router(browser.router)
app.include_router(social.router)
app.include_router(finance.router)
app.include_router(content.router)
app.include_router(control.router)
app.include_router(compliance.router)
app.include_router(approvals.router)
app.include_router(mission.router)
app.include_router(knowledge.router)
app.include_router(grants.router)
app.include_router(voice.router)
app.include_router(setup.router)
app.include_router(clients.router)
app.include_router(automations.router)
app.include_router(campaigns.router)
app.include_router(deliverability.router)
app.include_router(book.router)
app.include_router(conversations.router)
app.include_router(webhooks.router)
app.include_router(resend_webhook.router)


@app.get("/health", tags=["system"])
def health():
    return {"status": "ok", "service": "bruno-ai-workforce"}


@app.get("/version", tags=["system"])
def version():
    """Which build is actually live. BUILD_SHA is set to the deploying commit's
    short SHA by cloudbuild.backend.yaml, so you can confirm at a glance whether a
    merge has really reached production (answers 'why don't I see my changes?')."""
    import os
    return {
        "service": "bruno-ai-workforce",
        "app_version": app.version,
        "sha": os.environ.get("BUILD_SHA", "dev"),
    }


@app.get("/health/db", tags=["system"])
def health_db():
    """Reports whether the database is reachable, with the error if not."""
    from sqlalchemy import text

    from .database import engine

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"db": "ok"}
    except Exception as exc:  # surface the real connection error
        return {"db": "error", "detail": str(exc)[:600]}
