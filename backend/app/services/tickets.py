"""Ticket use cases: CRUD, status workflow, notes, public tracking (spec §4 F2–F4, §9)."""

import logging
from datetime import datetime

from sqlalchemy import exists, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import schemas
from app.db import utcnow
from app.errors import FieldValidationError, NotFoundError, TicketFinalError
from app.models import Customer, EventKind, Ticket, TicketEvent
from app.services import tracking_codes
from app.services.tracking_codes import TrackingCodeCollision, create_with_unique_code
from app.services.transitions import FINAL_STATUSES, TicketStatus, validate_transition

logger = logging.getLogger(__name__)

# Public lookups longer than this cannot be a code (contract: maxLength 20).
_MAX_PUBLIC_CODE_INPUT = 20


def list_tickets(
    session: Session,
    *,
    status: TicketStatus | None,
    customer_id: int | None,
    q: str | None,
    limit: int,
    offset: int,
) -> tuple[list[Ticket], int]:
    query = select(Ticket).join(Ticket.customer)
    if status is not None:
        query = query.where(Ticket.status == status)
    if customer_id is not None:
        query = query.where(Ticket.customer_id == customer_id)
    if q:
        query = query.where(
            or_(
                Ticket.tracking_code.icontains(q, autoescape=True),
                Customer.name.icontains(q, autoescape=True),
                Ticket.brand.icontains(q, autoescape=True),
                Ticket.model.icontains(q, autoescape=True),
            )
        )
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = session.scalars(
        query.order_by(Ticket.created_at.desc(), Ticket.id.desc()).limit(limit).offset(offset)
    )
    return list(items), total


def get_ticket(session: Session, ticket_id: int) -> Ticket:
    ticket = session.get(Ticket, ticket_id)
    if ticket is None:
        raise NotFoundError(f"Ticket {ticket_id} not found.")
    return ticket


def create_ticket(session: Session, data: schemas.TicketCreate) -> Ticket:
    """Create a `received` ticket plus its initial status event, with a unique code."""
    if session.get(Customer, data.customer_id) is None:
        raise FieldValidationError("customer_id", f"Customer {data.customer_id} does not exist.")
    fields = data.model_dump()

    def try_create(code: str) -> Ticket:
        now = utcnow()
        ticket = Ticket(
            **fields,
            status=TicketStatus.RECEIVED,
            tracking_code=code,
            created_at=now,
            updated_at=now,
        )
        ticket.events.append(
            TicketEvent(
                kind=EventKind.STATUS,
                from_status=None,
                to_status=TicketStatus.RECEIVED,
                created_at=now,
            )
        )
        session.add(ticket)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            if session.scalar(select(exists().where(Ticket.tracking_code == code))):
                raise TrackingCodeCollision(code) from None
            raise
        return ticket

    # Looked up at call time so tests can substitute the generator.
    ticket = create_with_unique_code(try_create, generate=tracking_codes.generate_tracking_code)
    logger.info("Created ticket %s for customer %s", ticket.tracking_code, ticket.customer_id)
    return ticket


def _ensure_not_final(ticket: Ticket) -> None:
    if ticket.status in FINAL_STATUSES:
        raise TicketFinalError(
            f"Ticket {ticket.tracking_code} is {ticket.status} and cannot be edited."
        )


def update_ticket(session: Session, ticket_id: int, data: schemas.TicketUpdate) -> Ticket:
    ticket = get_ticket(session, ticket_id)
    _ensure_not_final(ticket)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(ticket, field, value)
    ticket.updated_at = utcnow()
    session.commit()
    return ticket


def change_status(session: Session, ticket_id: int, data: schemas.StatusChange) -> Ticket:
    ticket = get_ticket(session, ticket_id)
    _ensure_not_final(ticket)
    validate_transition(ticket.status, data.to_status)
    now = utcnow()
    session.add(
        TicketEvent(
            ticket_id=ticket.id,
            kind=EventKind.STATUS,
            from_status=ticket.status,
            to_status=data.to_status,
            note=data.note,
            created_at=now,
        )
    )
    ticket.status = data.to_status
    ticket.updated_at = now
    session.commit()
    return ticket


def add_note(session: Session, ticket_id: int, data: schemas.NoteCreate) -> TicketEvent:
    """Notes are allowed on final tickets too (spec §9.7)."""
    ticket = get_ticket(session, ticket_id)
    now = utcnow()
    event = TicketEvent(ticket_id=ticket.id, kind=EventKind.NOTE, note=data.note, created_at=now)
    session.add(event)
    ticket.updated_at = now
    session.commit()
    return event


def list_events(session: Session, ticket_id: int) -> list[TicketEvent]:
    get_ticket(session, ticket_id)
    return list(
        session.scalars(
            select(TicketEvent)
            .where(TicketEvent.ticket_id == ticket_id)
            .order_by(TicketEvent.created_at, TicketEvent.id)
        )
    )


def track(session: Session, raw_code: str) -> schemas.PublicTracking:
    """Public lookup. Builds the response field by field from the §9.15 whitelist."""
    code = (
        tracking_codes.normalize_tracking_code(raw_code)
        if len(raw_code) <= _MAX_PUBLIC_CODE_INPUT
        else None
    )
    ticket = session.scalar(select(Ticket).where(Ticket.tracking_code == code)) if code else None
    if ticket is None:
        # Never log the raw input: without the BT- prefix the masking filter cannot spot it.
        logger.info("Public tracking lookup: not found")
        raise NotFoundError("No repair found for this tracking code.")

    status_events = [e for e in ticket.events if e.kind == EventKind.STATUS]
    last_change: datetime = status_events[-1].created_at if status_events else ticket.created_at
    logger.info("Public tracking lookup for %s: found", ticket.tracking_code)
    return schemas.PublicTracking(
        tracking_code=ticket.tracking_code,
        device_type=ticket.device_type,
        brand=ticket.brand,
        model=ticket.model,
        status=ticket.status,
        last_status_change_at=last_change,
        timeline=[
            schemas.PublicTimelineEntry(status=e.to_status, at=e.created_at) for e in status_events
        ],
    )
