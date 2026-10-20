"""API test fixtures: in-memory SQLite (StaticPool), fake clock, captured logs."""

import io
from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.db import Base, create_db_engine, utcnow
from app.main import create_app
from app.models import Ticket

STAFF_TOKEN = "fictional-staff-token-for-tests"
AUTH = {"Authorization": f"Bearer {STAFF_TOKEN}"}


class FakeClock:
    def __init__(self, start: float = 1_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def log_stream() -> io.StringIO:
    return io.StringIO()


@pytest.fixture
def app(clock: FakeClock, log_stream: io.StringIO) -> Iterator[FastAPI]:
    settings = Settings(
        _env_file=None,
        staff_token=STAFF_TOKEN,
        database_url="sqlite://",
        log_level="INFO",
        log_format="json",
    )
    # One shared connection, so every session sees the same in-memory database.
    engine = create_db_engine("sqlite://", poolclass=StaticPool)
    # Fast schema setup for in-memory tests; real databases use Alembic migrations.
    Base.metadata.create_all(engine)
    yield create_app(settings, engine=engine, clock=clock, log_stream=log_stream)
    engine.dispose()


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """Authenticated staff client."""
    with TestClient(app, headers=AUTH) as test_client:
        yield test_client


@pytest.fixture
def anon(app: FastAPI) -> Iterator[TestClient]:
    """Client without a token (public pages, auth checks)."""
    with TestClient(app) as test_client:
        yield test_client


# --- Helpers ------------------------------------------------------------------

_phone_counter = iter(range(10_000_000, 99_999_999))


def make_customer(client: TestClient, **overrides: Any) -> dict[str, Any]:
    body = {"name": "Ana Mora", "phone": f"+506{next(_phone_counter)}"} | overrides
    response = client.post("/api/customers", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def make_ticket(
    client: TestClient, customer_id: int | None = None, **overrides: Any
) -> dict[str, Any]:
    if customer_id is None:
        customer_id = make_customer(client)["id"]
    body = {
        "customer_id": customer_id,
        "device_type": "laptop",
        "brand": "Lenovo",
        "model": "ThinkPad T14",
        "reported_issue": "Does not turn on after a coffee spill.",
    } | overrides
    response = client.post("/api/tickets", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def move(client: TestClient, ticket_id: int, *statuses: str) -> dict[str, Any]:
    ticket: dict[str, Any] = {}
    for status in statuses:
        response = client.post(f"/api/tickets/{ticket_id}/status", json={"to_status": status})
        assert response.status_code == 200, response.text
        ticket = response.json()
    return ticket


def backdate(app: FastAPI, ticket_id: int, days: float) -> datetime:
    """Set a ticket's `updated_at` to `days` ago, directly in the database."""
    when = utcnow() - timedelta(days=days)
    with app.state.session_factory() as session:
        session.execute(update(Ticket).where(Ticket.id == ticket_id).values(updated_at=when))
        session.commit()
    return when


def assert_error(response: Any, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == code
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]
    return body["error"]
