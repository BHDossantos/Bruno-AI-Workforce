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
