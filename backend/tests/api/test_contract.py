"""Contract parity: the app implements exactly the operations in openapi.yaml."""

from collections.abc import Iterator
from functools import cache
from pathlib import Path
from typing import Any

import yaml
from fastapi.routing import APIRoute, iter_route_contexts

OPENAPI_PATH = Path(__file__).resolve().parents[3] / "openapi.yaml"
HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}

# Documentation routes are deliberately outside the contract: they serve the contract
# itself (/api/openapi.yaml) and a Swagger UI page that renders it (/docs).
DOC_ROUTES = {("GET", "/api/openapi.yaml"), ("GET", "/docs")}


@cache
def load_contract() -> dict[str, Any]:
    return yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))


def contract_operations() -> Iterator[tuple[str, str, dict[str, Any]]]:
    for path, item in load_contract()["paths"].items():
        for method, operation in item.items():
            if method in HTTP_METHODS:
                yield method.upper(), path, operation


def app_operations(app) -> dict[tuple[str, str], APIRoute]:
    """(METHOD, full path) → route. FastAPI ≥ 0.156 nests included routers, so walk them."""
    return {
        (method, ctx.path): ctx.original_route
        for ctx in iter_route_contexts(app.routes)
        if isinstance(ctx.original_route, APIRoute)
        for method in ctx.methods or ()
    }


def test_every_contract_operation_exists_in_the_app_and_vice_versa(app):
    contract = {(method, path) for method, path, _ in contract_operations()}
    implemented = set(app_operations(app)) - DOC_ROUTES
    assert set(app_operations(app)) >= DOC_ROUTES
    assert contract - implemented == set(), "in openapi.yaml but not implemented"
    assert implemented - contract == set(), "implemented but not in openapi.yaml"


def test_operation_ids_match(app):
    routes = app_operations(app)
    for method, path, operation in contract_operations():
        assert routes[(method, path)].operation_id == operation["operationId"], (method, path)


def test_success_status_codes_match(app):
    routes = app_operations(app)
    for method, path, operation in contract_operations():
        success = [int(code) for code in operation["responses"] if code.startswith("2")]
        assert success == [routes[(method, path)].status_code or 200], (method, path)


def test_public_schema_matches_whitelist_model():
    from app.schemas import PublicTimelineEntry, PublicTracking

    schemas = load_contract()["components"]["schemas"]
    assert set(schemas["PublicTracking"]["properties"]) == set(PublicTracking.model_fields)
    assert set(schemas["PublicTimelineEntry"]["properties"]) == set(
        PublicTimelineEntry.model_fields
    )
