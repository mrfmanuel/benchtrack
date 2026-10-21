"""Serving the built SPA (FRONTEND_DIST): client routes fall back to index.html, the API
keeps its JSON error envelope."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.db import Base, create_db_engine
from app.main import create_app
from app.spa import ASSET_CACHE_CONTROL, INDEX_CACHE_CONTROL
from tests.api.conftest import STAFF_TOKEN, assert_error

INDEX_HTML = '<!doctype html><html><body><div id="root"></div></body></html>'


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    root = tmp_path / "dist"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    (root / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    (root / "assets" / "index-abc123.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("outside dist", encoding="utf-8")
    return root


def make_settings(**overrides) -> Settings:
    return Settings(_env_file=None, staff_token=STAFF_TOKEN, database_url="sqlite://", **overrides)


@pytest.fixture
def web(dist: Path) -> Iterator[TestClient]:
    engine = create_db_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with TestClient(create_app(make_settings(frontend_dist=dist), engine=engine)) as client:
        yield client
    engine.dispose()


@pytest.mark.parametrize(
    "path", ["/", "/track", "/track/BT-DEM22", "/tickets/1", "/tickets/1/receipt", "/sign-in"]
)
def test_client_routes_get_index_html(web, path):
    response = web.get(path)
    assert response.status_code == 200
    assert response.text == INDEX_HTML
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["cache-control"] == INDEX_CACHE_CONTROL


def test_hashed_assets_are_served_and_cached(web):
    response = web.get("/assets/index-abc123.js")
    assert response.status_code == 200
    assert response.text == "console.log(1)"
    assert response.headers["cache-control"] == ASSET_CACHE_CONTROL


def test_top_level_public_files_are_served(web):
    response = web.get("/favicon.svg")
    assert response.status_code == 200
    assert response.text == "<svg/>"


def test_missing_asset_is_a_404_not_index_html(web):
    response = web.get("/assets/missing.js")
    assert response.status_code == 404
    assert "root" not in response.text


@pytest.mark.parametrize("path", ["/api/nope", "/api", "/api/tickets/1/nope"])
def test_unknown_api_paths_keep_the_json_envelope(web, path):
    assert_error(web.get(path), 404, "not_found")


def test_api_and_docs_routes_still_win(web):
    assert web.get("/api/health").json() == {"status": "ok", "database": "ok"}
    assert_error(web.get("/api/tickets"), 401, "unauthorized")
    assert_error(web.delete("/api/customers"), 405, "method_not_allowed")
    assert "swagger-ui" in web.get("/docs").text


def test_non_get_requests_do_not_fall_back(web):
    assert_error(web.post("/track/BT-DEM22"), 404, "not_found")


@pytest.mark.parametrize(
    "path", ["/../secret.txt", "/%2e%2e/secret.txt", "/assets/../../secret.txt"]
)
def test_files_outside_dist_are_never_served(web, path):
    assert "outside dist" not in web.get(path).text


def test_spa_is_off_by_default(anon):
    """Development and the API tests: no FRONTEND_DIST, unknown paths stay JSON 404s."""
    assert_error(anon.get("/track/BT-DEM22"), 404, "not_found")


def test_frontend_dist_without_index_html_fails_at_startup(tmp_path):
    with pytest.raises(RuntimeError, match="index.html"):
        create_app(make_settings(frontend_dist=tmp_path), engine=create_db_engine("sqlite://"))


def test_frontend_dist_is_read_from_the_environment(monkeypatch, dist):
    monkeypatch.setenv("FRONTEND_DIST", str(dist))
    assert Settings(_env_file=None, staff_token=STAFF_TOKEN).frontend_dist == dist
