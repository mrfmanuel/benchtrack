"""Customers API (spec §4 F1, §9.1, §9.4, §9.20)."""

import pytest

from tests.api.conftest import assert_error, make_customer


def test_create_normalizes_phone_and_returns_utc_timestamp(client):
    response = client.post(
        "/api/customers",
        json={"name": "Luis Vargas", "phone": "(506) 8800-1234", "email": "luis@example.com"},
    )
    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "name", "phone", "email", "created_at"}
    assert body["phone"] == "50688001234"
    assert body["email"] == "luis@example.com"
    assert body["created_at"].endswith("Z")


def test_duplicate_phone_returns_409_conflict(client):
    first = make_customer(client, phone="+50688001234")
    response = client.post("/api/customers", json={"name": "Other", "phone": "+506 8800 1234"})
    error = assert_error(response, 409, "conflict")
    assert error["details"] == {"field": "phone", "existing_customer_id": first["id"]}


def test_duplicate_phone_race_still_reports_existing_customer_id(client, monkeypatch):
    """Two requests pass the pre-check at once: the unique constraint decides (spec §9.1)."""
    from app.services import customers as service

    first = make_customer(client, phone="+50688001234")
    real_lookup = service._id_with_phone
    calls = []

    def lookup(session, phone):
        calls.append(phone)
        # The pre-check runs before the other request commits; later lookups see its row.
        return None if len(calls) == 1 else real_lookup(session, phone)

    monkeypatch.setattr(service, "_id_with_phone", lookup)
    response = client.post("/api/customers", json={"name": "Other", "phone": "+50688001234"})
    error = assert_error(response, 409, "conflict")
    assert error["details"] == {"field": "phone", "existing_customer_id": first["id"]}
    assert len(calls) == 2


def test_integrity_error_without_a_matching_phone_is_not_reported_as_a_conflict(
    app, client, monkeypatch
):
    from fastapi.testclient import TestClient
    from sqlalchemy.exc import IntegrityError

    from app.services import customers as service

    make_customer(client, phone="+50688001234")
    monkeypatch.setattr(service, "_id_with_phone", lambda session, phone: None)
    with pytest.raises(IntegrityError):
        client.post("/api/customers", json={"name": "Other", "phone": "+50688001234"})
    with TestClient(app, raise_server_exceptions=False, headers=client.headers) as quiet:
        response = quiet.post("/api/customers", json={"name": "Other", "phone": "+50688001234"})
    assert_error(response, 500, "internal_error")


@pytest.mark.parametrize("bad_id", ["0", "-1"])
def test_customer_id_below_1_is_a_validation_error(client, bad_id):
    for response in (
        client.get(f"/api/customers/{bad_id}"),
        client.patch(f"/api/customers/{bad_id}", json={"name": "X"}),
    ):
        error = assert_error(response, 422, "validation_error")
        assert error["details"][0]["field"] == "customer_id"


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"phone": "88001234"}, "name"),
        ({"name": "Ana"}, "phone"),
        ({"name": "", "phone": "88001234"}, "name"),
        ({"name": "   ", "phone": "88001234"}, "name"),
        ({"name": "x" * 101, "phone": "88001234"}, "name"),
        ({"name": "Ana", "phone": "123"}, "phone"),
        ({"name": "Ana", "phone": "8800.1234"}, "phone"),
        ({"name": "Ana", "phone": "+506 8800 1234 5678 99"}, "phone"),  # > 20 chars
        ({"name": "Ana", "phone": "88001234", "email": "not-an-email"}, "email"),
        ({"name": "Ana", "phone": "88001234", "vip": True}, "vip"),
    ],
)
def test_create_validation_errors(client, body, field):
    error = assert_error(client.post("/api/customers", json=body), 422, "validation_error")
    assert field in [d["field"] for d in error["details"]]
    assert all(set(d) == {"field", "message"} for d in error["details"])


