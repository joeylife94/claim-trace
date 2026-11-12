"""Alembic autogenerate must not propose dropping the hand-managed tables.

Migrations 0007-0009 create seven tables with raw SQL and no ORM model. Autogenerate
diffs ``Base.metadata`` against the live schema, so without a filter it would emit
``drop_table`` for all of them in the next ``alembic revision --autogenerate``.

The test drives the real ``env.py`` (through ``command.revision(autogenerate=True)``
against a throwaway copy of the script directory), so it covers the filter exactly as
it is configured there rather than a re-implementation of it.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest
import sqlalchemy as sa

from tests.conftest import API_ROOT

pytestmark = pytest.mark.integration

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


def _autogenerate(url: str, scratch: Path) -> str:
    """Return the text of the revision autogenerate would write for ``url``."""
    from alembic import command
    from alembic.config import Config

    scripts = scratch / "alembic"
    shutil.copytree(API_ROOT / "alembic", scripts, ignore=shutil.ignore_patterns("__pycache__"))
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(scripts))
    config.attributes["sqlalchemy_url"] = url

    before = set((scripts / "versions").glob("*.py"))
    command.revision(config, message="d7_probe", autogenerate=True)
    created = set((scripts / "versions").glob("*.py")) - before
    assert len(created) == 1, f"expected one probe revision, got {sorted(created)}"
    return created.pop().read_text(encoding="utf-8")


def _upgrade_ops(revision_text: str) -> str:
    match = re.search(r"def upgrade\(\).*?(?=\ndef downgrade\(\))", revision_text, re.DOTALL)
    assert match, revision_text
    return match.group(0)


def test_autogenerate_proposes_no_removal_of_hand_managed_tables(
    integration_database_url: str, tmp_path: Path
) -> None:
    upgrade = _upgrade_ops(_autogenerate(integration_database_url, tmp_path))

    # Any operation naming one of the tables counts, not only ``drop_table``: the
    # table's indexes are dropped through separate ``drop_index`` calls.
    touched = sorted(
        table for table in HAND_MANAGED_TABLES if re.search(rf"""['"]{table}['"]""", upgrade)
    )
    assert not touched, (
        f"autogenerate would drop hand-managed tables {touched}; "
        f"full proposed upgrade():\n{upgrade}"
    )


def test_hand_managed_tables_exist_in_migrated_database(integration_database_url: str) -> None:
    """Guards the allow-list: a renamed or removed table must be dropped from it."""
    engine = sa.create_engine(integration_database_url)
    try:
        present = set(sa.inspect(engine).get_table_names())
    finally:
        engine.dispose()
    assert present >= HAND_MANAGED_TABLES, sorted(HAND_MANAGED_TABLES - present)
