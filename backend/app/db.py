"""Engine, sessions and engine-specific settings. Models stay engine-agnostic."""

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

from fastapi import Request
from sqlalchemy import DateTime, Engine, create_engine, event, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.types import TypeDecorator


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator[datetime]):
    """Stores UTC; always returns timezone-aware UTC datetimes.

    SQLite has no timezone support and returns naive values, so values are stored as
    naive UTC everywhere and tagged as UTC on the way out.
    """

    impl = DateTime(timezone=False)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is not None:
            value = value.astimezone(UTC)
        return value.replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Any) -> datetime | None:
        return value.replace(tzinfo=UTC) if value is not None else None


def create_db_engine(url: str, **kwargs: Any) -> Engine:
    if url.startswith("sqlite"):
        # FastAPI may use a connection from a different thread than the one that opened it.
        kwargs.setdefault("connect_args", {"check_same_thread": False})
        engine = create_engine(url, **kwargs)

        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(dbapi_connection: Any, _record: Any) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        return engine
    kwargs.setdefault("pool_pre_ping", True)
    return create_engine(url, **kwargs)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def check_database(engine: Engine) -> bool:
    """Run `SELECT 1`; False if the database is unreachable."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return False
    return True


def get_session(request: Request) -> Iterator[Session]:
    """FastAPI dependency: one session per request."""
    with request.app.state.session_factory() as session:
        yield session
