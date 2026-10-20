"""Shared FastAPI dependencies."""

from typing import Annotated

from fastapi import Depends, Query, Request
from sqlalchemy.orm import Session

from app.db import get_session
from app.errors import RateLimitedError

SessionDep = Annotated[Session, Depends(get_session)]
QueryParam = Annotated[
    str | None, Query(max_length=100, description="Case-insensitive substring search.")
]
LimitParam = Annotated[int, Query(ge=1, le=200)]
OffsetParam = Annotated[int, Query(ge=0)]


def public_rate_limit(request: Request) -> None:
    """10 requests/min per client IP on public routes (spec §9.14).

    The client IP comes from uvicorn, which honours X-Forwarded-For only when run with
    `--proxy-headers` behind a trusted proxy.
    """
    client_ip = request.client.host if request.client else "unknown"
    result = request.app.state.rate_limiter.hit(client_ip)
    if not result.allowed:
        raise RateLimitedError(result.retry_after)
