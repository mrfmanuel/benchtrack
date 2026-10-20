from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app import schemas
from app.auth import require_staff
from app.deps import LimitParam, OffsetParam, QueryParam, SessionDep
from app.services import tickets as service
from app.services.transitions import TicketStatus

router = APIRouter(prefix="/api/tickets", tags=["Tickets"], dependencies=[Depends(require_staff)])


@router.get("", response_model=schemas.TicketList, operation_id="listTickets")
def list_tickets(
    session: SessionDep,
    customer_id: Annotated[int | None, Query(ge=1)] = None,
    status: TicketStatus | None = None,
    q: QueryParam = None,
    limit: LimitParam = 50,
    offset: OffsetParam = 0,
):
    items, total = service.list_tickets(
        session, status=status, customer_id=customer_id, q=q, limit=limit, offset=offset
    )
    return {"items": items, "total": total}


@router.post("", response_model=schemas.Ticket, status_code=201, operation_id="createTicket")
def create_ticket(data: schemas.TicketCreate, session: SessionDep):
    return service.create_ticket(session, data)


@router.get("/{ticket_id}", response_model=schemas.Ticket, operation_id="getTicket")
def get_ticket(ticket_id: int, session: SessionDep):
    return service.get_ticket(session, ticket_id)


@router.patch("/{ticket_id}", response_model=schemas.Ticket, operation_id="updateTicket")
def update_ticket(ticket_id: int, data: schemas.TicketUpdate, session: SessionDep):
    return service.update_ticket(session, ticket_id, data)


@router.post(
    "/{ticket_id}/status", response_model=schemas.Ticket, operation_id="changeTicketStatus"
)
def change_status(ticket_id: int, data: schemas.StatusChange, session: SessionDep):
    return service.change_status(session, ticket_id, data)


@router.post(
    "/{ticket_id}/notes",
    response_model=schemas.TicketEvent,
    status_code=201,
    operation_id="addTicketNote",
)
def add_note(ticket_id: int, data: schemas.NoteCreate, session: SessionDep):
    return service.add_note(session, ticket_id, data)


@router.get(
    "/{ticket_id}/events", response_model=schemas.TicketEventList, operation_id="listTicketEvents"
)
def list_events(ticket_id: int, session: SessionDep):
    events = service.list_events(session, ticket_id)
    return {"items": events, "total": len(events)}
