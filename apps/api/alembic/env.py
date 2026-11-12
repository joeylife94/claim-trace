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
from claimtrace_api.db import element_models, models, review_models  # noqa: F401
from claimtrace_api.db.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata

# Tables created by hand-written migrations (0007-0009) and queried with raw SQL; they
# have no ORM model on purpose. Autogenerate diffs the live schema against
# ``Base.metadata``, so without this it would propose ``drop_table`` for every one of
# them (and their indexes). An explicit list rather than "ignore whatever the metadata
# lacks": a blanket filter would also hide a table that is genuinely orphaned. If one of
# these gains an ORM model, remove it here and autogenerate will compare it normally.
HAND_MANAGED_TABLES = frozenset(
    {
        "description_derivation_runs",
        "description_segments",
        "description_search_records",
        "analyst_cases",
        "analyst_case_documents",
        "analyst_case_results",
        "analyst_case_evidence",
    }
)


def include_object(object_, name, type_, reflected, compare_to):  # noqa: ANN001, ANN201
    """Leave hand-managed tables, and the indexes on them, out of autogenerate."""
    if type_ == "table" and reflected and compare_to is None:
        return name not in HAND_MANAGED_TABLES
    if type_ == "index" and reflected and compare_to is None:
        return getattr(getattr(object_, "table", None), "name", None) not in HAND_MANAGED_TABLES
    return True


def _database_url() -> str:
    override = config.attributes.get("sqlalchemy_url")
    if override:
        return str(override)
    return get_settings().sqlalchemy_database_uri


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _database_url()

    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
