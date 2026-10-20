"""Alembic environment: URL from app settings, metadata from app.models."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool

import app.models  # noqa: F401  (registers all tables on Base.metadata)
from app.config import DatabaseSettings, normalize_database_url
from app.db import Base, UTCDateTime, create_db_engine

config = context.config

# Programmatic callers (tests) pass the URL via attributes and keep their own logging.
if config.config_file_name is not None and not config.attributes.get("skip_logging_config"):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _database_url() -> str:
    url = config.attributes.get("database_url")
    return normalize_database_url(url) if url else DatabaseSettings().database_url


def _render_item(type_: str, obj: object, autogen_context: object) -> str | bool:
    # Render our TypeDecorator as its plain implementation so migrations don't import app code.
    if type_ == "type" and isinstance(obj, UTCDateTime):
        return "sa.DateTime()"
    return False


_OPTIONS = {
    "target_metadata": target_metadata,
    "compare_type": True,
    "render_item": _render_item,
    "render_as_batch": True,  # SQLite cannot ALTER most things; batch mode recreates tables
}


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(), literal_binds=True, dialect_opts={"paramstyle": "named"}, **_OPTIONS
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_db_engine(_database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, **_OPTIONS)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
