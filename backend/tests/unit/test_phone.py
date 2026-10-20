"""Phone normalization and validation (spec §9.1)."""

import pytest

from app.services.phone import InvalidPhoneError, normalize_phone


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+50688001234", "+50688001234"),
        ("88001234", "88001234"),  # 8 digits (minimum)
        ("+123456789012345", "+123456789012345"),  # 15 digits (maximum)
        ("+506 8800 1234", "+50688001234"),
        ("+506 8800-1234", "+50688001234"),
        ("(506) 8800-1234", "50688001234"),
        ("+(506) 8800-1234", "+50688001234"),
        ("  8800-1234  ", "88001234"),
        ("8-8-0-0-1-2-3-4", "88001234"),
    ],
)
def test_normalizes_valid_numbers(raw, expected):
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "8800123",  # 7 digits
        "+8800123",
        "1234567890123456",  # 16 digits
        "+1234567890123456",
        "8800.1234",  # dots are not removed
        "8800/1234",
        "88001234 ext 5",
        "++50688001234",
        "506+88001234",  # + only allowed at the start
        "8800-123A",
        "+",
        "---",
        "８８００１２３４",  # full-width digits are not ASCII digits
    ],
)
def test_rejects_invalid_numbers(raw):
    with pytest.raises(InvalidPhoneError):
        normalize_phone(raw)


def test_invalid_phone_error_is_a_value_error():
    # Lets Pydantic validators surface it as a 422 validation error.
    assert issubclass(InvalidPhoneError, ValueError)


def test_error_message_is_human_readable():
    with pytest.raises(InvalidPhoneError, match="8 to 15 digits"):
        normalize_phone("123")
