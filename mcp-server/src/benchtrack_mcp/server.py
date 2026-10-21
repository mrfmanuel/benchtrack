"""MCP server exposing read-only BenchTrack tools to coding agents.

Five tools, all GET-only and annotated `readOnlyHint`: health, dashboard, list_tickets,
get_ticket, track. There are deliberately no write tools (create, update, status change,
notes): changing shop data stays a human action in the BenchTrack UI.
"""

import logging
import os
from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from benchtrack_mcp.api import DEFAULT_TIMEOUT_SECONDS, BenchTrackAPI, BenchTrackError

DEFAULT_URL = "http://127.0.0.1:8000"
TOOL_NAMES = ("health", "dashboard", "list_tickets", "get_ticket", "track")

TicketStatus = Literal[
    "received", "diagnosing", "waiting_parts", "repairing", "ready", "delivered", "cancelled"
]
READ_ONLY = ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
)


def build_server(api: BenchTrackAPI) -> MCPServer:
    server = MCPServer(
        "benchtrack",
        instructions=(
            "Read-only access to the BenchTrack repair-ticket API (fictional demo data in "
            "development). Use it to inspect tickets and dashboards while working on the code. "
            "It cannot change data."
        ),
    )

    async def call(coro: Any) -> Any:
        try:
            return await coro
        except BenchTrackError as exc:
            raise ToolError(str(exc)) from None

    @server.tool(annotations=READ_ONLY)
    async def health() -> dict[str, Any]:
        """API and database health, plus the deployed version (commit SHA). No token needed."""
        return await call(api.health())

    @server.tool(annotations=READ_ONLY)
    async def dashboard() -> dict[str, Any]:
        """Ticket counts per status and the stale tickets (open, no update for 7+ days)."""
        return await call(api.dashboard())

    @server.tool(annotations=READ_ONLY)
    async def list_tickets(
        status: TicketStatus | None = None,
        q: Annotated[
            str | None,
            Field(
                description="Case-insensitive search in tracking code, customer name, brand, model."
            ),
        ] = None,
        limit: Annotated[int, Field(ge=1, le=100)] = 20,
        offset: Annotated[int, Field(ge=0)] = 0,
    ) -> dict[str, Any]:
        """List tickets, newest first, optionally filtered by status and search text."""
        return await call(api.list_tickets(status=status, q=q, limit=limit, offset=offset))

    @server.tool(annotations=READ_ONLY)
    async def get_ticket(id: Annotated[int, Field(ge=1)]) -> dict[str, Any]:  # noqa: A002
        """One ticket with its customer summary, by numeric id."""
        return await call(api.get_ticket(id))

    @server.tool(annotations=READ_ONLY)
    async def track(
        code: Annotated[str, Field(min_length=1, max_length=32, description="e.g. BT-7K3QX")],
    ) -> dict[str, Any]:
        """What a customer sees on the public tracking page (no PII, no notes). No token."""
        return await call(api.track(code))

    return server


def api_from_env(environ: dict[str, str] | None = None) -> BenchTrackAPI:
    env = os.environ if environ is None else environ
    timeout = float(env.get("BENCHTRACK_TIMEOUT") or DEFAULT_TIMEOUT_SECONDS)
    return BenchTrackAPI(
        env.get("BENCHTRACK_URL") or DEFAULT_URL, env.get("BENCHTRACK_TOKEN"), timeout=timeout
    )


def main() -> None:
    # stdout carries the MCP protocol: log to stderr only, and keep httpx quiet (it would log
    # every request URL at INFO).
    logging.basicConfig(level=logging.WARNING, format="benchtrack-mcp %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    build_server(api_from_env()).run("stdio")
