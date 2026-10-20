"""Documentation routes: the contract file and Swagger UI (both unauthenticated)."""

import re

import yaml

from app.routers import docs
from tests.api.conftest import assert_error
from tests.api.test_contract import OPENAPI_PATH


def test_contract_is_served_verbatim_without_token(anon):
    response = anon.get("/api/openapi.yaml")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/yaml; charset=utf-8"
    assert response.content == OPENAPI_PATH.read_bytes()
    assert yaml.safe_load(response.text)["openapi"] == "3.1.0"


def test_missing_contract_file_returns_404_envelope(anon, monkeypatch, tmp_path):
    monkeypatch.setattr(docs, "CONTRACT_PATH", tmp_path / "missing.yaml")
    assert_error(anon.get("/api/openapi.yaml"), 404, "not_found")


def test_swagger_ui_loads_the_contract_from_a_pinned_cdn(anon):
    response = anon.get("/docs")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/html; charset=utf-8"
    html = response.text
    assert 'url: "/api/openapi.yaml"' in html
    cdn_urls = re.findall(r'(?:href|src)="(https://[^"]+)"', html)
    assert len(cdn_urls) == 2
    assert all(f"swagger-ui-dist@{docs.SWAGGER_UI_VERSION}/" in url for url in cdn_urls)
    assert re.fullmatch(r"\d+\.\d+\.\d+", docs.SWAGGER_UI_VERSION)  # pinned, not "latest"
    assert html.count('integrity="sha384-') == 2


def test_docs_routes_ignore_rate_limit_and_auth(anon):
    for _ in range(15):
        assert anon.get("/api/openapi.yaml").status_code == 200
