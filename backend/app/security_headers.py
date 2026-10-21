"""Security headers on every response (pure ASGI middleware, no response buffering).

Three Content-Security-Policies, by path:

- `/api/*`: JSON/YAML only, so nothing may load (`default-src 'none'`).
- `/docs`: Swagger UI. Only the two pinned CDN files (exact URLs, not the whole
  jsdelivr host, which serves any npm package) plus the hash of the one inline script.
- everything else: the SPA, which is built without inline scripts or styles, so
  `'self'` is enough.

`Cache-Control: no-store` on `/api/*` keeps tickets, customers and tracking results out of
browser and proxy caches; the contract file is exempt (public, versioned with the code).

HSTS is sent only on HTTPS: the request scheme, or `X-Forwarded-Proto: https` from the
platform proxy (uvicorn runs without proxy-header rewriting, see docker/entrypoint.sh).
A spoofed `X-Forwarded-Proto` over plain HTTP is harmless: browsers ignore HSTS on HTTP.
"""

import base64
import hashlib

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.routers.docs import SWAGGER_CSS_URL, SWAGGER_INIT_SCRIPT, SWAGGER_JS_URL

CONTRACT_PATH = "/api/openapi.yaml"
DOCS_PATH = "/docs"


def csp_hash(script: str) -> str:
    digest = hashlib.sha256(script.encode("utf-8")).digest()
    return f"'sha256-{base64.b64encode(digest).decode('ascii')}'"


def _policy(*directives: str) -> str:
    return "; ".join(directives)


_LOCKDOWN = ("object-src 'none'", "base-uri 'none'", "frame-ancestors 'none'")

API_CSP = _policy("default-src 'none'", "frame-ancestors 'none'")
SPA_CSP = _policy(
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self'",
    "img-src 'self'",
    "font-src 'self'",
    "connect-src 'self'",
    "form-action 'self'",
    *_LOCKDOWN,
)
DOCS_CSP = _policy(
    "default-src 'none'",
    f"script-src {SWAGGER_JS_URL} {csp_hash(SWAGGER_INIT_SCRIPT)}",
    f"style-src {SWAGGER_CSS_URL}",
    "img-src 'self' data:",  # swagger-ui.css embeds its icons as data: URIs
    "connect-src 'self'",  # fetches /api/openapi.yaml and "Try it out" calls
    "form-action 'none'",
    *_LOCKDOWN,
)

COMMON_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": (
        "accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), "
        "microphone=(), payment=(), usb=()"
    ),
}
HSTS = "max-age=31536000; includeSubDomains"
API_CACHE_CONTROL = "no-store"


def _is_api(path: str) -> bool:
    return path == "/api" or path.startswith("/api/")


def content_security_policy(path: str) -> str:
    if _is_api(path):
        return API_CSP
    if path == DOCS_PATH:
        return DOCS_CSP
    return SPA_CSP


def is_https(scope: Scope) -> bool:
    if scope.get("scheme") == "https":
        return True
    # The proxy closest to us appends last; earlier entries come from the client.
    forwarded = Headers(scope=scope).get("x-forwarded-proto", "")
    return forwarded.rsplit(",", 1)[-1].strip().lower() == "https"


def security_headers(scope: Scope) -> dict[str, str]:
    """All headers for a response to this request (also used by the 500 handler)."""
    path = scope.get("path", "")
    headers = {**COMMON_HEADERS, "Content-Security-Policy": content_security_policy(path)}
    if is_https(scope):
        headers["Strict-Transport-Security"] = HSTS
    if _is_api(path) and path != CONTRACT_PATH:
        headers["Cache-Control"] = API_CACHE_CONTROL
    return headers


class ForwardedProtoMiddleware:
    """Restore the request scheme behind a TLS-terminating proxy.

    Uvicorn runs with --no-proxy-headers (it would also take the client IP from the forgeable
    X-Forwarded-For), so without this the app sees `http` on Render and absolute URLs it builds,
    such as FastAPI's trailing-slash redirect, would downgrade to `http://`. Only the scheme is
    taken from the header. Forging it can only make the server believe it is on HTTPS: absolute
    URLs and HSTS for the forger's own plain-HTTP request, which browsers ignore.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        plain = scope["type"] in ("http", "websocket") and scope.get("scheme") in ("http", "ws")
        if plain and is_https(scope):
            scope = {**scope, "scheme": "https" if scope["type"] == "http" else "wss"}
        await self.app(scope, receive, send)


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        extra = security_headers(scope)

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in extra.items():
                    headers[name] = value  # replace, never duplicate
            await send(message)

        await self.app(scope, receive, send_with_headers)
