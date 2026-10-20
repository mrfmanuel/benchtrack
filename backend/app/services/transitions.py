"""Ticket status workflow (spec §4 F3, §9.9)."""

from enum import StrEnum


class TicketStatus(StrEnum):
    RECEIVED = "received"
    DIAGNOSING = "diagnosing"
    WAITING_PARTS = "waiting_parts"
    REPAIRING = "repairing"
    READY = "ready"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


_S = TicketStatus

ALLOWED_TRANSITIONS: dict[TicketStatus, frozenset[TicketStatus]] = {
    _S.RECEIVED: frozenset({_S.DIAGNOSING, _S.CANCELLED}),
    _S.DIAGNOSING: frozenset({_S.WAITING_PARTS, _S.REPAIRING, _S.READY, _S.CANCELLED}),
    _S.WAITING_PARTS: frozenset({_S.REPAIRING, _S.CANCELLED}),
    _S.REPAIRING: frozenset({_S.WAITING_PARTS, _S.READY, _S.CANCELLED}),
    _S.READY: frozenset({_S.DELIVERED, _S.REPAIRING}),
    _S.DELIVERED: frozenset(),
    _S.CANCELLED: frozenset(),
}

FINAL_STATUSES: frozenset[TicketStatus] = frozenset(
    status for status, nexts in ALLOWED_TRANSITIONS.items() if not nexts
)
OPEN_STATUSES: frozenset[TicketStatus] = frozenset(TicketStatus) - FINAL_STATUSES


class InvalidTransitionError(Exception):
    """Raised when a status change is not allowed by the workflow."""

    def __init__(self, from_status: TicketStatus, to_status: TicketStatus) -> None:
        self.from_status = from_status
        self.to_status = to_status
        self.allowed = ALLOWED_TRANSITIONS[from_status]
        super().__init__(f"Cannot change status from {from_status} to {to_status}.")


def allowed_next_statuses(status: TicketStatus | str) -> frozenset[TicketStatus]:
    return ALLOWED_TRANSITIONS[TicketStatus(status)]


def is_transition_allowed(from_status: TicketStatus | str, to_status: TicketStatus | str) -> bool:
    return TicketStatus(to_status) in allowed_next_statuses(from_status)


def validate_transition(from_status: TicketStatus | str, to_status: TicketStatus | str) -> None:
    """Raise InvalidTransitionError unless `from_status → to_status` is allowed."""
    from_status, to_status = TicketStatus(from_status), TicketStatus(to_status)
    if not is_transition_allowed(from_status, to_status):
        raise InvalidTransitionError(from_status, to_status)
