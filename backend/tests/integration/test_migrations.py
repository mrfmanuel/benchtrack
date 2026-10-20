"""Alembic migrations on PostgreSQL."""

import pytest
from sqlalchemy import inspect, text

from tests.alembic_helpers import downgrade, schema_diff, upgrade

pytestmark = pytest.mark.integration

TABLES = {"customers", "tickets", "ticket_events"}


def test_upgrade_head_on_empty_database(engine, database_url):
    assert inspect(engine).get_table_names() == []
    upgrade(database_url)

    inspector = inspect(engine)
    assert set(inspector.get_table_names()) == TABLES | {"alembic_version"}
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version"))


def test_constraint_names_follow_the_naming_convention(migrated_engine):
    inspector = inspect(migrated_engine)
    assert inspector.get_pk_constraint("tickets")["name"] == "pk_tickets"
    assert {u["name"] for u in inspector.get_unique_constraints("customers")} == {
        "uq_customers_phone"
    }
    assert {u["name"] for u in inspector.get_unique_constraints("tickets")} == {
        "uq_tickets_tracking_code"
    }
    assert {f["name"] for f in inspector.get_foreign_keys("ticket_events")} == {
        "fk_ticket_events_ticket_id_tickets"
    }
    # PostgreSQL also reports the index backing each unique constraint; skip those.
    indexes = inspector.get_indexes("tickets")
    assert {i["name"] for i in indexes if "duplicates_constraint" not in i} == {
        "ix_tickets_created_at",
        "ix_tickets_customer_id",
        "ix_tickets_status",
        "ix_tickets_updated_at",
    }


def test_autogenerate_finds_no_differences(migrated_engine):
    assert schema_diff(migrated_engine) == []


def test_downgrade_base_and_upgrade_again(migrated_engine, database_url):
    downgrade(database_url)
    assert set(inspect(migrated_engine).get_table_names()) == {"alembic_version"}

    upgrade(database_url)
    assert set(inspect(migrated_engine).get_table_names()) == TABLES | {"alembic_version"}
    assert schema_diff(migrated_engine) == []
