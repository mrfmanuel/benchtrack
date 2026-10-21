"""Security header policies (no HTTP): CSP per path, inline-script hash, HTTPS detection."""

import asyncio
import re

import pytest

from app.routers import docs
from app.security_headers import (
    API_CSP,
    DOCS_CSP,
    HSTS,
    SPA_CSP,
    ForwardedProtoMiddleware,
    content_security_policy,
    csp_hash,
    is_https,
    security_headers,
)


def directives(policy: str) -> dict[str, list[str]]:
    parsed = {}
    for part in policy.split(";"):
        name, *values = part.split()
        assert name not in parsed, f"duplicate directive {name}"
        parsed[name] = values
    return parsed


def test_csp_hash_matches_the_mdn_reference_example():
    # https://developer.mozilla.org/docs/Web/HTTP/Headers/Content-Security-Policy/script-src
    assert csp_hash("alert('Hello, world.');") == (
        "'sha256-qznLcsROx4GACP2dm0UCKCzCG+HiZ1guq6ZZDob/Tng='"
    )


@pytest.mark.parametrize(
    ("path", "policy"),
    [
        ("/api/health", API_CSP),
        ("/api", API_CSP),
        ("/api/openapi.yaml", API_CSP),
        ("/docs", DOCS_CSP),
        ("/docs/", SPA_CSP),  # not the Swagger page: SPA fallback
        ("/", SPA_CSP),
        ("/track/BT-7K3QX", SPA_CSP),
        ("/apix", SPA_CSP),
    ],
)
def test_policy_by_path(path, policy):
    assert content_security_policy(path) == policy


@pytest.mark.parametrize("policy", [API_CSP, SPA_CSP, DOCS_CSP])
def test_no_policy_allows_unsafe_sources_or_framing(policy):
    assert "unsafe-inline" not in policy
    assert "unsafe-eval" not in policy
    assert "*" not in policy
    assert directives(policy)["frame-ancestors"] == ["'none'"]


def test_api_policy_loads_nothing():
    assert directives(API_CSP)["default-src"] == ["'none'"]


def test_spa_policy_is_same_origin_only():
    d = directives(SPA_CSP)
    for name in ("default-src", "script-src", "style-src", "img-src", "connect-src"):
        assert d[name] == ["'self'"], name
    assert d["object-src"] == ["'none'"]
    assert d["base-uri"] == ["'none'"]


def test_docs_policy_allows_exactly_the_pinned_files_and_the_inline_script():
    d = directives(DOCS_CSP)
    assert d["default-src"] == ["'none'"]
    assert d["script-src"] == [docs.SWAGGER_JS_URL, csp_hash(docs.SWAGGER_INIT_SCRIPT)]
    assert d["style-src"] == [docs.SWAGGER_CSS_URL]
    # Full file URLs, never the bare host: cdn.jsdelivr.net serves any npm package.
    for source in d["script-src"] + d["style-src"]:
        assert source.startswith("'sha256-") or source.endswith((".js", ".css")), source
        assert f"@{docs.SWAGGER_UI_VERSION}/" in source or source.startswith("'sha256-")


def test_docs_hash_covers_the_inline_script_actually_served():
    inline = re.findall(r"<script>(.*?)</script>", docs.SWAGGER_HTML, flags=re.S)
    assert inline == [docs.SWAGGER_INIT_SCRIPT]
    assert csp_hash(inline[0]) in DOCS_CSP


def test_swagger_does_not_call_the_external_validator():
    assert "validatorUrl: null" in docs.SWAGGER_INIT_SCRIPT


def scope(path="/", scheme="http", headers=()):
    return {
        "type": "http",
        "path": path,
        "scheme": scheme,
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers],
    }


@pytest.mark.parametrize(
    ("scheme", "forwarded", "expected"),
    [
        ("http", None, False),
        ("https", None, True),
        ("http", "https", True),
        ("http", "HTTPS", True),
        ("http", "http", False),
        ("http", "https, http", False),  # the nearest proxy (rightmost) saw plain HTTP
        ("http", "http, https", True),
    ],
)
def test_https_detection(scheme, forwarded, expected):
    headers = [("X-Forwarded-Proto", forwarded)] if forwarded else []
    assert is_https(scope(scheme=scheme, headers=headers)) is expected


def test_hsts_only_over_https():
    assert "Strict-Transport-Security" not in security_headers(scope())
    assert security_headers(scope(scheme="https"))["Strict-Transport-Security"] == HSTS


@pytest.mark.parametrize(
    ("path", "no_store"),
    [
        ("/api/health", True),
        ("/api/tickets/1", True),
        ("/api/public/track/BT-7K3QX", True),
        ("/api/openapi.yaml", False),
        ("/docs", False),
        ("/", False),
    ],
)
def test_no_store_on_api_except_the_contract(path, no_store):
    assert (security_headers(scope(path)).get("Cache-Control") == "no-store") is no_store


@pytest.mark.parametrize(
    ("type_", "scheme", "forwarded", "expected"),
    [
        ("http", "http", "https", "https"),
        ("http", "http", None, "http"),
        ("http", "http", "https, http", "http"),
        ("http", "https", None, "https"),
        ("websocket", "ws", "https", "wss"),
    ],
)
def test_forwarded_proto_middleware_sets_the_scheme(type_, scheme, forwarded, expected):
    seen = {}

    async def app(inner_scope, _receive, _send):
        seen.update(inner_scope)

    headers = [("X-Forwarded-Proto", forwarded)] if forwarded else []
    s = scope(scheme=scheme, headers=headers) | {"type": type_}
    asyncio.run(ForwardedProtoMiddleware(app)(s, None, None))
    assert seen["scheme"] == expected
