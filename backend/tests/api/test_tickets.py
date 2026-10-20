"""Tickets API: CRUD, status workflow, notes, timeline (spec §4 F2–F3, §9)."""

import pytest

from app.services import tracking_codes
from tests.api.conftest import assert_error, backdate, make_customer, make_ticket, move

TICKET_KEYS = {
    "id",
    "customer_id",
    "customer",
    "device_type",
    "brand",
    "model",
    "serial_number",
    "reported_issue",
    "diagnosis",
    "estimated_cost",
    "status",
    "tracking_code",
    "created_at",
    "updated_at",
}


# --- Create ------------------------------------------------------------------------


def test_create_ticket_shape_and_initial_event(client):
    ticket = make_ticket(client, estimated_cost=45000.5)
    assert set(ticket) == TICKET_KEYS
    assert ticket["status"] == "received"
    assert tracking_codes.is_valid_tracking_code(ticket["tracking_code"])
    assert ticket["created_at"] == ticket["updated_at"]
    assert ticket["created_at"].endswith("Z")

    events = client.get(f"/api/tickets/{ticket['id']}/events").json()["items"]
    assert len(events) == 1
    assert events[0] | {"id": None} == {
        "id": None,
        "ticket_id": ticket["id"],
        "kind": "status",
        "from_status": None,
        "to_status": "received",
        "note": None,
        "created_at": ticket["created_at"],
    }


def test_estimated_cost_is_a_json_number(client):
    ticket = make_ticket(client, estimated_cost=45000.5)
    assert ticket["estimated_cost"] == 45000.5
    assert isinstance(ticket["estimated_cost"], float)
    assert make_ticket(client)["estimated_cost"] is None


def test_unknown_customer_returns_422_on_customer_id(client):
    response = client.post(
        "/api/tickets",
        json={"customer_id": 99, "device_type": "laptop", "brand": "HP", "reported_issue": "x"},
    )
    error = assert_error(response, 422, "validation_error")
    assert error["details"] == [{"field": "customer_id", "message": "Customer 99 does not exist."}]


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"device_type": "toaster"}, "device_type"),
        ({"brand": ""}, "brand"),
        ({"brand": "x" * 61}, "brand"),
        ({"model": "x" * 61}, "model"),
        ({"reported_issue": "x" * 2001}, "reported_issue"),
        ({"estimated_cost": -1}, "estimated_cost"),
        ({"estimated_cost": 10_000_000.01}, "estimated_cost"),
        ({"estimated_cost": 1.234}, "estimated_cost"),
        ({"status": "ready"}, "status"),
        ({"tracking_code": "BT-22222"}, "tracking_code"),
    ],
)
def test_create_validation_errors(client, overrides, field):
    customer = make_customer(client)
    body = {
        "customer_id": customer["id"],
        "device_type": "laptop",
        "brand": "HP",
        "reported_issue": "Broken hinge.",
    } | overrides
    error = assert_error(client.post("/api/tickets", json=body), 422, "validation_error")
    assert field in [d["field"] for d in error["details"]]


def test_cost_boundaries_are_accepted(client):
    assert make_ticket(client, estimated_cost=0)["estimated_cost"] == 0
    assert make_ticket(client, estimated_cost=10_000_000)["estimated_cost"] == 10_000_000


def test_tracking_code_collision_is_retried(client, monkeypatch):
    codes = iter(["BT-22222", "BT-22222", "BT-33333"])
    monkeypatch.setattr(tracking_codes, "generate_tracking_code", lambda: next(codes))
    assert make_ticket(client)["tracking_code"] == "BT-22222"
    assert make_ticket(client)["tracking_code"] == "BT-33333"


def test_tracking_code_generation_gives_up_with_500(client, monkeypatch):
    monkeypatch.setattr(tracking_codes, "generate_tracking_code", lambda: "BT-22222")
    make_ticket(client)
    customer = make_customer(client)
    response = client.post(
        "/api/tickets",
        json={
            "customer_id": customer["id"],
            "device_type": "phone",
            "brand": "X",
            "reported_issue": "y",
        },
    )
    assert_error(response, 500, "tracking_code_generation_failed")
    assert client.get("/api/tickets").json()["total"] == 1


