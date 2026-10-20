"""API documentation: the hand-written contract and a Swagger UI page that renders it.

Both routes are unauthenticated and are not part of the contract itself.
"""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, Response

from app.errors import NotFoundError

# Repo root: backend/app/routers/docs.py → parents[3].
CONTRACT_PATH = Path(__file__).resolve().parents[3] / "openapi.yaml"

SWAGGER_UI_VERSION = "5.34.0"
_CDN = f"https://cdn.jsdelivr.net/npm/swagger-ui-dist@{SWAGGER_UI_VERSION}"
# Subresource Integrity hashes for the pinned files (sha384, base64).
_CSS_SRI = "sha384-4c3vsE5f+trhFyHrFrLM1fFGUn531NIaC7dcqEWIJdoRQJ5CkJbSuSCwXLpaS1KF"
_JS_SRI = "sha384-9Td7MKiIr2S83E1kZyyVi8KdJw/S8CpAvu0llLyMeg0xq/hDGiZJfVn0fV4llCmK"

SWAGGER_HTML = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>BenchTrack API</title>
  <link rel="stylesheet" href="{_CDN}/swagger-ui.css"
        integrity="{_CSS_SRI}" crossorigin="anonymous">
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="{_CDN}/swagger-ui-bundle.js"
          integrity="{_JS_SRI}" crossorigin="anonymous"></script>
  <script>
    window.ui = SwaggerUIBundle({{ url: "/api/openapi.yaml", dom_id: "#swagger-ui" }});
  </script>
</body>
</html>
"""

router = APIRouter(tags=["Docs"])


@router.get("/api/openapi.yaml", include_in_schema=False)
def get_contract() -> Response:
    if not CONTRACT_PATH.is_file():
        raise NotFoundError("API contract file is not available.")
    return Response(CONTRACT_PATH.read_bytes(), media_type="application/yaml; charset=utf-8")


@router.get("/docs", include_in_schema=False, response_class=HTMLResponse)
def swagger_ui() -> HTMLResponse:
    return HTMLResponse(SWAGGER_HTML)
