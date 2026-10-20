"""Seed script: fictional, idempotent, covers all statuses and stale tickets."""

from sqlalchemy import func, select

from app.models import Customer, Ticket
from app.seed import seed
from app.services.transitions import TicketStatus


def test_seed_is_idempotent_and_covers_dashboard(app, client):
    with app.state.session_factory() as session:
        assert seed(session) == (6, 12)
        assert seed(session) == (0, 0)
        assert session.scalar(select(func.count()).select_from(Customer)) == 6
        assert session.scalar(select(func.count()).select_from(Ticket)) == 12

    dashboard = client.get("/api/dashboard").json()
    assert set(dashboard["counts"]) == {s.value for s in TicketStatus}
    assert all(count >= 1 for count in dashboard["counts"].values())
    assert len(dashboard["stale_tickets"]) >= 2

    for ticket in client.get("/api/tickets", params={"limit": 200}).json()["items"]:
        events = client.get(f"/api/tickets/{ticket['id']}/events").json()["items"]
        assert events[0]["from_status"] is None and events[0]["to_status"] == "received"
        assert events[-1]["to_status"] == ticket["status"]
        assert events[-1]["created_at"] == ticket["updated_at"]