def _email_of_length(length: int) -> str:
    # 64-character local part, then 63-character labels: valid shape at any length used here.
    domain_len = length - 65
    labels = ["d" * 63] * (domain_len // 64)
    labels.append("d" * (domain_len - 64 * len(labels) - 4) + ".com")
    email = "a" * 64 + "@" + ".".join(labels)
    assert len(email) == length
    return email


def test_email_max_length_is_254(client):
    ok = client.post(
        "/api/customers", json={"name": "Ana", "phone": "88001234", "email": _email_of_length(254)}
    )
    assert ok.status_code == 201, ok.text
    too_long = client.post(
        "/api/customers", json={"name": "Ana", "phone": "88001235", "email": _email_of_length(255)}
    )
    error = assert_error(too_long, 422, "validation_error")
    assert [d["field"] for d in error["details"]] == ["email"]


def test_phone_error_message_is_readable(client):
    response = client.post("/api/customers", json={"name": "Ana", "phone": "123"})
    error = assert_error(response, 422, "validation_error")
    assert error["details"] == [
        {
            "field": "phone",
            "message": "Phone must contain 8 to 15 digits, optionally starting with +.",
        }
    ]


def test_malformed_json_returns_422(client):
    response = client.post(
        "/api/customers", content="{not json", headers={"Content-Type": "application/json"}
    )
    assert_error(response, 422, "validation_error")


def test_list_sorted_by_name_with_pagination(client):
    for name in ["Carlos Rojas", "Ana Mora", "Bea Solís"]:
        make_customer(client, name=name)

    page = client.get("/api/customers", params={"limit": 2}).json()
    assert page["total"] == 3
    assert [c["name"] for c in page["items"]] == ["Ana Mora", "Bea Solís"]

    page2 = client.get("/api/customers", params={"limit": 2, "offset": 2}).json()
    assert [c["name"] for c in page2["items"]] == ["Carlos Rojas"]


def test_search_by_name_and_formatted_phone(client):
    make_customer(client, name="Ana Mora", phone="+50688001234")
    make_customer(client, name="Luis Vargas", phone="+50677005678")

    by_name = client.get("/api/customers", params={"q": "mOrA"}).json()
    assert [c["name"] for c in by_name["items"]] == ["Ana Mora"]

    by_phone = client.get("/api/customers", params={"q": "7700-56"}).json()
    assert [c["name"] for c in by_phone["items"]] == ["Luis Vargas"]


def test_search_treats_wildcards_literally(client):
    make_customer(client, name="Ana Mora")
    assert client.get("/api/customers", params={"q": "%"}).json()["total"] == 0


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 201}, {"offset": -1}, {"q": "x" * 101}])
def test_list_rejects_bad_query_params(client, params):
    assert_error(client.get("/api/customers", params=params), 422, "validation_error")


def test_get_and_404(client):
    customer = make_customer(client)
    assert client.get(f"/api/customers/{customer['id']}").json() == customer
    error = assert_error(client.get("/api/customers/9999"), 404, "not_found")
    assert error["message"] == "Customer 9999 not found."


def test_patch_updates_only_given_fields(client):
    customer = make_customer(client, name="Ana Mora", email="ana@example.com")
    response = client.patch(f"/api/customers/{customer['id']}", json={"phone": "+506 7000-0001"})
    assert response.status_code == 200
    assert response.json() | {"phone": customer["phone"]} == customer
    assert response.json()["phone"] == "+50670000001"

    cleared = client.patch(f"/api/customers/{customer['id']}", json={"email": None})
    assert cleared.json()["email"] is None


def test_patch_duplicate_phone_returns_409(client):
    make_customer(client, phone="+50688001234")
    other = make_customer(client)
    response = client.patch(f"/api/customers/{other['id']}", json={"phone": "+50688001234"})
    assert_error(response, 409, "conflict")


def test_patch_own_phone_is_not_a_conflict(client):
    customer = make_customer(client, phone="+50688001234")
    response = client.patch(f"/api/customers/{customer['id']}", json={"phone": "+506 8800 1234"})
    assert response.status_code == 200


@pytest.mark.parametrize("body", [{}, {"name": None}, {"phone": None}, {"id": 5}])
def test_patch_validation_errors(client, body):
    customer = make_customer(client)
    assert_error(
        client.patch(f"/api/customers/{customer['id']}", json=body), 422, "validation_error"
    )


def test_patch_unknown_customer_returns_404(client):
    assert_error(client.patch("/api/customers/9999", json={"name": "X"}), 404, "not_found")
