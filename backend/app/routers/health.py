from fastapi import APIRouter, Request

from app.db import check_database
from app.responses import UTF8JSONResponse as JSONResponse

router = APIRouter(prefix="/api", tags=["Health"])


@router.get("/health", operation_id="getHealth")
def get_health(request: Request) -> JSONResponse:
    if check_database(request.app.state.engine):
        return JSONResponse({"status": "ok", "database": "ok"})
    return JSONResponse({"status": "degraded", "database": "error"}, status_code=503)
