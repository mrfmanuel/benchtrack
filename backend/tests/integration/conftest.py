"""PostgreSQL integration fixtures.

Runs only with `uv run pytest -m integration` and a TEST_DATABASE_URL (env or .env) that
points to PostgreSQL. Every test starts from an empty `public` schema, so the database
name must end in `_test`; it is created if it does not exist.
"""

import io
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import Engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

from app.config import Settings, normalize_database_url
from app.db import create_db_engine
from app.main import create_app
from tests.alembic_helpers import upgrade
from tests.api.conftest import AUTH, STAFF_TOKEN, FakeClock


class IntegrationSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    test_database_url: str | None = None


def _test_database_url() -> str:
    raw = IntegrationSettings().test_database_url
    if not raw:
        pytest.skip(
            "Integration tests need PostgreSQL: set TEST_DATABASE_URL, e.g. "
            "postgresql+psycopg://benchtrack:benchtrack@127.0.0.1:5433/benchtrack_test "
            "(start it with `docker compose up -d db --wait`)."
        )
    url = normalize_database_url(raw)
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql":
        pytest.skip(f"TEST_DATABASE_URL must point to PostgreSQL, not {parsed.get_backend_name()}.")
    if not (parsed.database or "").endswith("_test"):
        pytest.fail(
            f"Refusing to run: integration tests wipe the database, and "
            f"'{parsed.database}' does not end in '_test'.",
            pytrace=False,
        )
    return url


def _ensure_database_exists(url: str) -> None:
    parsed = make_url(url)
    admin = create_db_engine(
        parsed.set(database="postgres").render_as_string(hide_password=False),
        poolclass=NullPool,
        isolation_level="AUTOCOMMIT",
    )
    with admin.connect() as connection:
        exists = connection.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": parsed.database}
        )
        if not exists:
            connection.execute(text(f'CREATE DATABASE "{parsed.database}"'))
    admin.dispose()


@pytest.fixture(scope="session")
def database_url() -> str:
    url = _test_database_url()
    _ensure_database_exists(url)
    return url


@pytest.fixture
def engine(database_url: str) -> Iterator[Engine]:
    """Engine on an empty `public` schema (no tables, no alembic_version)."""
    engine = create_db_engine(database_url, poolclass=NullPool)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    yield engine
    engine.dispose()


@pytest.fixture
def migrated_engine(engine: Engine, database_url: str) -> Engine:
    upgrade(database_url)
    return engine


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def app(migrated_engine: Engine, database_url: str, clock: FakeClock) -> FastAPI:
    settings = Settings(_env_file=None, staff_token=STAFF_TOKEN, database_url=database_url)
    return create_app(settings, engine=migrated_engine, clock=clock, log_stream=io.StringIO())


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, headers=AUTH) as test_client:
        yield test_client


@pytest.fixture
def anon(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
