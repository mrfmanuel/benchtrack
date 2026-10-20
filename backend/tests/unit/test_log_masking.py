"""Tracking codes are masked in logs (spec §9.16)."""

import pytest

from app.services.log_masking import MASK, mask_tracking_codes


def test_mask_value():
    assert MASK == "BT-*****"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Ticket BT-7K3QX created", "Ticket BT-***** created"),
        ("bt-7k3qx looked up", "BT-***** looked up"),
        ("BT-7K3QX,BT-22222", "BT-*****,BT-*****"),
        ('{"tracking_code": "BT-7K3QX"}', '{"tracking_code": "BT-*****"}'),
        ("GET /api/tickets?q=BT-7K3QX&limit=5", "GET /api/tickets?q=BT-*****&limit=5"),
    ],
)
def test_masks_codes_in_text(text, expected):
    assert mask_tracking_codes(text) == expected


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/api/public/track/BT-7K3QX", "/api/public/track/BT-*****"),
        ("/api/public/track/7k3qx", "/api/public/track/BT-*****"),
        ("/api/public/track/bt-7k3qx?x=1", "/api/public/track/BT-*****?x=1"),
        ("/api/public/track/%20bt-7k3qx%20", "/api/public/track/BT-*****"),
        ("/api/public/track/whatever-was-typed", "/api/public/track/BT-*****"),
        ("/track/7K3QX", "/track/BT-*****"),
        (
            '127.0.0.1 - "GET /api/public/track/7k3qx HTTP/1.1" 404',
            '127.0.0.1 - "GET /api/public/track/BT-***** HTTP/1.1" 404',
        ),
    ],
)
def test_masks_any_value_in_tracking_paths(path, expected):
    # Codes in tracking paths may lack the prefix or be invalid; mask the whole segment.
    assert mask_tracking_codes(path) == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        "Customer 12 updated",
        "GET /api/tickets/42/events",
        "GET /api/public/track/ HTTP/1.1",
        "BT-12 is not a code",
        "ABT-7K3QXY",
        "/api/tracking/stats",
    ],
)
def test_leaves_other_text_untouched(text):
    assert mask_tracking_codes(text) == text


def test_is_idempotent():
    once = mask_tracking_codes("/api/public/track/7k3qx and BT-7K3QX")
    assert mask_tracking_codes(once) == once
