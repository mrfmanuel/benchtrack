"""Public tracking (spec §4 F4, §9.11, §9.13, §9.14, §9.15)."""

import pytest

from tests.api.conftest import assert_error, make_ticket, move

WHITELIST = {
    "tracking_code",
    "device_type",
    "brand",
    "model",
    "status",
    "last_status_change_at",
    "timeline",
}


def test_response_keys_are_exactly_the_whitelist(client, anon):
    ticket = make_ticket(client, serial_number="SN-1", diagnosis="secret", estimated_cost=1000)
    client.post(f"/api/tickets/{ticket['id']}/notes", json={"note": "internal"})
    move(client, ticket["id"], "diagnosing")

    body = anon.get(f"/api/public/track/{ticket['tracking_code']}").json()
    assert set(body) == WHITELIST
    assert all(set(entry) == {"status", "at"} for entry in body["timeline"])
    assert body["tracking_code"] == ticket["tracking_code"]
    assert (body["device_type"], body["brand"], body["model"]) == (
        "laptop",
        "Lenovo",
        "ThinkPad T14",
    )


def test_timeline_has_status_events_only_and_last_change_ignores_notes(app, client, anon):
    ticket = make_ticket(client)
    changed = move(client, ticket["id"], "diagnosing")
    client.post(f"/api/tickets/{ticket['id']}/notes", json={"note": "later note"})

    body = anon.get(f"/api/public/track/{ticket['tracking_code']}").json()
    assert [e["status"] for e in body["timeline"]] == ["received", "diagnosing"]
    # §9.11: last status event, not updated_at (which the note bumped).
    assert body["last_status_change_at"] == changed["updated_at"] == body["timeline"][-1]["at"]
    assert body["last_status_change_at"].endswith("Z")


@pytest.mark.parametrize(
    "variant",
    [
        lambda c: c,
        lambda c: c.lower(),
        lambda c: c.removeprefix("BT-"),
        lambda c: c.removeprefix("BT-").lower(),
        lambda c: f"  {c}  ",
        lambda c: f"%20{c.lower()}%20",
    ],
    ids=["canonical", "lowercase", "no-prefix", "no-prefix-lowercase", "spaces", "encoded-spaces"],
)
def test_lookup_normalization(client, anon, variant):
    code = make_ticket(client)["tracking_code"]
    response = anon.get(f"/api/public/track/{variant(code)}")
    assert response.status_code == 200, response.text
    assert response.json()["tracking_code"] == code


@pytest.mark.parametrize("raw", ["BT-ZZZZZ", "BT7K3QX", "BT-0O1IL", "x" * 21, "%00", "BT-22222x"])
def test_unknown_or_invalid_codes_return_404(anon, raw):
    error = assert_error(anon.get(f"/api/public/track/{raw}"), 404, "not_found")
    assert error["message"] == "No repair found for this tracking code."


def test_public_route_needs_no_token_and_ignores_a_wrong_one(client, anon):
    code = make_ticket(client)["tracking_code"]
    assert anon.get(f"/api/public/track/{code}").status_code == 200
    response = anon.get(f"/api/public/track/{code}", headers={"Authorization": "Bearer wrong"})
    assert response.status_code == 200


def test_rate_limit_429_with_retry_after_then_recovers(anon, clock):
    for _ in range(10):
        assert anon.get("/api/public/track/BT-ZZZZZ").status_code == 404
        clock.advance(1)

    response = anon.get("/api/public/track/BT-ZZZZZ")
    error = assert_error(response, 429, "rate_limited")
    # Oldest hit was at t=0, now t=10 → it leaves the 60 s window in 50 s.
    assert response.headers["Retry-After"] == "50"
    assert "50 seconds" in error["message"]

    clock.advance(49)
    assert anon.get("/api/public/track/BT-ZZZZZ").status_code == 429
    clock.advance(1)
    assert anon.get("/api/public/track/BT-ZZZZZ").status_code == 404


def test_rate_limit_applies_only_to_public_routes(client, anon):
    for _ in range(12):
        anon.get("/api/public/track/BT-ZZZZZ")
    assert client.get("/api/tickets").status_code == 200
    assert anon.get("/api/health").status_code == 200
