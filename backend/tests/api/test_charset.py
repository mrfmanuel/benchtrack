"""Every JSON response declares charset=utf-8 (Windows PowerShell 5.1 needs it)."""

import pytest

from app.routers import health
from tests.api.conftest import make_customer, make_ticket

JSON_UTF8 = "application/json; charset=utf-8"


def test_success_responses_declare_utf8_and_keep_accents(client):
    customer = make_customer(client, name="Sofía Jiménez")
    ticket = make_ticket(client, customer["id"], brand="Señal Técnica")

    for response in (
        client.get(f"/api/customers/{customer['id']}"),
        client.get("/api/customers"),
        client.get(f"/api/tickets/{ticket['id']}"),
        client.get(f"/api/tickets/{ticket['id']}/events"),
        client.get("/api/dashboard"),
        client.get(f"/api/public/track/{ticket['tracking_code']}"),
        client.get("/api/health"),
    ):
        assert response.headers["content-type"] == JSON_UTF8, response.request.url
    raw = client.get(f"/api/customers/{customer['id']}").content
    assert "Sofía Jiménez".encode() in raw


@pytest.mark.parametrize(
    ("method", "path", "kwargs", "status"),
    [
        ("GET", "/api/tickets", {"headers": {"Authorization": "Bearer nope"}}, 401),
        ("GET", "/api/tickets/9999", {}, 404),
        ("GET", "/api/nope", {}, 404),
        ("DELETE", "/api/customers", {}, 405),
        ("POST", "/api/customers", {"json": {}}, 422),
    ],
)
def test_error_envelope_declares_utf8(client, method, path, kwargs, status):
    response = client.request(method, path, **kwargs)
    assert response.status_code == status
    assert response.headers["content-type"] == JSON_UTF8


def test_conflict_and_rate_limit_errors_declare_utf8(client, anon):
    customer = make_customer(client)
    duplicate = client.post("/api/customers", json={"name": "X", "phone": customer["phone"]})
    assert duplicate.status_code == 409
    assert duplicate.headers["content-type"] == JSON_UTF8
    for _ in range(10):
        anon.get("/api/public/track/BT-ZZZZZ")
    limited = anon.get("/api/public/track/BT-ZZZZZ")
    assert limited.status_code == 429
    assert limited.headers["content-type"] == JSON_UTF8


def test_degraded_health_declares_utf8(anon, monkeypatch):
    monkeypatch.setattr(health, "check_database", lambda _engine: False)
    response = anon.get("/api/health")
    assert response.status_code == 503
    assert response.headers["content-type"] == JSON_UTF8
