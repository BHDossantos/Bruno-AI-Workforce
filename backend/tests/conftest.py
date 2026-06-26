"""Pytest fixtures.

Sets safe defaults for required settings (so the app imports without a real
``.env``) and provides a ``client`` fixture that seeds the database and returns
an authenticated-capable TestClient. DB-backed tests are skipped automatically
when no PostgreSQL is reachable, so ``pytest`` still works offline.
"""
import os

import pytest

# Defaults must be set before the app/config is imported.
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("ENABLE_SCHEDULER", "false")
os.environ.setdefault("ADMIN_EMAIL", "admin@example.com")
os.environ.setdefault("ADMIN_PASSWORD", "testpass")
# Disable live lead sourcing (OpenStreetMap) during tests — no network calls.
os.environ["LEAD_CITIES"] = ""
os.environ["LEAD_STATES"] = ""
os.environ["ENABLE_FREE_JOBS"] = "false"
# Keep scoped (consulting/restaurant) sourcing offline in tests too.
os.environ["WIDER_LEAD_SOURCING"] = "false"
os.environ.setdefault(
    "DATABASE_URL",
    os.environ.get("DATABASE_URL", "postgresql+psycopg://bruno@localhost:5432/bruno_ai"),
)


def _db_available() -> bool:
    try:
        from sqlalchemy import text

        from app.database import engine

        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


requires_db = pytest.mark.skipif(not _db_available(), reason="PostgreSQL not reachable")


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:  # triggers lifespan: seed + (disabled) scheduler
        yield c


@pytest.fixture(scope="session")
def auth_headers(client):
    resp = client.post(
        "/auth/token",
        data={"username": os.environ["ADMIN_EMAIL"], "password": os.environ["ADMIN_PASSWORD"]},
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
