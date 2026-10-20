"""Seed fictional demo data. Idempotent: `uv run python -m app.seed`.

All names, phones (`+506 0000-xxxx`, not a valid Costa Rican range) and emails
(`example.com`) are fictional. Seeded tracking codes are fixed (`BT-DEM..`) so they can
be found again and skipped on re-runs.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import Base, create_db_engine, make_session_factory, utcnow
from app.models import Customer, DeviceType, EventKind, Ticket, TicketEvent
from app.services.transitions import TicketStatus, validate_transition

S = TicketStatus

CUSTOMERS = [
    ("Ana Mora", "+50600000101", "ana.mora@example.com"),
    ("Luis Vargas", "+50600000102", None),
    ("Sofía Jiménez", "+50600000103", "sofia.jimenez@example.com"),
    ("Carlos Rojas", "+50600000104", None),
    ("María Solano", "+50600000105", "maria.solano@example.org"),
    ("Diego Castro", "+50600000106", None),
]


@dataclass(frozen=True)
class DemoTicket:
    code: str
    phone: str
    device_type: DeviceType
    brand: str
    model: str | None
    issue: str
    path: list[TicketStatus]  # statuses after `received`
    days_ago: int  # creation time
    idle_days: int  # days since last update (≥ 8 on open tickets → stale)
    diagnosis: str | None = None
    cost: Decimal | None = None


TICKETS = [
    DemoTicket(
        "BT-DEM22",
        "+50600000101",
        DeviceType.LAPTOP,
        "Lenovo",
        "ThinkPad T14",
        "Does not turn on after a coffee spill.",
        [],
        1,
        1,
    ),
    DemoTicket(
        "BT-DEM23",
        "+50600000102",
        DeviceType.PHONE,
        "Samsung",
        "Galaxy A54",
        "Cracked screen.",
        [S.DIAGNOSING],
        3,
        2,
        "Display and digitizer need replacement.",
        Decimal("65000.00"),
    ),
    DemoTicket(
        "BT-DEM24",
        "+50600000103",
        DeviceType.DESKTOP,
        "Dell",
        "OptiPlex 7090",
        "Random reboots under load.",
        [S.DIAGNOSING, S.WAITING_PARTS],
        20,
        12,
        "Failing power supply.",
        Decimal("38000.00"),
    ),
    DemoTicket(
        "BT-DEM25",
        "+50600000104",
        DeviceType.PRINTER,
        "Epson",
        "EcoTank L3250",
        "Paper jam on every print.",
        [S.DIAGNOSING, S.WAITING_PARTS],
        6,
        3,
        "Worn pickup roller.",
        Decimal("12000.00"),
    ),
    DemoTicket(
        "BT-DEM26",
        "+50600000105",
        DeviceType.TABLET,
        "Apple",
        "iPad 9th gen",
        "Battery drains in two hours.",
        [S.DIAGNOSING, S.REPAIRING],
        15,
        9,
        "Battery health 61%.",
        Decimal("42000.00"),
    ),
    DemoTicket(
        "BT-DEM27",
        "+50600000106",
        DeviceType.LAPTOP,
        "HP",
        "Pavilion 15",
        "Keyboard keys not responding.",
        [S.DIAGNOSING, S.REPAIRING],
        4,
        1,
        "Keyboard ribbon cable loose.",
        Decimal("15000.00"),
    ),
    DemoTicket(
        "BT-DEM28",
        "+50600000101",
        DeviceType.OTHER,
        "Nintendo",
        "Switch",
        "Joy-Con drift.",
        [S.DIAGNOSING, S.REPAIRING, S.READY],
        7,
        2,
        "Replaced analog stick.",
        Decimal("18000.00"),
    ),
    DemoTicket(
        "BT-DEM29",
        "+50600000103",
        DeviceType.LAPTOP,
        "Acer",
        "Aspire 5",
        "Overheating and fan noise.",
        [S.DIAGNOSING, S.REPAIRING, S.READY],
        25,
        10,
        "Cleaned fan, new thermal paste.",
        Decimal("20000.00"),
    ),
    DemoTicket(
        "BT-DEM2A",
        "+50600000102",
        DeviceType.DESKTOP,
        "Custom build",
        None,
        "No video output.",
        [S.DIAGNOSING, S.WAITING_PARTS, S.REPAIRING, S.READY, S.DELIVERED],
        30,
        18,
        "Dead graphics card.",
        Decimal("145000.00"),
    ),
    DemoTicket(
        "BT-DEM2B",
        "+50600000104",
        DeviceType.PHONE,
        "Motorola",
        "Moto G84",
        "Does not charge.",
        [S.DIAGNOSING, S.REPAIRING, S.READY, S.DELIVERED],
        12,
        5,
        "Charging port replaced.",
        Decimal("22000.00"),
    ),
    DemoTicket(
        "BT-DEM2C",
        "+50600000105",
        DeviceType.PRINTER,
        "HP",
        "LaserJet M111w",
        "Prints blank pages.",
        [S.DIAGNOSING, S.CANCELLED],
        40,
        35,
        "Fuser unit failure; repair cost exceeds device value.",
        Decimal("60000.00"),
    ),
    DemoTicket(
        "BT-DEM2D",
        "+50600000106",
        DeviceType.LAPTOP,
        "Asus",
        "VivoBook 14",
        "Wants an SSD upgrade.",
        [S.CANCELLED],
        9,
        8,
    ),
]


def _timestamps(created: datetime, last: datetime, steps: int) -> list[datetime]:
    """`steps` evenly spaced timestamps after `created`, the last one at `last`."""
    if steps == 0:
        return []
    gap = (last - created) / steps
    return [created + gap * (i + 1) for i in range(steps)]


def _seed_ticket(session: Session, demo: DemoTicket, customer: Customer, now: datetime) -> None:
    created = now - timedelta(days=demo.days_ago)
    last = now - timedelta(days=demo.idle_days)
    ticket = Ticket(
        customer_id=customer.id,
        device_type=demo.device_type,
        brand=demo.brand,
        model=demo.model,
        reported_issue=demo.issue,
        diagnosis=demo.diagnosis,
        estimated_cost=demo.cost,
        status=S.RECEIVED,
        tracking_code=demo.code,
        created_at=created,
        updated_at=created,
    )
    ticket.events.append(
        TicketEvent(kind=EventKind.STATUS, to_status=S.RECEIVED, created_at=created)
    )
    for to_status, at in zip(demo.path, _timestamps(created, last, len(demo.path)), strict=True):
        validate_transition(ticket.status, to_status)  # seeds must follow the workflow too
        ticket.events.append(
            TicketEvent(
                kind=EventKind.STATUS, from_status=ticket.status, to_status=to_status, created_at=at
            )
        )
        ticket.status = to_status
        ticket.updated_at = at
    session.add(ticket)


def seed(session: Session, now: datetime | None = None) -> tuple[int, int]:
    """Insert missing demo customers and tickets. Returns (customers, tickets) added."""
    now = now or utcnow()
    added_customers = added_tickets = 0
    by_phone: dict[str, Customer] = {}
    for name, phone, email in CUSTOMERS:
        customer = session.scalar(select(Customer).where(Customer.phone == phone))
        if customer is None:
            customer = Customer(
                name=name, phone=phone, email=email, created_at=now - timedelta(days=45)
            )
            session.add(customer)
            added_customers += 1
        by_phone[phone] = customer
    session.flush()

    for demo in TICKETS:
        if session.scalar(select(Ticket.id).where(Ticket.tracking_code == demo.code)) is None:
            _seed_ticket(session, demo, by_phone[demo.phone], now)
            added_tickets += 1
    session.commit()
    return added_customers, added_tickets


def main() -> None:
    settings = get_settings()
    engine = create_db_engine(settings.database_url)
    Base.metadata.create_all(engine)
    with make_session_factory(engine)() as session:
        customers, tickets = seed(session)
    engine.dispose()
    print(f"Seed complete: {customers} customers and {tickets} tickets added.")


if __name__ == "__main__":
    main()
