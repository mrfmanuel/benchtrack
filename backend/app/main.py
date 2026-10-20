"""App factory. Run with `uv run uvicorn app.main:app --reload`."""

import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any, TextIO

from fastapi import FastAPI
from sqlalchemy import Engine

from app.config import Settings, get_settings
from app.db import Base, create_db_engine, make_session_factory
from app.errors import register_exception_handlers
from app.logging_config import configure_logging
from app.routers import customers, dashboard, health, public, tickets
from app.services.rate_limit import SlidingWindowRateLimiter

PUBLIC_RATE_LIMIT = 10
PUBLIC_RATE_WINDOW_SECONDS = 60.0


def create_app(
    settings: Settings | None = None,
    *,
    engine: Engine | None = None,
    clock: Callable[[], float] = time.monotonic,
    log_stream: TextIO | None = None,
) -> FastAPI:
    # Loading settings here makes a missing/short STAFF_TOKEN stop the server at startup.
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_format, stream=log_stream)
    engine = engine or create_db_engine(settings.database_url)
    Base.metadata.create_all(engine)  # replaced by Alembic migrations in Step 3

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        engine.dispose()

    # `openapi.yaml` is the contract; FastAPI's generated docs are not served.
    app = FastAPI(
        title="BenchTrack API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)
    app.state.rate_limiter = SlidingWindowRateLimiter(
        PUBLIC_RATE_LIMIT, PUBLIC_RATE_WINDOW_SECONDS, clock=clock
    )

    register_exception_handlers(app)
    for module in (health, customers, tickets, dashboard, public):
        app.include_router(module.router)
    return app


_app: FastAPI | None = None


def __getattr__(name: str) -> Any:
    """Build `app.main:app` on first access (PEP 562), so importing this module in tests
    does not read `.env` or create a database."""
    global _app
    if name == "app":
        if _app is None:
            _app = create_app()
        return _app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
