"""Append-only human review records for element decomposition.

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "element_decomposition_reviews",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["element_decomposition_runs.id"],
            name="fk_element_decomposition_reviews_run_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "status IN ('accepted', 'needs_correction')",
            name="ck_element_decomposition_reviews_status",
        ),
    )
    op.create_index(
        "ix_element_decomposition_reviews_run_id",
        "element_decomposition_reviews",
        ["run_id"],
    )


def downgrade() -> None:
    op.drop_table("element_decomposition_reviews")
