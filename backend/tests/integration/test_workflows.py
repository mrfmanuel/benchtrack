"""Key HTTP workflows against PostgreSQL (migrated schema, real constraints)."""

import pytest

from tests.api.conftest import assert_error, backdate, make_customer, make_ticket, move

pytestmark = pytest.mark.integration

PUBLIC_WHITELIST = {
    "tracking_code",
    "device_type",
    "brand",
    "model",
    "status",
    "last_status_change_at",
    "timeline",
}


def test_full_ticket_lifecycle_with_timeline(client):
    customer = make_customer(client, name="Sofía Jiménez", phone="+506 8800-1234")
    ticket = make_ticket(client, customer["id"], estimated_cost=45000.5)
    assert ticket["status"] == "received"
    assert ticket["estimated_cost"] == 45000.5  # Numeric(10,2) round-trips as a JSON number

    move(client, ticket["id"], "diagnosing", "waiting_parts", "repairing", "ready", "delivered")
    client.post(f"/api/tickets/{ticket['id']}/notes", json={"note": "Warranty follow-up."})

    events = client.get(f"/api/tickets/{ticket['id']}/events").json()
    assert events["total"] == 7
    assert [e["to_status"] for e in events["items"] if e["kind"] == "status"] == [
        "received",
        "diagnosing",
        "waiting_parts",
        "repairing",
        "ready",
        "delivered",
    ]
    assert events["items"][-1]["kind"] == "note"
    assert all(e["created_at"].endswith("Z") for e in events["items"])

    fetched = client.get(f"/api/tickets/{ticket['id']}").json()
    assert fetched["customer"]["name"] == "Sofía Jiménez"
    assert_error(
        client.patch(f"/api/tickets/{ticket['id']}", json={"brand": "HP"}), 409, "ticket_final"
    )


def test_invalid_transition_returns_409(client):
    ticket = make_ticket(client)
    response = client.post(f"/api/tickets/{ticket['id']}/status", json={"to_status": "ready"})
    error = assert_error(response, 409, "invalid_transition")
    assert error["details"]["allowed"] == ["cancelled", "diagnosing"]


def test_public_tracking_whitelist(client, anon):
    customer = make_customer(client, email="ana@example.com")
    ticket = make_ticket(client, customer["id"], serial_number="SN-1", estimated_cost=1000)
    client.post(f"/api/tickets/{ticket['id']}/notes", json={"note": "INTERNAL"})

    response = anon.get(f"/api/public/track/{ticket['tracking_code'].lower()}")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == PUBLIC_WHITELIST
    assert body["timeline"] == [{"status": "received", "at": ticket["created_at"]}]
    for secret in ("INTERNAL", "SN-1", "ana@example.com", customer["phone"]):
        assert secret not in response.text


def test_duplicate_phone_returns_409(client):
    first = make_customer(client, phone="+50688001234")
    response = client.post("/api/customers", json={"name": "Other", "phone": "+506 8800 1234"})
    error = assert_error(response, 409, "conflict")
    assert error["details"]["existing_customer_id"] == first["id"]


def test_dashboard_stale_detection(app, client):
    stale = make_ticket(client)
    move(client, stale["id"], "diagnosing")
    almost_seven = make_ticket(client)
    closed = make_ticket(client)
    move(client, closed["id"], "cancelled")
    backdate(app, stale["id"], days=8)
    backdate(app, almost_seven["id"], days=6.99)
    backdate(app, closed["id"], days=30)

    body = client.get("/api/dashboard").json()
    assert body["counts"]["received"] == 1
    assert body["counts"]["diagnosing"] == 1
    assert body["counts"]["cancelled"] == 1
    assert [t["id"] for t in body["stale_tickets"]] == [stale["id"]]


def test_search_is_case_insensitive_on_postgres(client):
    # ILIKE on PostgreSQL vs LIKE on SQLite: make sure both behave the same.
    customer = make_customer(client, name="Sofía Jiménez")
    make_ticket(client, customer["id"], brand="Lenovo")
    assert client.get("/api/customers", params={"q": "JIMÉNEZ"}).json()["total"] == 1
    assert client.get("/api/tickets", params={"q": "lenovo"}).json()["total"] == 1
    assert client.get("/api/customers", params={"q": "%"}).json()["total"] == 0
