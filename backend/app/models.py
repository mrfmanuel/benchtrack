"""SQLAlchemy models (engine-agnostic)."""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, UTCDateTime, utcnow


class DeviceType(StrEnum):
    LAPTOP = "laptop"
    DESKTOP = "desktop"
    PHONE = "phone"
    TABLET = "tablet"
    PRINTER = "printer"
    OTHER = "other"


class EventKind(StrEnum):
    STATUS = "status"
    NOTE = "note"


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), index=True)
    phone: Mapped[str] = mapped_column(String(20), unique=True)
    email: Mapped[str | None] = mapped_column(String(254))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    tickets: Mapped[list["Ticket"]] = relationship(back_populates="customer")


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    device_type: Mapped[str] = mapped_column(String(20))
    brand: Mapped[str] = mapped_column(String(60))
    model: Mapped[str | None] = mapped_column(String(60))
    serial_number: Mapped[str | None] = mapped_column(String(60))
    reported_issue: Mapped[str] = mapped_column(String(2000))
    diagnosis: Mapped[str | None] = mapped_column(String(2000))
    estimated_cost: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    status: Mapped[str] = mapped_column(String(20), index=True)
    tracking_code: Mapped[str] = mapped_column(String(8), unique=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)

    customer: Mapped[Customer] = relationship(back_populates="tickets", lazy="joined")
    events: Mapped[list["TicketEvent"]] = relationship(
        back_populates="ticket",
        order_by="[TicketEvent.created_at, TicketEvent.id]",
    )


class TicketEvent(Base):
    """Timeline entry: `kind=status` (status change) or `kind=note` (statuses null)."""

    __tablename__ = "ticket_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), index=True)
    kind: Mapped[str] = mapped_column(String(10))
    from_status: Mapped[str | None] = mapped_column(String(20))
    to_status: Mapped[str | None] = mapped_column(String(20))
    note: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    ticket: Mapped[Ticket] = relationship(back_populates="events")