# --- List and get ----------------------------------------------------------------------


def test_list_sorted_newest_first_with_filters(client):
    ana = make_customer(client, name="Ana Mora")
    luis = make_customer(client, name="Luis Vargas")
    t1 = make_ticket(client, ana["id"], brand="Lenovo")
    t2 = make_ticket(client, luis["id"], brand="Samsung", model="Galaxy A54")
    t3 = make_ticket(client, ana["id"], brand="Dell")
    move(client, t3["id"], "diagnosing")

    def ids(**params):
        body = client.get("/api/tickets", params=params).json()
        assert body["total"] == len(body["items"])
        return [t["id"] for t in body["items"]]

    assert ids() == [t3["id"], t2["id"], t1["id"]]
    assert ids(status="received") == [t2["id"], t1["id"]]
    assert ids(customer_id=ana["id"]) == [t3["id"], t1["id"]]
    assert ids(customer_id=ana["id"], status="diagnosing") == [t3["id"]]
    assert ids(customer_id=9999) == []
    assert ids(q="galaxy") == [t2["id"]]
    assert ids(q="vargas") == [t2["id"]]
    assert ids(q="lenovo") == [t1["id"]]
    assert ids(q=t1["tracking_code"].lower()) == [t1["id"]]


def test_list_pagination(client):
    customer = make_customer(client)
    for _ in range(3):
        make_ticket(client, customer["id"])
    page = client.get("/api/tickets", params={"limit": 2, "offset": 2}).json()
    assert page["total"] == 3 and len(page["items"]) == 1


@pytest.mark.parametrize("params", [{"status": "lost"}, {"customer_id": 0}, {"limit": 500}])
def test_list_rejects_bad_filters(client, params):
    assert_error(client.get("/api/tickets", params=params), 422, "validation_error")


def test_get_ticket_and_404(client):
    ticket = make_ticket(client)
    assert client.get(f"/api/tickets/{ticket['id']}").json() == ticket
    assert_error(client.get("/api/tickets/9999"), 404, "not_found")
    assert_error(client.get("/api/tickets/abc"), 422, "validation_error")


# --- Update ------------------------------------------------------------------------------


def test_patch_details_bumps_updated_at(app, client):
    ticket = make_ticket(client)
    backdate(app, ticket["id"], days=3)
    response = client.patch(
        f"/api/tickets/{ticket['id']}",
        json={
            "diagnosis": "Liquid damage on the keyboard.",
            "estimated_cost": 45000,
            "model": None,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["diagnosis"] == "Liquid damage on the keyboard."
    assert body["estimated_cost"] == 45000
    assert body["model"] is None
    assert body["tracking_code"] == ticket["tracking_code"]
    assert body["updated_at"] >= ticket["updated_at"]


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"customer_id": 2},
        {"status": "ready"},
        {"tracking_code": "BT-22222"},
        {"brand": None},
        {"reported_issue": None},
        {"device_type": None},
    ],
)
def test_patch_rejects_immutable_and_null_fields(client, body):
    ticket = make_ticket(client)
    assert_error(client.patch(f"/api/tickets/{ticket['id']}", json=body), 422, "validation_error")


@pytest.mark.parametrize("final", ["delivered", "cancelled"])
def test_final_ticket_details_are_read_only(client, final):
    ticket = make_ticket(client)
    path = ["diagnosing", "ready", "delivered"] if final == "delivered" else ["cancelled"]
    move(client, ticket["id"], *path)
    response = client.patch(f"/api/tickets/{ticket['id']}", json={"diagnosis": "late edit"})
    error = assert_error(response, 409, "ticket_final")
    assert final in error["message"]


def test_patch_unknown_ticket_returns_404(client):
    assert_error(client.patch("/api/tickets/9999", json={"brand": "HP"}), 404, "not_found")


# --- Status -------------------------------------------------------------------------------


