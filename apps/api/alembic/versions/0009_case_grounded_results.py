"""Persist bounded grounded-analysis snapshots under analyst Cases.

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-11

D5-02 stores reviewer-visible analysis state plus provenance references. Source
text remains owned exclusively by document_pages; persisted locator snapshots
refer back to that canonical coordinate system and are re-resolved on read.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "analyst_case_grounded_results",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("query", sa.String(length=512), nullable=False),
        sa.Column("request_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("result_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["analyst_cases.id"],
            name="fk_case_grounded_results_case_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("length(trim(query)) > 0", name="ck_case_grounded_results_query_nonempty"),
    )
    op.create_index(
        "ix_case_grounded_results_case_created",
        "analyst_case_grounded_results",
        ["case_id", "created_at", "id"],
    )

    op.create_table(
        "analyst_case_grounded_evidence",
        sa.Column("result_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_id", sa.String(length=16), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("locator_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["result_id"],
            ["analyst_case_grounded_results.id"],
            name="fk_case_grounded_evidence_result_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_case_grounded_evidence_document_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "result_id",
            "evidence_id",
            name="pk_case_grounded_evidence",
        ),
    )
    op.create_index(
        "ix_case_grounded_evidence_document_id",
        "analyst_case_grounded_evidence",
        ["document_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_case_grounded_evidence_document_id", table_name="analyst_case_grounded_evidence")
    op.drop_table("analyst_case_grounded_evidence")
    op.drop_index("ix_case_grounded_results_case_created", table_name="analyst_case_grounded_results")
    op.drop_table("analyst_case_grounded_results")
