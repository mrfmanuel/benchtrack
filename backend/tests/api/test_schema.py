"""Schema ownership: Alembic creates tables, the app never does (fast SQLite checks).

The same checks run against PostgreSQL in tests/integration/.
"""

from sqlalchemy import inspect
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.db import create_db_engine
from app.main import create_app
from tests.alembic_helpers import downgrade, schema_diff, upgrade
from tests.api.conftest import STAFF_TOKEN

TABLES = {"customers", "tickets", "ticket_events"}


def test_app_startup_does_not_create_tables():
    engine = create_db_engine("sqlite://", poolclass=StaticPool)
    create_app(Settings(_env_file=None, staff_token=STAFF_TOKEN), engine=engine)
    assert inspect(engine).get_table_names() == []
    engine.dispose()


def test_sqlite_migrations_match_models_and_round_trip(tmp_path):
    url = f"sqlite:///{(tmp_path / 'migrations.db').as_posix()}"
    engine = create_db_engine(url)

    upgrade(url)
    assert set(inspect(engine).get_table_names()) == TABLES | {"alembic_version"}
    assert schema_diff(engine) == []

    downgrade(url)
    assert set(inspect(engine).get_table_names()) == {"alembic_version"}

    upgrade(url)
    assert schema_diff(engine) == []
    engine.dispose()
