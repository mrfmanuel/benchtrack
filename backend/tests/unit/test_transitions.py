"""Status workflow rules (spec §4 F3, §9.9)."""

from itertools import product

import pytest

from app.services.transitions import (
    FINAL_STATUSES,
    OPEN_STATUSES,
    InvalidTransitionError,
    TicketStatus,
    allowed_next_statuses,
    is_transition_allowed,
    validate_transition,
)

S = TicketStatus

# Written out from the spec on purpose, independent of the implementation's table.
SPEC_ALLOWED: dict[TicketStatus, set[TicketStatus]] = {
    S.RECEIVED: {S.DIAGNOSING, S.CANCELLED},
    S.DIAGNOSING: {S.WAITING_PARTS, S.REPAIRING, S.READY, S.CANCELLED},
    S.WAITING_PARTS: {S.REPAIRING, S.CANCELLED},
    S.REPAIRING: {S.WAITING_PARTS, S.READY, S.CANCELLED},
    S.READY: {S.DELIVERED, S.REPAIRING},
    S.DELIVERED: set(),
    S.CANCELLED: set(),
}

ALL_PAIRS = list(product(TicketStatus, repeat=2))
ALLOWED_PAIRS = [(a, b) for a, b in ALL_PAIRS if b in SPEC_ALLOWED[a]]
FORBIDDEN_PAIRS = [(a, b) for a, b in ALL_PAIRS if b not in SPEC_ALLOWED[a]]


def _id(pair: tuple[TicketStatus, TicketStatus]) -> str:
    return f"{pair[0].value}->{pair[1].value}"


def test_status_values_match_spec():
    assert [s.value for s in TicketStatus] == [
        "received",
        "diagnosing",
        "waiting_parts",
        "repairing",
        "ready",
        "delivered",
        "cancelled",
    ]


def test_pair_counts():
    assert len(ALL_PAIRS) == 49
    assert len(ALLOWED_PAIRS) == 13


@pytest.mark.parametrize("pair", ALLOWED_PAIRS, ids=_id)
def test_allowed_transition(pair):
    from_status, to_status = pair
    assert is_transition_allowed(from_status, to_status) is True
    validate_transition(from_status, to_status)  # does not raise


@pytest.mark.parametrize("pair", FORBIDDEN_PAIRS, ids=_id)
def test_forbidden_transition(pair):
    from_status, to_status = pair
    assert is_transition_allowed(from_status, to_status) is False
    with pytest.raises(InvalidTransitionError) as exc_info:
        validate_transition(from_status, to_status)
    err = exc_info.value
    assert err.from_status == from_status
    assert err.to_status == to_status
    assert err.allowed == frozenset(SPEC_ALLOWED[from_status])


@pytest.mark.parametrize("status", list(TicketStatus), ids=lambda s: s.value)
def test_same_status_is_rejected(status):
    assert is_transition_allowed(status, status) is False
    with pytest.raises(InvalidTransitionError):
        validate_transition(status, status)


@pytest.mark.parametrize("status", list(TicketStatus), ids=lambda s: s.value)
def test_allowed_next_statuses_match_spec(status):
    assert allowed_next_statuses(status) == frozenset(SPEC_ALLOWED[status])


def test_final_statuses_have_no_exits():
    assert {S.DELIVERED, S.CANCELLED} == FINAL_STATUSES
    for status in FINAL_STATUSES:
        assert allowed_next_statuses(status) == frozenset()


def test_open_statuses_are_all_non_final():
    assert set(TicketStatus) - FINAL_STATUSES == OPEN_STATUSES


def test_accepts_plain_string_values():
    assert is_transition_allowed("received", "diagnosing") is True
    assert is_transition_allowed("received", "ready") is False


def test_unknown_status_string_raises_value_error():
    with pytest.raises(ValueError):
        is_transition_allowed("received", "lost")


def test_error_message_is_human_readable():
    with pytest.raises(InvalidTransitionError) as exc_info:
        validate_transition(S.RECEIVED, S.READY)
    assert str(exc_info.value) == "Cannot change status from received to ready."
