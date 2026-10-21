"""Shared FastAPI dependencies."""

from typing import Annotated

from fastapi import Depends, Query, Request
from sqlalchemy.orm import Session

from app.db import get_session
from app.errors import RateLimitedError
from app.services.client_ip import rate_limit_key

SessionDep = Annotated[Session, Depends(get_session)]
QueryParam = Annotated[
    str | None, Query(max_length=100, description="Case-insensitive substring search.")
]
LimitParam = Annotated[int, Query(ge=1, le=200)]
OffsetParam = Annotated[int, Query(ge=0)]


def public_rate_limit(request: Request) -> None:
    """10 requests/min per client on public routes (spec §9.14).

    The client is the TCP peer, or the edge-set `CLIENT_IP_HEADER` when configured; never
    `X-Forwarded-For`, which clients can forge (see app/services/client_ip.py).
    """
    key = rate_limit_key(
        request.client.host if request.client else None,
        request.headers,
        request.app.state.settings.client_ip_header,
    )
    result = request.app.state.rate_limiter.hit(key)
    if not result.allowed:
        raise RateLimitedError(result.retry_after)
