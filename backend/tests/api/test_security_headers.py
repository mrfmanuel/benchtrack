"""Security headers on real responses (every status and route kind), and the public rate
limit not being bypassable with a forged X-Forwarded-For."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.db import Base, create_db_engine
from app.main import create_app
from app.routers import health
from app.security_headers import API_CSP, COMMON_HEADERS, DOCS_CSP, HSTS, SPA_CSP
from tests.api.conftest import STAFF_TOKEN, FakeClock, assert_error


def assert_common(response) -> None:
    for name, value in COMMON_HEADERS.items():
        assert response.headers.get_list(name) == [value], name


# --- Every kind of API response carries the headers ----------------------------------


@pytest.mark.parametrize(
    ("method", "path", "kwargs", "status"),
    [
        ("GET", "/api/health", {}, 200),
        ("GET", "/api/tickets", {}, 401),
        ("GET", "/api/nope", {}, 404),
        ("DELETE", "/api/customers", {"headers": {"Authorization": f"Bearer {STAFF_TOKEN}"}}, 405),
        (
            "POST",
            "/api/customers",
            {"headers": {"Authorization": f"Bearer {STAFF_TOKEN}"}, "json": {}},
            422,
        ),
        ("GET", "/api/public/track/BT-ZZZZZ", {}, 404),
    ],
)
def test_api_responses_have_security_headers_and_no_store(anon, method, path, kwargs, status):
    response = anon.request(method, path, **kwargs)
    assert response.status_code == status
    assert_common(response)
    assert response.headers["content-security-policy"] == API_CSP
    assert response.headers["cache-control"] == "no-store"
    assert "strict-transport-security" not in response.headers  # plain HTTP


def test_authenticated_staff_data_is_not_cacheable(client):
    response = client.get("/api/customers")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"


def test_rate_limited_response_has_headers(anon):
    for _ in range(10):
        anon.get("/api/public/track/BT-ZZZZZ")
    response = anon.get("/api/public/track/BT-ZZZZZ")
    assert_error(response, 429, "rate_limited")
    assert_common(response)
    assert response.headers["cache-control"] == "no-store"
    assert "retry-after" in response.headers


def test_unhandled_error_500_still_has_headers(app, monkeypatch):
    def boom(_engine):
        raise RuntimeError("fictional failure")

    monkeypatch.setattr(health, "check_database", boom)
    with TestClient(app, raise_server_exceptions=False) as anon:
        response = anon.get("/api/health")
    assert_error(response, 500, "internal_error")
    assert_common(response)
    assert response.headers["content-security-policy"] == API_CSP
    assert response.headers["cache-control"] == "no-store"


def test_contract_file_is_cacheable(anon):
    response = anon.get("/api/openapi.yaml")
    assert response.status_code == 200
    assert_common(response)
    assert response.headers["content-security-policy"] == API_CSP
    assert "cache-control" not in response.headers


def test_docs_page_gets_the_swagger_policy(anon):
    response = anon.get("/docs")
    assert response.status_code == 200
    assert_common(response)
    assert response.headers["content-security-policy"] == DOCS_CSP
    assert "cache-control" not in response.headers


# --- HSTS ----------------------------------------------------------------------------


def test_hsts_over_https(app):
    with TestClient(app, base_url="https://testserver") as https:
        assert https.get("/api/health").headers["strict-transport-security"] == HSTS


def test_hsts_behind_a_tls_terminating_proxy(anon):
    response = anon.get("/api/health", headers={"X-Forwarded-Proto": "https"})
    assert response.headers["strict-transport-security"] == HSTS


def test_no_hsts_over_plain_http(anon):
    assert "strict-transport-security" not in anon.get("/api/health").headers


# --- SPA responses -------------------------------------------------------------------


@pytest.fixture
def web(tmp_path: Path) -> Iterator[TestClient]:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><div id=root></div>", encoding="utf-8")
    (dist / "assets" / "index-abc.js").write_text("1", encoding="utf-8")
    engine = create_db_engine("sqlite://", poolclass=StaticPool)
    settings = Settings(
        _env_file=None, staff_token=STAFF_TOKEN, database_url="sqlite://", frontend_dist=dist
    )
    with TestClient(create_app(settings, engine=engine)) as client:
        yield client
    engine.dispose()


@pytest.mark.parametrize("path", ["/", "/track/BT-DEM22", "/assets/index-abc.js"])
def test_spa_responses_get_the_spa_policy(web, path):
    response = web.get(path)
    assert response.status_code == 200
    assert_common(response)
    assert response.headers["content-security-policy"] == SPA_CSP
    assert response.headers["cache-control"] != "no-store"


def test_missing_asset_404_gets_the_spa_policy(web):
    response = web.get("/assets/missing.js")
    assert response.status_code == 404
    assert response.headers["content-security-policy"] == SPA_CSP


# --- Rate limit vs. forged client addresses ------------------------------------------


def make_client(**overrides) -> TestClient:
    engine = create_db_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    settings = Settings(
        _env_file=None, staff_token=STAFF_TOKEN, database_url="sqlite://", **overrides
    )
    return TestClient(create_app(settings, engine=engine, clock=FakeClock()))


def test_forged_x_forwarded_for_does_not_reset_the_rate_limit():
    """App level: the key never comes from X-Forwarded-For. The original bug was in the
    uvicorn flags (--forwarded-allow-ips='*' took the forged leftmost entry), which
    TestClient does not run; the CI docker job repeats this against the real container."""
    with make_client() as anon:
        statuses = [
            anon.get(
                "/api/public/track/BT-ZZZZZ", headers={"X-Forwarded-For": f"198.51.100.{i}"}
            ).status_code
            for i in range(11)
        ]
    assert statuses == [404] * 10 + [429]


def test_forged_x_forwarded_for_is_ignored_when_an_edge_header_is_trusted():
    with make_client(client_ip_header="CF-Connecting-IP") as anon:
        headers = {"CF-Connecting-IP": "203.0.113.9"}
        statuses = [
            anon.get(
                "/api/public/track/BT-ZZZZZ",
                headers=headers | {"X-Forwarded-For": f"198.51.100.{i}"},
            ).status_code
            for i in range(11)
        ]
    assert statuses == [404] * 10 + [429]


def test_edge_header_gives_each_real_client_its_own_limit():
    with make_client(client_ip_header="CF-Connecting-IP") as anon:
        for _ in range(10):
            anon.get("/api/public/track/BT-ZZZZZ", headers={"CF-Connecting-IP": "203.0.113.9"})
        blocked = anon.get(
            "/api/public/track/BT-ZZZZZ", headers={"CF-Connecting-IP": "203.0.113.9"}
        )
        other = anon.get("/api/public/track/BT-ZZZZZ", headers={"CF-Connecting-IP": "203.0.113.10"})
    assert blocked.status_code == 429
    assert other.status_code == 404


def test_render_without_client_ip_header_logs_a_warning(log_stream):
    engine = create_db_engine("sqlite://", poolclass=StaticPool)
    settings = Settings(
        _env_file=None,
        staff_token=STAFF_TOKEN,
        database_url="sqlite://",
        log_format="json",
        render_git_commit="3f1c2e9a7b6d",
    )
    create_app(settings, engine=engine, log_stream=log_stream)
    assert "CLIENT_IP_HEADER" in log_stream.getvalue()
