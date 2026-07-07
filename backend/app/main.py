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
    connections,
    control,
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
    """Slower, network-touching boot work — run in a background thread so it never
    delays the port from opening. Cloud Run marks the revision healthy once the app
    is listening; doing OAuth token refresh (inside selfcheck) or a slow Cloud SQL
    read here synchronously intermittently blew past the startup-probe window and
    failed the deploy. None of this needs to finish before /health can answer, and
    endpoints that need connected creds already call apply_to_settings themselves."""
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
    # Do the MINIMUM before serving so Cloud Run's startup health check passes fast
    # and deploys stop flaking: create the schema, then hand the slow/network boot
    # work to a background thread. Don't let a DB/seed hiccup crash startup — the
    # container must listen on $PORT. Errors are logged so they're visible.
    try:
        seed()
    except Exception:
        log.exception("Startup seed() failed — check DATABASE_URL / Cloud SQL connection")
    if settings.enable_scheduler:
        # Production (Cloud Run): defer slow boot work so the port opens immediately
        # and the deploy's startup probe passes without flaking.
        threading.Thread(target=_post_boot, name="post-boot", daemon=True).start()
        log.info("Bruno AI Workforce backend started (serving; background boot running).")
    else:
        # Tests / local without the scheduler: run synchronously so seeded state
        # (objectives, knowledge base, applied creds) is deterministic before use.
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
app.include_router(webhooks.router)


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
