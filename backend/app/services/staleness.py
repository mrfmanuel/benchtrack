"""Stale ticket detection (spec §4 F5, §9.21)."""

from datetime import UTC, datetime, timedelta

from app.services.transitions import OPEN_STATUSES, TicketStatus

STALE_AFTER = timedelta(days=7)


def as_utc(value: datetime) -> datetime:
    """Return `value` in UTC; naive datetimes are assumed to already be UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def stale_cutoff(now: datetime) -> datetime:
    """Open tickets with `updated_at` strictly before this instant are stale."""
    return as_utc(now) - STALE_AFTER


def is_stale(status: TicketStatus | str, updated_at: datetime, now: datetime | None = None) -> bool:
    if TicketStatus(status) not in OPEN_STATUSES:
        return False
    now = now if now is not None else datetime.now(UTC)
    return as_utc(updated_at) < stale_cutoff(now)