def test_status_change_records_event_with_note_and_bumps_updated_at(app, client):
    ticket = make_ticket(client)
    backdate(app, ticket["id"], days=3)
    response = client.post(
        f"/api/tickets/{ticket['id']}/status",
        json={"to_status": "diagnosing", "note": "Started teardown."},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "diagnosing"
    assert body["updated_at"] >= ticket["updated_at"]

    last = client.get(f"/api/tickets/{ticket['id']}/events").json()["items"][-1]
    assert (last["kind"], last["from_status"], last["to_status"], last["note"]) == (
        "status",
        "received",
        "diagnosing",
        "Started teardown.",
    )
    assert last["created_at"] == body["updated_at"]


def test_same_status_is_invalid_transition(client):
    ticket = make_ticket(client)
    response = client.post(f"/api/tickets/{ticket['id']}/status", json={"to_status": "received"})
    assert_error(response, 409, "invalid_transition")


@pytest.mark.parametrize(
    ("path", "final"),
    [(["cancelled"], "cancelled"), (["diagnosing", "ready", "delivered"], "delivered")],
)
def test_status_change_on_final_ticket_is_ticket_final(client, path, final):
    ticket = make_ticket(client)
    move(client, ticket["id"], *path)
    response = client.post(f"/api/tickets/{ticket['id']}/status", json={"to_status": "repairing"})
    assert_error(response, 409, "ticket_final")


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"to_status": "lost"},
        {"to_status": "ready", "note": ""},
        {"to_status": "diagnosing", "note": None},
    ],
)
def test_status_change_validation(client, body):
    ticket = make_ticket(client)
    response = client.post(f"/api/tickets/{ticket['id']}/status", json=body)
    assert_error(response, 422, "validation_error")


def test_status_change_unknown_ticket_returns_404(client):
    response = client.post("/api/tickets/9999/status", json={"to_status": "diagnosing"})
    assert_error(response, 404, "not_found")


# --- Notes and events -----------------------------------------------------------------------


def test_add_note_creates_note_event_and_bumps_updated_at(app, client):
    ticket = make_ticket(client)
    backdate(app, ticket["id"], days=3)
    response = client.post(
        f"/api/tickets/{ticket['id']}/notes", json={"note": "  Customer called.  "}
    )
    assert response.status_code == 201
    event = response.json()
    assert (event["kind"], event["from_status"], event["to_status"], event["note"]) == (
        "note",
        None,
        None,
        "Customer called.",
    )
    after = client.get(f"/api/tickets/{ticket['id']}").json()
    assert after["status"] == "received"
    assert after["updated_at"] == event["created_at"] >= ticket["updated_at"]


@pytest.mark.parametrize("path", [["cancelled"], ["diagnosing", "ready", "delivered"]])
def test_notes_allowed_on_final_tickets(client, path):
    ticket = make_ticket(client)
    move(client, ticket["id"], *path)
    response = client.post(
        f"/api/tickets/{ticket['id']}/notes", json={"note": "Warranty follow-up."}
    )
    assert response.status_code == 201


@pytest.mark.parametrize(
    "body",
    [{}, {"note": ""}, {"note": "   "}, {"note": "x" * 1001}, {"note": "ok", "kind": "status"}],
)
def test_note_validation(client, body):
    ticket = make_ticket(client)
    assert_error(
        client.post(f"/api/tickets/{ticket['id']}/notes", json=body), 422, "validation_error"
    )


def test_notes_and_events_on_unknown_ticket_return_404(client):
    assert_error(client.post("/api/tickets/9999/notes", json={"note": "x"}), 404, "not_found")
    assert_error(client.get("/api/tickets/9999/events"), 404, "not_found")


def test_events_mix_status_and_notes_in_order(client):
    ticket = make_ticket(client)
    client.post(f"/api/tickets/{ticket['id']}/notes", json={"note": "First note."})
    move(client, ticket["id"], "diagnosing")
    body = client.get(f"/api/tickets/{ticket['id']}/events").json()
    assert [e["kind"] for e in body["items"]] == ["status", "note", "status"]
    assert body["total"] == 3
