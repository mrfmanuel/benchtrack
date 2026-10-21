"""Customer use cases (spec §4 F1, §9.1)."""

import re

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import schemas
from app.errors import ConflictError, NotFoundError
from app.models import Customer

_PHONE_SEPARATORS_RE = re.compile(r"[\s\-()]")


def _duplicate_phone(phone: str, existing_id: int) -> ConflictError:
    details = {"field": "phone", "existing_customer_id": existing_id}
    return ConflictError(f"A customer with phone {phone} already exists.", details)


def _id_with_phone(session: Session, phone: str) -> int | None:
    return session.scalar(select(Customer.id).where(Customer.phone == phone))


def list_customers(
    session: Session, q: str | None, limit: int, offset: int
) -> tuple[list[Customer], int]:
    query = select(Customer)
    if q:
        # Phones are stored normalized, so also match the query without separators.
        phone_q = _PHONE_SEPARATORS_RE.sub("", q) or q
        query = query.where(
            or_(
                Customer.name.icontains(q, autoescape=True),
                Customer.phone.icontains(phone_q, autoescape=True),
            )
        )
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = session.scalars(query.order_by(Customer.name, Customer.id).limit(limit).offset(offset))
    return list(items), total


def get_customer(session: Session, customer_id: int) -> Customer:
    customer = session.get(Customer, customer_id)
    if customer is None:
        raise NotFoundError(f"Customer {customer_id} not found.")
    return customer


def create_customer(session: Session, data: schemas.CustomerCreate) -> Customer:
    existing_id = _id_with_phone(session, data.phone)
    if existing_id is not None:
        raise _duplicate_phone(data.phone, existing_id)
    customer = Customer(name=data.name, phone=data.phone, email=data.email)
    session.add(customer)
    _commit_or_conflict(session, data.phone)
    return customer


def update_customer(session: Session, customer_id: int, data: schemas.CustomerUpdate) -> Customer:
    customer = get_customer(session, customer_id)
    changes = data.model_dump(exclude_unset=True)
    if "phone" in changes:
        existing_id = _id_with_phone(session, changes["phone"])
        if existing_id is not None and existing_id != customer_id:
            raise _duplicate_phone(changes["phone"], existing_id)
    for field, value in changes.items():
        setattr(customer, field, value)
    _commit_or_conflict(session, customer.phone)
    return customer


def _commit_or_conflict(session: Session, phone: str) -> None:
    """The unique constraint is the final guard against concurrent duplicates."""
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        # Another request committed the same phone first; report its ID like the pre-check.
        existing_id = _id_with_phone(session, phone)
        if existing_id is None:
            # No customer has the phone (there are no deletes in v1), so this was some other
            # integrity failure: let it surface as a 500 instead of a misleading conflict.
            raise
        raise _duplicate_phone(phone, existing_id) from exc
