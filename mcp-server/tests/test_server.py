"""BenchTrack MCP server against a mocked API (httpx.MockTransport), through the real MCP
protocol (in-process mcp.Client)."""

import json
import logging
from typing import Any

import httpx
import pytest
from mcp import Client

from benchtrack_mcp.api import REDACTED, BenchTrackAPI
from benchtrack_mcp.server import TOOL_NAMES, api_from_env, build_server

TOKEN = "fictional-mcp-test-token-0123456789"
BASE = "http://bench.test"

DASHBOARD = {
    "counts": {
        "received": 1,
        "diagnosing": 0,
        "waiting_parts": 2,
        "repairing": 0,
        "ready": 1,
        "delivered": 3,
        "cancelled": 0,
    },
    "stale_tickets": [{"id": 7, "tracking_code": "BT-DEM24", "status": "waiting_parts"}],
}
TICKET = {"id": 7, "tracking_code": "BT-DEM24", "status": "waiting_parts"}
PUBLIC = {"tracking_code": "BT-DEM22", "status": "received", "timeline": []}


class FakeAPI:
    """Records every request; answers like the real API."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        staff = path != "/api/health" and not path.startswith("/api/public/")
        if staff and request.headers.get("authorization") != f"Bearer {TOKEN}":
            return httpx.Response(
                401, json={"error": {"code": "unauthorized", "message": "Missing token."}}
            )
        if path == "/api/health":
            return httpx.Response(200, json={"status": "ok", "database": "ok", "version": "abc"})
        if path == "/api/dashboard":
            return httpx.Response(200, json=DASHBOARD)
        if path == "/api/tickets":
            return httpx.Response(
                200, json={"items": [TICKET], "total": 1, "limit": 20, "offset": 0}
            )
        if path == "/api/tickets/7":
            return httpx.Response(200, json=TICKET)
        if path == "/api/tickets/404":
            return httpx.Response(
                404, json={"error": {"code": "not_found", "message": "Ticket not found."}}
            )
        if path == "/api/public/track/BT-DEM22":
            return httpx.Response(200, json=PUBLIC)
        return httpx.Response(404, json={"error": {"code": "not_found", "message": "Not Found"}})


@pytest.fixture
def fake() -> FakeAPI:
    return FakeAPI()


def make_api(fake: FakeAPI, token: str | None = TOKEN, **kwargs: Any) -> BenchTrackAPI:
    return BenchTrackAPI(BASE, token, transport=httpx.MockTransport(fake), **kwargs)


async def call(api: BenchTrackAPI, tool: str, args: dict[str, Any] | None = None):
    async with Client(build_server(api)) as client:
        return await client.call_tool(tool, args or {})


def payload(result) -> Any:
    assert not result.is_error, result.content
    if result.structured_content is not None:
        return result.structured_content
    return json.loads(result.content[0].text)


def error_text(result) -> str:
    assert result.is_error
    return " ".join(getattr(c, "text", "") for c in result.content)


# --- Tool surface: exactly five read-only tools ---------------------------------------


async def test_exactly_the_read_only_tools_are_exposed(fake):
    async with Client(build_server(make_api(fake))) as client:
        tools = (await client.list_tools()).tools
    assert sorted(t.name for t in tools) == sorted(TOOL_NAMES)
    for tool in tools:
        assert tool.annotations.read_only_hint is True, tool.name
        assert tool.annotations.destructive_hint is False, tool.name


async def test_every_tool_sends_get_only(fake):
    api = make_api(fake)
    for tool, args in [
        ("health", {}),
        ("dashboard", {}),
        ("list_tickets", {"status": "ready", "q": "lenovo"}),
        ("get_ticket", {"id": 7}),
        ("track", {"code": "BT-DEM22"}),
    ]:
        payload(await call(api, tool, args))
    assert fake.requests and {r.method for r in fake.requests} == {"GET"}


# --- Results --------------------------------------------------------------------------


async def test_dashboard(fake):
    assert payload(await call(make_api(fake), "dashboard")) == DASHBOARD


async def test_list_tickets_passes_filters_and_drops_empty_ones(fake):
    api = make_api(fake)
    payload(await call(api, "list_tickets", {"status": "waiting_parts", "q": "BT-DEM", "limit": 5}))
    payload(await call(api, "list_tickets", {"q": ""}))
    first, second = fake.requests
    assert dict(first.url.params) == {
        "status": "waiting_parts",
        "q": "BT-DEM",
        "limit": "5",
        "offset": "0",
    }
    assert dict(second.url.params) == {"limit": "20", "offset": "0"}


async def test_list_tickets_rejects_unknown_status(fake):
    result = await call(make_api(fake), "list_tickets", {"status": "lost"})
    assert result.is_error
    assert fake.requests == []


@pytest.mark.parametrize("bad", [{"limit": 0}, {"limit": 101}, {"offset": -1}])
async def test_list_tickets_validates_paging(fake, bad):
    assert (await call(make_api(fake), "list_tickets", bad)).is_error
    assert fake.requests == []


async def test_get_ticket(fake):
    assert payload(await call(make_api(fake), "get_ticket", {"id": 7})) == TICKET


async def test_get_ticket_404_is_a_readable_tool_error(fake):
    text = error_text(await call(make_api(fake), "get_ticket", {"id": 404}))
    assert "HTTP 404 not_found: Ticket not found." in text


async def test_track_is_public_and_url_encodes_the_code(fake):
    api = make_api(fake)
    assert payload(await call(api, "track", {"code": " BT-DEM22 "})) == PUBLIC
    payload_err = await call(api, "track", {"code": "../tickets/7"})
    assert payload_err.is_error
    assert fake.requests[0].headers.get("authorization") is None
    assert fake.requests[1].url.raw_path == b"/api/public/track/..%2Ftickets%2F7"


async def test_public_tools_work_without_a_token(fake):
    api = make_api(fake, token=None)
    assert payload(await call(api, "health"))["status"] == "ok"
    assert payload(await call(api, "track", {"code": "BT-DEM22"})) == PUBLIC


async def test_staff_tools_without_a_token_fail_before_any_request(fake):
    text = error_text(await call(make_api(fake, token=None), "dashboard"))
    assert "BENCHTRACK_TOKEN is not set" in text
    assert fake.requests == []


async def test_wrong_token_surfaces_the_401(fake):
    text = error_text(await call(make_api(fake, token="wrong-token-0000000000"), "dashboard"))
    assert "HTTP 401 unauthorized" in text


# --- The token never leaks --------------------------------------------------------------


async def test_token_is_never_in_results_errors_or_logs(fake, caplog):
    caplog.set_level(logging.DEBUG)
    api = make_api(fake)
    outputs = [
        await call(api, "dashboard"),
        await call(api, "get_ticket", {"id": 404}),
        await call(api, "list_tickets", {"status": "nope"}),
    ]
    blob = json.dumps([o.model_dump(mode="json") for o in outputs]) + caplog.text + repr(api)
    assert TOKEN not in blob
    staff = [r for r in fake.requests if r.url.path == "/api/dashboard"]
    assert staff[0].headers["authorization"] == f"Bearer {TOKEN}"
    assert TOKEN not in str(staff[0].url)


async def test_token_is_scrubbed_if_the_api_echoes_it():
    def echo(request: httpx.Request) -> httpx.Response:
        auth = request.headers["authorization"]
        return httpx.Response(400, json={"error": {"code": "bad", "message": f"got {auth}"}})

    api = BenchTrackAPI(BASE, TOKEN, transport=httpx.MockTransport(echo))
    text = error_text(await call(api, "dashboard"))
    assert TOKEN not in text
    assert REDACTED in text


# --- Timeouts and transport errors --------------------------------------------------------


async def test_timeout_becomes_a_tool_error(fake):
    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    api = BenchTrackAPI(BASE, TOKEN, timeout=2, transport=httpx.MockTransport(slow))
    assert "did not answer within 2 s" in error_text(await call(api, "dashboard"))


async def test_connection_error_becomes_a_tool_error():
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    api = BenchTrackAPI(BASE, TOKEN, transport=httpx.MockTransport(down))
    text = error_text(await call(api, "health"))
    assert "Cannot reach the BenchTrack API at http://bench.test" in text


def test_every_call_has_a_timeout():
    api = BenchTrackAPI(BASE, TOKEN)
    assert api.timeout == 10.0
    with pytest.raises(ValueError):
        BenchTrackAPI(BASE, TOKEN, timeout=0)


# --- Configuration -------------------------------------------------------------------------


def test_config_from_env():
    api = api_from_env(
        {
            "BENCHTRACK_URL": "http://127.0.0.1:8010/",
            "BENCHTRACK_TOKEN": TOKEN,
            "BENCHTRACK_TIMEOUT": "3",
        }
    )
    assert api.base_url == "http://127.0.0.1:8010"
    assert api.timeout == 3.0
    assert TOKEN not in repr(api)


def test_config_defaults_to_local_and_no_token():
    api = api_from_env({})
    assert api.base_url == "http://127.0.0.1:8000"
    assert "token=unset" in repr(api)


@pytest.mark.parametrize(
    "url", ["127.0.0.1:8000", "ftp://bench.test", "http://user:pass@bench.test", "http://"]
)
def test_bad_urls_are_rejected(url):
    with pytest.raises(ValueError):
        BenchTrackAPI(url, TOKEN)
