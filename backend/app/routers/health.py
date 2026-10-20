from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.db import check_database

router = APIRouter(prefix="/api", tags=["Health"])


@router.get("/health", operation_id="getHealth")
def get_health(request: Request) -> JSONResponse:
    if check_database(request.app.state.engine):
        return JSONResponse({"status": "ok", "database": "ok"})
    return JSONResponse({"status": "degraded", "database": "error"}, status_code=503)
