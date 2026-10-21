"""Auth on every staff route, error envelope and health (spec §5, §9.17, §9.19, §9.22)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.db import create_db_engine
from app.main import create_app
from app.routers import health
from tests.api.conftest import STAFF_TOKEN, assert_error
from tests.api.test_contract import contract_operations

STAFF_OPERATIONS = sorted(
    (method, path)
    for method, path, operation in contract_operations()
    if operation.get("security", [{"staffToken": []}]) != []
)


def _concrete(path: str) -> str:
    return path.replace("{customer_id}", "1").replace("{ticket_id}", "1")


def test_staff_operations_are_all_contract_operations_except_public_and_health():
    assert len(STAFF_OPERATIONS) == 12


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer wrong-token-of-enough-length"},
        {"Authorization": f"Bearer {STAFF_TOKEN}x"},
        {"Authorization": f"Basic {STAFF_TOKEN}"},
        {"Authorization": STAFF_TOKEN},
        {"Authorization": "Bearer "},
    ],
    ids=["missing", "wrong", "suffix", "basic-scheme", "no-scheme", "empty"],
)
@pytest.mark.parametrize(("method", "path"), STAFF_OPERATIONS, ids=lambda v: str(v))
def test_staff_routes_require_valid_token(anon, method, path, headers):
    response = anon.request(method, _concrete(path), headers=headers, json={})
    error = assert_error(response, 401, "unauthorized")
    assert error["message"] == "Missing or invalid staff token."
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_token_is_checked_before_body_validation(anon):
    response = anon.post("/api/customers", json={"bogus": True})
    assert_error(response, 401, "unauthorized")


def test_unknown_route_uses_error_envelope(client):
    assert_error(client.get("/api/nope"), 404, "not_found")


def test_wrong_method_uses_error_envelope(client):
    assert_error(client.delete("/api/customers"), 405, "method_not_allowed")


def test_fastapi_generated_docs_are_not_served(anon):
    for path in ("/redoc", "/openapi.json"):
        assert anon.get(path).status_code == 404


def test_health_ok(anon):
    response = anon.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok", "version": "dev"}


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"app_version": "3f1c2e9a7b6d", "render_git_commit": "a1b2c3d4"}, "3f1c2e9a7b6d"),
        ({"app_version": "  ", "render_git_commit": "a1b2c3d4"}, "a1b2c3d4"),
        ({"app_version": None, "render_git_commit": None}, "dev"),
    ],
)
def test_health_reports_the_configured_version(overrides, expected):
    settings = Settings(
        _env_file=None, staff_token=STAFF_TOKEN, database_url="sqlite://", **overrides
    )
    engine = create_db_engine("sqlite://", poolclass=StaticPool)
    with TestClient(create_app(settings, engine=engine)) as client:
        response = client.get("/api/health")
    engine.dispose()
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok", "version": expected}


def test_health_degraded_when_database_fails(anon, monkeypatch):
    monkeypatch.setattr(health, "check_database", lambda _engine: False)
    response = anon.get("/api/health")
    assert response.status_code == 503
    # §9.22 body, deliberately not the error envelope.
    assert response.json() == {"status": "degraded", "database": "error", "version": "dev"}
