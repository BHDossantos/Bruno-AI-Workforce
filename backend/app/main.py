"""FastAPI application entrypoint."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import (
    agents,
    auth,
    connections,
    cron,
    export,
    imports,
    instagram,
    jobs,
    leads,
    messages,
    music,
    outreach_queue,
    reports,
    restaurants,
    sms,
)
from .scheduler import shutdown_scheduler, start_scheduler
from .seed import seed

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bruno")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Don't let a DB/seed hiccup crash startup — the container must listen on
    # $PORT for Cloud Run. Errors are logged so they're visible in the logs.
    try:
        seed()
    except Exception:
        log.exception("Startup seed() failed — check DATABASE_URL / Cloud SQL connection")
    try:
        start_scheduler()
    except Exception:
        log.exception("Scheduler failed to start")
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
app.include_router(cron.router)
app.include_router(export.router)
app.include_router(imports.router)
app.include_router(connections.router)


@app.get("/health", tags=["system"])
def health():
    return {"status": "ok", "service": "bruno-ai-workforce"}


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
