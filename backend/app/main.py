"""FastAPI application factory.

Usage:
    uvicorn app.main:app --reload            # development
    uvicorn app.main:app --host 0.0.0.0      # production (behind TLS proxy)
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings, get_settings
from .crm.base import NullCRMClient
from .crm.factory import build_crm_client
from .database import Base, create_db_engine, create_session_factory
from .rate_limit import SlidingWindowRateLimiter
from .routers import admin, auth, leads
from .seed_admin import seed_admin

logger = logging.getLogger("aura")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    engine = create_db_engine(settings.database_url)
    session_factory = create_session_factory(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if settings.db_auto_create:
            Base.metadata.create_all(engine)  # dev convenience; use Alembic in prod
        seed_admin(session_factory, settings)
        logger.info("CRM provider: %s", app.state.crm_client.name)
        yield

    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.submit_limiter = SlidingWindowRateLimiter(
        settings.rate_limit_submit_max, settings.rate_limit_submit_window
    )
    app.state.login_limiter = SlidingWindowRateLimiter(
        settings.rate_limit_login_max, settings.rate_limit_login_window
    )

    try:
        app.state.crm_client = build_crm_client(settings)
    except Exception as exc:  # misconfigured CRM must not take the site down
        logger.error("CRM client misconfigured (%s). Falling back to provider 'none'.", exc)
        app.state.crm_client = NullCRMClient()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(leads.router)
    app.include_router(auth.router)
    app.include_router(admin.router)

    @app.get("/api/health", tags=["meta"])
    def health() -> dict:
        return {"status": "ok", "service": settings.app_name, "environment": settings.environment}

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
