from fastapi import APIRouter, Depends

from app import schemas
from app.deps import SessionDep, public_rate_limit
from app.services import tickets as service

# No auth: customers only have the tracking code. Rate-limited against code guessing.
router = APIRouter(prefix="/api/public", tags=["Public"], dependencies=[Depends(public_rate_limit)])


@router.get(
    "/track/{tracking_code}", response_model=schemas.PublicTracking, operation_id="trackTicket"
)
def track_ticket(tracking_code: str, session: SessionDep):
    return service.track(session, tracking_code)
