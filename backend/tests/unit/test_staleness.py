"""Stale ticket detection (spec §4 F5, §9.10, §9.21)."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.services.staleness import STALE_AFTER, is_stale, stale_cutoff
from app.services.transitions import TicketStatus

NOW = datetime(2026, 10, 20, 12, 0, 0, tzinfo=UTC)
WEEK = timedelta(days=7)
OPEN = [
    TicketStatus.RECEIVED,
    TicketStatus.DIAGNOSING,
    TicketStatus.WAITING_PARTS,
    TicketStatus.REPAIRING,
    TicketStatus.READY,
]
FINAL = [TicketStatus.DELIVERED, TicketStatus.CANCELLED]


def test_threshold_is_seven_times_24_hours():
    assert timedelta(hours=7 * 24) == STALE_AFTER


@pytest.mark.parametrize("status", OPEN, ids=lambda s: s.value)
def test_open_ticket_older_than_threshold_is_stale(status):
    assert is_stale(status, NOW - WEEK - timedelta(seconds=1), now=NOW) is True


@pytest.mark.parametrize("status", OPEN, ids=lambda s: s.value)
def test_open_ticket_exactly_at_threshold_is_not_stale(status):
    assert is_stale(status, NOW - WEEK, now=NOW) is False


@pytest.mark.parametrize("status", OPEN, ids=lambda s: s.value)
def test_recently_updated_open_ticket_is_not_stale(status):
    assert is_stale(status, NOW - timedelta(days=1), now=NOW) is False


def test_acceptance_scenario_eight_days_is_stale():
    assert is_stale(TicketStatus.WAITING_PARTS, NOW - timedelta(days=8), now=NOW) is True


@pytest.mark.parametrize("status", FINAL, ids=lambda s: s.value)
def test_final_tickets_are_never_stale(status):
    assert is_stale(status, NOW - timedelta(days=365), now=NOW) is False


def test_accepts_plain_string_status():
    assert is_stale("repairing", NOW - timedelta(days=8), now=NOW) is True
    assert is_stale("delivered", NOW - timedelta(days=8), now=NOW) is False


def test_naive_datetimes_are_treated_as_utc():
    naive_now = NOW.replace(tzinfo=None)
    assert is_stale(TicketStatus.READY, naive_now - timedelta(days=8), now=NOW) is True
    assert is_stale(TicketStatus.READY, NOW - timedelta(days=8), now=naive_now) is True


def test_other_timezones_are_compared_in_utc():
    costa_rica = timezone(timedelta(hours=-6))
    # 7 days + 1 s before NOW, expressed in UTC-6.
    updated = (NOW - WEEK - timedelta(seconds=1)).astimezone(costa_rica)
    assert is_stale(TicketStatus.READY, updated, now=NOW) is True


def test_default_now_is_current_utc_time():
    assert is_stale(TicketStatus.READY, datetime.now(UTC) - timedelta(days=8)) is True
    assert is_stale(TicketStatus.READY, datetime.now(UTC)) is False


def test_stale_cutoff_for_db_queries():
    # Stale means updated_at < cutoff (strictly).
    assert stale_cutoff(NOW) == NOW - WEEK
    assert stale_cutoff(NOW).tzinfo is not None
