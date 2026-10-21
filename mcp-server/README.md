# BenchTrack MCP server

A small, **read-only** [Model Context Protocol](https://modelcontextprotocol.io) server that lets a coding agent (Claude Code) look at BenchTrack data while it works on the code: is the API healthy and which commit is deployed, what does the dashboard show, what does a ticket or a public tracking page look like.

Built with the official Python SDK (`mcp` 2.x, `MCPServer`) and `httpx`, managed with uv. It speaks stdio.

## Tools

| Tool | API call | Token | Returns |
|---|---|---|---|
| `health` | `GET /api/health` | no | `status`, `database`, deployed `version` |
| `dashboard` | `GET /api/dashboard` | yes | counts per status, stale tickets |
| `list_tickets(status?, q?, limit=20, offset=0)` | `GET /api/tickets` | yes | a page of tickets (newest first); `status` is one of the 7 statuses, `q` searches code, customer name, brand, model |
| `get_ticket(id)` | `GET /api/tickets/{id}` | yes | one ticket with its customer summary |
| `track(code)` | `GET /api/public/track/{code}` | no | the public tracking view (no PII, no notes) |

All tools are annotated `readOnlyHint: true`, `destructiveHint: false`. **There are no write tools**: creating tickets, changing status or adding notes stays a human action in the BenchTrack UI. The client only ever sends `GET`, and a test asserts it.

## Configuration (environment)

| Variable | Default | Notes |
|---|---|---|
| `BENCHTRACK_URL` | `http://127.0.0.1:8000` | Base URL of the API (local Compose, or production) |
| `BENCHTRACK_TOKEN` | unset | The staff bearer token. Needed for `dashboard`, `list_tickets`, `get_ticket`; `health` and `track` work without it |
| `BENCHTRACK_TIMEOUT` | `10` | Seconds per call (connect timeout ≤ 5 s). Every call has a timeout |

**Token handling:** the token is read from the environment at startup, sent only in the `Authorization` header of staff calls, and never logged, returned, put in a URL or included in error messages; an API echo of it is scrubbed to `[REDACTED]`. Logs go to stderr only (stdout carries the protocol), and httpx request logging is turned down. Note that the staff token can also write through the API, so the read-only guarantee comes from this server's code, not from the credential. See [`docs/permissions.md`](../docs/permissions.md).

## Use it from Claude Code

The repo's [`.mcp.json`](../.mcp.json) registers the server with environment expansion, never literal values:

```json
"benchtrack": {
  "command": "uv",
  "args": ["run", "--directory", "mcp-server", "--frozen", "--quiet", "benchtrack-mcp"],
  "env": { "BENCHTRACK_URL": "${BENCHTRACK_URL:-http://127.0.0.1:8000}", "BENCHTRACK_TOKEN": "${BENCHTRACK_TOKEN:-}" }
}
```

Set the variables in the shell that starts Claude Code (never in a committed file, never pasted into a chat):

```powershell
$env:BENCHTRACK_URL = "http://127.0.0.1:8000"
$env:BENCHTRACK_TOKEN = "<your local staff token>"   # typed by you, not by the agent
claude
```

Claude Code asks once to approve the project's MCP server, then the tools appear as `mcp__benchtrack__dashboard` and so on. The [`benchtrack-dev` plugin](../plugins/benchtrack-dev/) bundles the same server.

## Development

```bash
cd mcp-server
uv sync
uv run pytest -q          # mocked API (httpx.MockTransport) through the real MCP protocol
uv run ruff check . && uv run ruff format --check .
uv run benchtrack-mcp     # run over stdio (normally Claude Code starts it)
```

The tests cover exactly five read-only tools, GET-only requests, filters and validation, the 401/404 error envelopes as tool errors, timeouts and connection errors, and that the token never appears in results, errors, logs or `repr`.
