"""Dashboard: counts per status and stale tickets (spec §4 F5, §9.21)."""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import utcnow
from app.models import Ticket
from app.services.staleness import stale_cutoff
from app.services.transitions import OPEN_STATUSES, TicketStatus


def status_counts(session: Session) -> dict[str, int]:
    counts = {status.value: 0 for status in TicketStatus}
    rows = session.execute(select(Ticket.status, func.count()).group_by(Ticket.status))
    for status, count in rows:
        counts[status] = count
    return counts


def stale_tickets(session: Session, now: datetime | None = None) -> list[Ticket]:
    """Open tickets with `updated_at` older than 7 × 24 h, oldest first."""
    cutoff = stale_cutoff(now or utcnow())
    return list(
        session.scalars(
            select(Ticket)
            .where(Ticket.status.in_(OPEN_STATUSES), Ticket.updated_at < cutoff)
            .order_by(Ticket.updated_at, Ticket.id)
        )
    )
