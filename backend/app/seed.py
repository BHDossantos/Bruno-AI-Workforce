"""Idempotent bootstrap: create the admin user and register agents."""
from __future__ import annotations

import logging

from .agents import AGENTS
from .config import settings
from .database import SessionLocal, init_db
from .models import Agent, User
from .security import hash_password

log = logging.getLogger("bruno.seed")


def seed() -> None:
    init_db()
    db = SessionLocal()
    try:
        # Admin user
        if not db.query(User).filter(User.email == settings.admin_email).first():
            db.add(User(
                email=settings.admin_email,
                full_name="Bruno (Admin)",
                hashed_password=hash_password(settings.admin_password),
                role="admin",
            ))
            log.info("Created admin user %s", settings.admin_email)

        # Register agents
        for key, cls in AGENTS.items():
            if not db.query(Agent).filter(Agent.key == key).first():
                db.add(Agent(key=key, name=cls.name, description=cls.description,
                             schedule_cron=cls.schedule_cron))
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    seed()
