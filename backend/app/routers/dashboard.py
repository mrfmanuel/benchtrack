from fastapi import APIRouter, Depends

from app import schemas
from app.auth import require_staff
from app.deps import SessionDep
from app.services import dashboard as service

router = APIRouter(prefix="/api", tags=["Dashboard"], dependencies=[Depends(require_staff)])


@router.get("/dashboard", response_model=schemas.Dashboard, operation_id="getDashboard")
def get_dashboard(session: SessionDep):
    return {
        "counts": service.status_counts(session),
        "stale_tickets": service.stale_tickets(session),
    }
