"""Serve the built frontend (`frontend/dist`) from the API process.

Enabled only when `FRONTEND_DIST` is set (the Docker image sets it); in local development
the Vite dev server serves the SPA instead.

The SPA is a fallback, not a route: API routing is untouched, and only a request that would
otherwise be a 404 is answered with a file from `dist/` or with `index.html`, so client routes
such as `/track/BT-7K3QX` and `/tickets/1` work on reload. `/api/*` and `/assets/*` never fall
back: an unknown API path keeps the JSON error envelope, and a missing asset stays a 404.
"""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
from starlette.types import Scope

ASSETS_PREFIX = "/assets"
_NO_FALLBACK_PREFIXES = ("/api", ASSETS_PREFIX)
# index.html must be revalidated so a deploy is picked up; hashed assets never change.
INDEX_CACHE_CONTROL = "no-cache"
ASSET_CACHE_CONTROL = "public, max-age=31536000, immutable"


class ImmutableStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = ASSET_CACHE_CONTROL
        return response


class SPA:
    def __init__(self, dist: Path) -> None:
        self.dist = dist.resolve()
        self.index = self.dist / "index.html"
        if not self.index.is_file():
            raise RuntimeError(f"FRONTEND_DIST has no index.html: {self.dist}")

    def accepts(self, request: Request) -> bool:
        path = request.url.path
        return request.method in ("GET", "HEAD") and not any(
            path == prefix or path.startswith(prefix + "/") for prefix in _NO_FALLBACK_PREFIXES
        )

    def response_for(self, request: Request) -> Response:
        """A top-level file such as `/favicon.svg`, otherwise `index.html`."""
        candidate = (self.dist / request.url.path.lstrip("/")).resolve()
        if candidate != self.dist and candidate.is_relative_to(self.dist) and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(self.index, headers={"Cache-Control": INDEX_CACHE_CONTROL})


def mount_spa(app: FastAPI, dist: Path) -> SPA:
    spa = SPA(dist)
    assets = spa.dist / "assets"
    if assets.is_dir():
        app.mount(ASSETS_PREFIX, ImmutableStaticFiles(directory=assets), name="assets")
    app.state.spa = spa
    return spa
