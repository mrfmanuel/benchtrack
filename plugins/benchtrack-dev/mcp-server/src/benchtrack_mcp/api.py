"""Read-only HTTP client for the BenchTrack API.

Only GET is ever sent. The bearer token goes in the Authorization header of staff calls and
nowhere else: it is never logged, never put in a URL, and scrubbed from every error message.
"""

import json
from typing import Any
from urllib.parse import quote, urlsplit

import httpx

DEFAULT_TIMEOUT_SECONDS = 10.0
CONNECT_TIMEOUT_SECONDS = 5.0
REDACTED = "[REDACTED]"


class BenchTrackError(Exception):
    """A failed API call, with a message that is safe to show to the agent."""


class BenchTrackAPI:
    def __init__(
        self,
        base_url: str,
        token: str | None,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        parts = urlsplit(base_url)
        if parts.scheme not in ("http", "https") or not parts.netloc:
            raise ValueError("BENCHTRACK_URL must be an absolute http(s) URL.")
        if parts.username or parts.password:
            raise ValueError("BENCHTRACK_URL must not contain credentials.")
        if timeout <= 0:
            raise ValueError("The timeout must be positive.")
        self.base_url = base_url.rstrip("/")
        self._token = token.strip() if token and token.strip() else None
        self.timeout = timeout
        self._transport = transport

    def __repr__(self) -> str:  # never show the token, even in debug output
        return (
            f"BenchTrackAPI(base_url={self.base_url!r}, token={'set' if self._token else 'unset'})"
        )

    def _scrub(self, text: str) -> str:
        return text.replace(self._token, REDACTED) if self._token else text

    async def get(
        self, path: str, *, params: dict[str, Any] | None = None, auth: bool = True
    ) -> Any:
        headers = {"Accept": "application/json"}
        if auth:
            if not self._token:
                raise BenchTrackError(
                    "BENCHTRACK_TOKEN is not set; staff tools need the staff token."
                )
            headers["Authorization"] = f"Bearer {self._token}"
        query = {k: v for k, v in (params or {}).items() if v is not None and v != ""}
        timeout = httpx.Timeout(self.timeout, connect=min(CONNECT_TIMEOUT_SECONDS, self.timeout))
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url, timeout=timeout, transport=self._transport
            ) as client:
                response = await client.get(path, params=query, headers=headers)
        except httpx.TimeoutException:
            raise BenchTrackError(
                f"The BenchTrack API did not answer within {self.timeout:g} s."
            ) from None
        except httpx.HTTPError as exc:
            raise BenchTrackError(
                self._scrub(f"Cannot reach the BenchTrack API at {self.base_url}: {exc}")
            ) from None
        return self._parse(response)

    def _parse(self, response: httpx.Response) -> Any:
        try:
            body = response.json()
        except (json.JSONDecodeError, UnicodeDecodeError):
            body = None
        if response.is_success:
            if body is None:
                raise BenchTrackError(f"Unexpected non-JSON response ({response.status_code}).")
            return body
        error = body.get("error") if isinstance(body, dict) else None
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            detail = f"{error.get('code', 'error')}: {error['message']}"
            if error.get("details") is not None:
                detail += f" (details: {json.dumps(error['details'], ensure_ascii=False)})"
        else:
            detail = "request failed"
        raise BenchTrackError(self._scrub(f"HTTP {response.status_code} {detail}"))

    # --- Endpoints (all GET) --------------------------------------------------------------

    async def health(self) -> Any:
        return await self.get("/api/health", auth=False)

    async def dashboard(self) -> Any:
        return await self.get("/api/dashboard")

    async def list_tickets(
        self, *, status: str | None, q: str | None, limit: int, offset: int
    ) -> Any:
        return await self.get(
            "/api/tickets", params={"status": status, "q": q, "limit": limit, "offset": offset}
        )

    async def get_ticket(self, ticket_id: int) -> Any:
        return await self.get(f"/api/tickets/{int(ticket_id)}")

    async def track(self, code: str) -> Any:
        return await self.get(f"/api/public/track/{quote(code.strip(), safe='')}", auth=False)
