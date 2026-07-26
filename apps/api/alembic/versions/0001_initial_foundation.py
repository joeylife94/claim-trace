"""Initial foundation: pgvector extension and app_metadata table

Revision ID: 0001
Revises:
Create Date: 2026-07-25

Enables the pgvector extension so later phases can add embedding columns without a
schema-owner migration, and creates a single infrastructure table that proves the
migration pipeline works end to end. No domain tables are created here.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "app_metadata",
        sa.Column("key", sa.String(length=128), primary_key=True, nullable=False),
        sa.Column("value", sa.String(length=512), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.execute(
        """
        INSERT INTO app_metadata (key, value)
        VALUES ('schema_phase', 'phase-1-foundation')
        ON CONFLICT (key) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_table("app_metadata")
    # The vector extension is left in place: other databases objects may depend on
    # it and dropping a shared extension is not safe to automate.
