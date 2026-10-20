"""Acceptance scenarios from product-spec.md §8."""

from tests.api.conftest import assert_error, backdate, make_customer, make_ticket, move


def test_1_create_customer_and_laptop_ticket(client):
    customer = make_customer(client, name="Ana Mora", phone="+506 8800-1234")
    ticket = make_ticket(client, customer["id"], device_type="laptop")

    assert ticket["status"] == "received"
    assert ticket["tracking_code"].startswith("BT-") and len(ticket["tracking_code"]) == 8
    assert ticket["customer"] == {"id": customer["id"], "name": "Ana Mora", "phone": "+50688001234"}


def test_2_full_workflow_timeline_has_six_entries_in_order(client):
    ticket = make_ticket(client)
    path = ["diagnosing", "waiting_parts", "repairing", "ready", "delivered"]
    move(client, ticket["id"], *path)

    events = client.get(f"/api/tickets/{ticket['id']}/events").json()
    assert events["total"] == 6
    transitions = [(e["from_status"], e["to_status"]) for e in events["items"]]
    assert transitions == [
        (None, "received"),
        ("received", "diagnosing"),
        ("diagnosing", "waiting_parts"),
        ("waiting_parts", "repairing"),
        ("repairing", "ready"),
        ("ready", "delivered"),
    ]
    assert all(e["kind"] == "status" for e in events["items"])
    timestamps = [e["created_at"] for e in events["items"]]
    assert timestamps == sorted(timestamps)


def test_3_invalid_transition_returns_409(client):
    ticket = make_ticket(client)
    response = client.post(f"/api/tickets/{ticket['id']}/status", json={"to_status": "ready"})

    error = assert_error(response, 409, "invalid_transition")
    assert error["message"] == "Cannot change status from received to ready."
    assert error["details"] == {
        "from_status": "received",
        "to_status": "ready",
        "allowed": ["cancelled", "diagnosing"],
    }
    assert client.get(f"/api/tickets/{ticket['id']}").json()["status"] == "received"


def test_4_public_tracking_hides_phone_and_notes(client, anon):
    customer = make_customer(client, name="Ana Mora", phone="+50688001234", email="ana@example.com")
    ticket = make_ticket(client, customer["id"], serial_number="PF-2X9QK1", estimated_cost=45000)
    client.post(
        f"/api/tickets/{ticket['id']}/status",
        json={"to_status": "diagnosing", "note": "INTERNAL: customer was rude"},
    )
    client.post(f"/api/tickets/{ticket['id']}/notes", json={"note": "INTERNAL: owes ₡5000"})

    response = anon.get(f"/api/public/track/{ticket['tracking_code']}")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "diagnosing"
    assert [entry["status"] for entry in body["timeline"]] == ["received", "diagnosing"]

    raw = response.text
    for secret in ("88001234", "Ana Mora", "ana@example.com", "INTERNAL", "PF-2X9QK1"):
        assert secret not in raw
    assert "estimated_cost" not in body


def test_5_staff_endpoint_without_token_returns_401(anon):
    assert_error(anon.get("/api/tickets"), 401, "unauthorized")


def test_6_dashboard_counts_and_stale_ticket(app, client):
    stale = make_ticket(client)
    move(client, stale["id"], "diagnosing", "waiting_parts")
    fresh = make_ticket(client)
    done = make_ticket(client)
    move(client, done["id"], "cancelled")
    backdate(app, stale["id"], days=8)
    backdate(app, done["id"], days=30)

    body = client.get("/api/dashboard").json()
    assert body["counts"] == {
        "received": 1,
        "diagnosing": 0,
        "waiting_parts": 1,
        "repairing": 0,
        "ready": 0,
        "delivered": 0,
        "cancelled": 1,
    }
    assert [t["id"] for t in body["stale_tickets"]] == [stale["id"]]
    assert fresh["id"] not in [t["id"] for t in body["stale_tickets"]]
