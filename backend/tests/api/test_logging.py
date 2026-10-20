"""Tracking codes never reach the logs (spec §9.16)."""

import json
import logging

from tests.api.conftest import make_ticket


def _lines(log_stream) -> list[dict]:
    return [json.loads(line) for line in log_stream.getvalue().splitlines() if line]


def test_codes_are_masked_in_application_logs(client, anon, log_stream):
    code = make_ticket(client)["tracking_code"]
    anon.get(f"/api/public/track/{code.lower().removeprefix('bt-')}")
    anon.get("/api/public/track/BT-ZZZZZ")

    output = log_stream.getvalue()
    assert code not in output
    assert code.removeprefix("BT-") not in output
    messages = [line["message"] for line in _lines(log_stream)]
    assert any("Created ticket BT-*****" in m for m in messages)
    assert "Public tracking lookup for BT-*****: found" in messages
    assert "Public tracking lookup: not found" in messages


def test_codes_are_masked_in_uvicorn_access_logs(app, log_stream):
    # Same call shape as uvicorn's access logger (message template + args).
    logging.getLogger("uvicorn.access").info(
        '%s - "%s %s HTTP/%s" %d',
        "203.0.113.7:51234",
        "GET",
        "/api/public/track/7k3qx",
        "1.1",
        404,
    )
    entry = _lines(log_stream)[-1]
    assert entry["logger"] == "uvicorn.access"
    assert entry["message"] == '203.0.113.7:51234 - "GET /api/public/track/BT-***** HTTP/1.1" 404'


def test_json_log_format_fields(app, log_stream):
    logging.getLogger("app.test").warning("Ticket %s is late", "BT-7K3QX")
    entry = _lines(log_stream)[-1]
    assert set(entry) == {"time", "level", "logger", "message"}
    assert entry["level"] == "WARNING"
    assert entry["message"] == "Ticket BT-***** is late"
    assert entry["time"].endswith("Z")


def test_text_format_is_also_masked(app):
    import io

    from app.logging_config import configure_logging

    stream = io.StringIO()
    configure_logging("INFO", "text", stream=stream)
    logging.getLogger("app.test").info("Code %s", "bt-7k3qx")
    assert stream.getvalue().rstrip().endswith("app.test: Code BT-*****")
