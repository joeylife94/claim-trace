"""Alembic environment.

Migrations run synchronously against the same PostgreSQL instance the application
uses; the URL comes from application settings so credentials stay in the
environment rather than in ``alembic.ini``.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from claimtrace_api.core.config import get_settings
from claimtrace_api.db import element_models, models  # noqa: F401  (metadata registration)
from claimtrace_api.db.base import Base

config = context.config

if config.config_file_name is not None:
    # disable_existing_loggers defaults to True, which would switch off every
    # already-created claimtrace_api logger. That is invisible when Alembic runs
    # as its own process and silently fatal when it is driven in-process.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _database_url() -> str:
    """Resolve the migration target URL.

    An explicit override in ``config.attributes`` wins, which lets the test suite
    migrate a throwaway database. Attributes are used rather than a main option so
    the value skips ConfigParser interpolation and a '%' in a password is safe.
    """
    override = config.attributes.get("sqlalchemy_url")
    if override:
        return str(override)
    return get_settings().sqlalchemy_database_uri


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting to a database."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Apply migrations against a live connection."""
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _database_url()

    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
