"""Domain errors and the single error envelope (spec §9.19)."""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response

from app.responses import UTF8JSONResponse as JSONResponse
from app.services.tracking_codes import TrackingCodeGenerationError
from app.services.transitions import InvalidTransitionError

logger = logging.getLogger(__name__)

_HTTP_CODES = {
    401: "unauthorized",
    404: "not_found",
    405: "method_not_allowed",
    429: "rate_limited",
}


class AppError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, details: Any = None, headers: dict[str, str] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details
        self.headers = headers


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class TicketFinalError(AppError):
    status_code = 409
    code = "ticket_final"


class FieldValidationError(AppError):
    """A semantic validation failure on one field (e.g. unknown `customer_id`)."""

    status_code = 422
    code = "validation_error"

    def __init__(self, field: str, message: str):
        super().__init__("Request validation failed.", [{"field": field, "message": message}])


class RateLimitedError(AppError):
    status_code = 429
    code = "rate_limited"

    def __init__(self, retry_after: int):
        super().__init__(
            f"Too many requests. Try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: Any = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        body["details"] = details
    return JSONResponse({"error": body}, status_code=status_code, headers=headers)


def _validation_details(exc: RequestValidationError) -> list[dict[str, str]]:
    details = []
    for err in exc.errors():
        loc = [str(part) for part in err.get("loc", ())]
        # Drop the source ("body", "query", "path") unless it is all there is.
        field = ".".join(loc[1:]) if len(loc) > 1 else (loc[0] if loc else "request")
        message = str(err.get("msg", "Invalid value.")).removeprefix("Value error, ")
        details.append({"field": field, "message": message})
    return details


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_request: Request, exc: AppError) -> JSONResponse:
        return error_response(exc.status_code, exc.code, exc.message, exc.details, exc.headers)

    @app.exception_handler(InvalidTransitionError)
    async def _invalid_transition(_request: Request, exc: InvalidTransitionError) -> JSONResponse:
        details = {
            "from_status": exc.from_status.value,
            "to_status": exc.to_status.value,
            "allowed": sorted(s.value for s in exc.allowed),
        }
        return error_response(409, "invalid_transition", str(exc), details)

    @app.exception_handler(TrackingCodeGenerationError)
    async def _code_generation(_request: Request, exc: TrackingCodeGenerationError) -> JSONResponse:
        logger.error("Tracking code generation failed: %s", exc)
        return error_response(
            500,
            "tracking_code_generation_failed",
            "Could not generate a unique tracking code. Please retry.",
        )

    @app.exception_handler(RequestValidationError)
    async def _request_validation(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(
            422, "validation_error", "Request validation failed.", _validation_details(exc)
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception(request: Request, exc: StarletteHTTPException) -> Response:
        spa = getattr(request.app.state, "spa", None)
        if exc.status_code == 404 and spa is not None and spa.accepts(request):
            return spa.response_for(request)  # client-side route (see app/spa.py)
        code = _HTTP_CODES.get(exc.status_code, "http_error")
        message = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return error_response(exc.status_code, code, message, headers=exc.headers)

    @app.exception_handler(Exception)
    async def _unhandled(_request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error")
        return error_response(500, "internal_error", "Internal server error.")
