"""Staff authentication: `Authorization: Bearer <STAFF_TOKEN>` (spec §5, §9.17)."""

import secrets

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer = HTTPBearer(auto_error=False)


def require_staff(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),  # noqa: B008
) -> None:
    """Missing or wrong token → 401 (single role, so never 403)."""
    expected = request.app.state.settings.staff_token.get_secret_value()
    if credentials is None or not secrets.compare_digest(
        credentials.credentials.encode(), expected.encode()
    ):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid staff token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
