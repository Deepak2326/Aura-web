"""Seed the initial admin user.

Runs automatically on startup when the admin table is empty, or manually via:
    python -m app.seed_admin
Credentials come from ADMIN_DEFAULT_EMAIL / ADMIN_DEFAULT_PASSWORD.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import sessionmaker

from . import crud
from .config import Settings, get_settings
from .database import create_db_engine, create_session_factory
from .models import AdminUser

logger = logging.getLogger("aura.seed")


def seed_admin(session_factory: sessionmaker, settings: Settings) -> None:
    db = session_factory()
    try:
        if db.query(AdminUser).count() == 0:
            crud.create_admin(
                db,
                email=settings.admin_default_email,
                password=settings.admin_default_password,
                role="admin",
            )
            logger.warning(
                "Seeded initial admin user '%s'. Change the default password before going to production!",
                settings.admin_default_email,
            )
    finally:
        db.close()


def main() -> None:
    settings = get_settings()
    engine = create_db_engine(settings.database_url)
    seed_admin(create_session_factory(engine), settings)
    print(f"Admin user ensured: {settings.admin_default_email}")


if __name__ == "__main__":
    main()
