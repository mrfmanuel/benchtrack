from fastapi import APIRouter, Depends

from app import schemas
from app.auth import require_staff
from app.deps import LimitParam, OffsetParam, QueryParam, SessionDep
from app.services import customers as service

router = APIRouter(
    prefix="/api/customers", tags=["Customers"], dependencies=[Depends(require_staff)]
)


@router.get("", response_model=schemas.CustomerList, operation_id="listCustomers")
def list_customers(
    session: SessionDep, q: QueryParam = None, limit: LimitParam = 50, offset: OffsetParam = 0
):
    items, total = service.list_customers(session, q, limit, offset)
    return {"items": items, "total": total}


@router.post("", response_model=schemas.Customer, status_code=201, operation_id="createCustomer")
def create_customer(data: schemas.CustomerCreate, session: SessionDep):
    return service.create_customer(session, data)


@router.get("/{customer_id}", response_model=schemas.Customer, operation_id="getCustomer")
def get_customer(customer_id: int, session: SessionDep):
    return service.get_customer(session, customer_id)


@router.patch("/{customer_id}", response_model=schemas.Customer, operation_id="updateCustomer")
def update_customer(customer_id: int, data: schemas.CustomerUpdate, session: SessionDep):
    return service.update_customer(session, customer_id, data)
