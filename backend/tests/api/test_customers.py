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
