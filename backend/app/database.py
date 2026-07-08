"""Database engine, session factory and declarative base."""
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


def _normalize(url: str) -> str:
    """Coerce managed-Postgres URLs (Render/Supabase/Heroku) to the psycopg driver."""
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


engine = create_engine(_normalize(settings.database_url), pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Idempotent column additions for tables that predate a new feature.
# create_all() creates missing TABLES but never alters existing ones.
_MIGRATIONS = [
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS times_contacted INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS last_contacted_at TIMESTAMPTZ",
    "ALTER TABLE restaurants ADD COLUMN IF NOT EXISTS times_contacted INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE restaurants ADD COLUMN IF NOT EXISTS last_contacted_at TIMESTAMPTZ",
    "ALTER TABLE brand_profile ADD COLUMN IF NOT EXISTS music_links TEXT",
    # Client Book: which business a client belongs to (insurance/bnb/savorymind/…).
    "ALTER TABLE clients ADD COLUMN IF NOT EXISTS business VARCHAR NOT NULL DEFAULT 'insurance'",
    # Campaign Builder: tag sourced leads/restaurants with the launch that found them.
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS campaign_id VARCHAR",
    "CREATE INDEX IF NOT EXISTS ix_leads_campaign_id ON leads (campaign_id)",
    "ALTER TABLE restaurants ADD COLUMN IF NOT EXISTS campaign_id VARCHAR",
    "CREATE INDEX IF NOT EXISTS ix_restaurants_campaign_id ON restaurants (campaign_id)",
    # Lead profile: quote-intake answers tracked per lead (see lead_profile.py).
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS intake JSONB",
    # Multi-touch cadence: each follow-up step now carries a channel (email/sms/call).
    "ALTER TABLE follow_ups ADD COLUMN IF NOT EXISTS channel VARCHAR NOT NULL DEFAULT 'email'",
    # Real provider delivery outcome (Twilio) for texts/calls — did it actually land?
    "ALTER TABLE messages ADD COLUMN IF NOT EXISTS delivery_status VARCHAR",
    # Backfill streaming links onto an already-seeded profile — only when it still
    # holds the original Spotify-only seed, so user edits are never clobbered.
    ("UPDATE brand_profile SET music_links = "
     "'Spotify: https://open.spotify.com/artist/1NoggpCXnG7WctASlZU1UG\n"
     "Apple Music: https://music.apple.com/us/artist/bruno-d/1875998863\n"
     "YouTube Music: https://music.youtube.com/channel/UCCR-WCik-Gex9JojTRGS_hw' "
     "WHERE music_links IS NULL OR music_links = "
     "'Spotify: https://open.spotify.com/artist/1NoggpCXnG7WctASlZU1UG'"),
]


def init_db() -> None:
    """Create all tables from the SQLAlchemy models, then run light migrations."""
    from sqlalchemy import text

    from . import models  # noqa: F401  (ensure models are imported/registered)

    Base.metadata.create_all(bind=engine)
    # Add any new columns to pre-existing tables (Postgres supports IF NOT EXISTS).
    with engine.begin() as conn:
        for stmt in _MIGRATIONS:
            try:
                conn.execute(text(stmt))
            except Exception:  # pragma: no cover - non-Postgres or perms
                pass
