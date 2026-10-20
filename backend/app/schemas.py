"""Pydantic schemas mirroring `openapi.yaml` components."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    PlainSerializer,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.models import DeviceType, EventKind
from app.services.phone import normalize_phone
from app.services.transitions import TicketStatus

# --- Field types (limits from spec §9.4, §9.3) --------------------------------

CustomerName = Annotated[str, StringConstraints(min_length=1, max_length=100)]
PhoneInput = Annotated[str, StringConstraints(max_length=20), AfterValidator(normalize_phone)]
Email = Annotated[EmailStr, StringConstraints(max_length=254)]
DeviceText = Annotated[str, StringConstraints(min_length=1, max_length=60)]
OptionalDeviceText = Annotated[str, StringConstraints(max_length=60)]
LongText = Annotated[str, StringConstraints(min_length=1, max_length=2000)]
OptionalLongText = Annotated[str, StringConstraints(max_length=2000)]
NoteText = Annotated[str, StringConstraints(min_length=1, max_length=1000)]
EstimatedCost = Annotated[
    Decimal,
    Field(ge=0, le=10_000_000, max_digits=10, decimal_places=2),
    # The contract uses a JSON number, not Pydantic's default string for Decimal.
    PlainSerializer(float, return_type=float, when_used="json"),
]


def _reject_null(value: Any) -> Any:
    if value is None:
        raise ValueError("Field may not be null.")
    return value


class InputModel(BaseModel):
    """Request bodies: unknown fields rejected (`additionalProperties: false`)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PatchModel(InputModel):
    """Partial updates: at least one field (`minProperties: 1`)."""

    @model_validator(mode="after")
    def _not_empty(self) -> "PatchModel":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided.")
        return self


class OutputModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Errors and health ---------------------------------------------------------


class ErrorBody(BaseModel):
    code: str
    message: str
    details: Any = None


class Error(BaseModel):
    error: ErrorBody


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["ok", "error"]


# --- Customers -----------------------------------------------------------------


class CustomerCreate(InputModel):
    name: CustomerName
    phone: PhoneInput
    email: Email | None = None


class CustomerUpdate(PatchModel):
    name: CustomerName | None = None
    phone: PhoneInput | None = None
    email: Email | None = None

    _non_nullable = field_validator("name", "phone", mode="before")(_reject_null)


class Customer(OutputModel):
    id: int
    name: str
    phone: str
    email: str | None
    created_at: datetime


class CustomerSummary(OutputModel):
    id: int
    name: str
    phone: str


class CustomerList(BaseModel):
    items: list[Customer]
    total: int


# --- Tickets -------------------------------------------------------------------


class TicketCreate(InputModel):
    customer_id: int = Field(ge=1)
    device_type: DeviceType
    brand: DeviceText
    model: OptionalDeviceText | None = None
    serial_number: OptionalDeviceText | None = None
    reported_issue: LongText
    diagnosis: OptionalLongText | None = None
    estimated_cost: EstimatedCost | None = None


class TicketUpdate(PatchModel):
    device_type: DeviceType | None = None
    brand: DeviceText | None = None
    model: OptionalDeviceText | None = None
    serial_number: OptionalDeviceText | None = None
    reported_issue: LongText | None = None
    diagnosis: OptionalLongText | None = None
    estimated_cost: EstimatedCost | None = None

    _non_nullable = field_validator("device_type", "brand", "reported_issue", mode="before")(
        _reject_null
    )


class Ticket(OutputModel):
    id: int
    customer_id: int
    customer: CustomerSummary
    device_type: DeviceType
    brand: str
    model: str | None
    serial_number: str | None
    reported_issue: str
    diagnosis: str | None
    estimated_cost: EstimatedCost | None
    status: TicketStatus
    tracking_code: str
    created_at: datetime
    updated_at: datetime


class TicketList(BaseModel):
    items: list[Ticket]
    total: int


class StatusChange(InputModel):
    to_status: TicketStatus
    note: NoteText | None = None

    _non_nullable = field_validator("note", mode="before")(_reject_null)


class NoteCreate(InputModel):
    note: NoteText


class TicketEvent(OutputModel):
    id: int
    ticket_id: int
    kind: EventKind
    from_status: TicketStatus | None
    to_status: TicketStatus | None
    note: str | None
    created_at: datetime


class TicketEventList(BaseModel):
    items: list[TicketEvent]
    total: int


# --- Dashboard -----------------------------------------------------------------


class StatusCounts(BaseModel):
    received: int
    diagnosing: int
    waiting_parts: int
    repairing: int
    ready: int
    delivered: int
    cancelled: int


class Dashboard(BaseModel):
    counts: StatusCounts
    stale_tickets: list[Ticket]


# --- Public (exact whitelist, spec §9.15) ----------------------------------------


class PublicTimelineEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: TicketStatus
    at: datetime


class PublicTracking(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tracking_code: str
    device_type: DeviceType
    brand: str
    model: str | None
    status: TicketStatus
    last_status_change_at: datetime
    timeline: list[PublicTimelineEntry]
