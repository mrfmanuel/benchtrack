"""Tracking code generation and normalization (spec §4 F2, §9.12, §9.13)."""

import re
from collections.abc import Iterator

import pytest

from app.services.tracking_codes import (
    ALPHABET,
    MAX_ATTEMPTS,
    TrackingCodeCollision,
    TrackingCodeGenerationError,
    create_with_unique_code,
    generate_tracking_code,
    is_valid_tracking_code,
    normalize_tracking_code,
)

SPEC_ALPHABET = "23456789ABCDEFGHJKMNPQRSTVWXYZ"
SPEC_PATTERN = re.compile(r"^BT-[23456789ABCDEFGHJKMNPQRSTVWXYZ]{5}$")


# --- Alphabet and generation -------------------------------------------------


def test_alphabet_matches_spec():
    assert ALPHABET == SPEC_ALPHABET


@pytest.mark.parametrize("char", ["0", "O", "1", "I", "L", "U"])
def test_alphabet_excludes_ambiguous_characters(char):
    assert char not in ALPHABET


def test_max_attempts_is_five():
    assert MAX_ATTEMPTS == 5


def test_generated_codes_match_format():
    for _ in range(500):
        assert SPEC_PATTERN.fullmatch(generate_tracking_code())


def test_generated_codes_vary():
    assert len({generate_tracking_code() for _ in range(200)}) > 190


def test_generation_uses_injected_choice():
    picks = iter("7K3QX")
    assert generate_tracking_code(choice=lambda _alphabet: next(picks)) == "BT-7K3QX"


# --- Validation and normalization ---------------------------------------------


@pytest.mark.parametrize("code", ["BT-7K3QX", "BT-22222", "BT-ZZZZZ"])
def test_valid_codes(code):
    assert is_valid_tracking_code(code) is True


@pytest.mark.parametrize(
    "code",
    ["bt-7k3qx", "BT-7K3Q", "BT-7K3QXX", "BT-7K3Q0", "BT-7K3QI", "BT7K3QX", "7K3QX", ""],
)
def test_invalid_canonical_codes(code):
    assert is_valid_tracking_code(code) is False


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("BT-7K3QX", "BT-7K3QX"),
        ("bt-7k3qx", "BT-7K3QX"),
        ("Bt-7k3Qx", "BT-7K3QX"),
        ("7K3QX", "BT-7K3QX"),
        ("7k3qx", "BT-7K3QX"),
        ("  BT-7K3QX  ", "BT-7K3QX"),
        ("\t7k3qx\n", "BT-7K3QX"),
    ],
)
def test_normalize_accepts_user_input(raw, expected):
    assert normalize_tracking_code(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "BT-",
        "7K3Q",  # too short
        "7K3QXX",  # too long
        "BT-7K3Q0",  # 0 not in alphabet
        "OK3QX",  # O not in alphabet
        "7K3QI",
        "7K3QL",
        "7K3QU",
        "BT 7K3QX",  # inner whitespace is not trimmed
        "7K 3QX",
        "XX-7K3QX",  # wrong prefix
        "BT--7K3QX",
        "BT-7K3QX/../x",
        "%42T-7K3QX",
    ],
)
def test_normalize_rejects_invalid_input(raw):
    assert normalize_tracking_code(raw) is None


# --- Collision retry -----------------------------------------------------------


def _codes() -> Iterator[str]:
    for n in range(1, 100):
        yield f"BT-{'23456789A'[n % 9]}AAAA"


def test_create_returns_result_on_first_try():
    calls: list[str] = []

    def try_create(code: str) -> str:
        calls.append(code)
        return f"ticket:{code}"

    result = create_with_unique_code(try_create)
    assert result == f"ticket:{calls[0]}"
    assert len(calls) == 1
    assert SPEC_PATTERN.fullmatch(calls[0])


def test_create_retries_on_collision_with_a_new_code():
    codes = _codes()
    calls: list[str] = []

    def try_create(code: str) -> str:
        calls.append(code)
        if len(calls) < MAX_ATTEMPTS:
            raise TrackingCodeCollision(code)
        return code

    result = create_with_unique_code(try_create, generate=lambda: next(codes))
    assert len(calls) == MAX_ATTEMPTS
    assert result == calls[-1]
    assert len(set(calls)) == MAX_ATTEMPTS  # a fresh code each attempt


def test_create_gives_up_after_max_attempts():
    calls: list[str] = []

    def try_create(code: str) -> str:
        calls.append(code)
        raise TrackingCodeCollision(code)

    with pytest.raises(TrackingCodeGenerationError):
        create_with_unique_code(try_create)
    assert len(calls) == MAX_ATTEMPTS


def test_create_does_not_swallow_other_errors():
    calls: list[str] = []

    def try_create(code: str) -> str:
        calls.append(code)
        raise RuntimeError("database is down")

    with pytest.raises(RuntimeError, match="database is down"):
        create_with_unique_code(try_create)
    assert len(calls) == 1
