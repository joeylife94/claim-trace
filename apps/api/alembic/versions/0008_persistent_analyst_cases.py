"""Persistent analyst Case identity and document association.

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-10

D5-01 adds only workspace identity and references to existing documents. Source
text and provenance remain owned by the existing document/page tables.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "analyst_cases",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
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
        sa.CheckConstraint(
            "length(trim(title)) > 0",
            name="ck_analyst_cases_title_nonempty",
        ),
    )
    op.create_index(
        "ix_analyst_cases_created_at",
        "analyst_cases",
        ["created_at"],
    )

    op.create_table(
        "analyst_case_documents",
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column(
            "associated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["analyst_cases.id"],
            name="fk_analyst_case_documents_case_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_analyst_case_documents_document_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "case_id",
            "document_id",
            name="pk_analyst_case_documents",
        ),
    )
    op.create_index(
        "ix_analyst_case_documents_document_id",
        "analyst_case_documents",
        ["document_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_analyst_case_documents_document_id",
        table_name="analyst_case_documents",
    )
    op.drop_table("analyst_case_documents")
    op.drop_index(
        "ix_analyst_cases_created_at",
        table_name="analyst_cases",
    )
    op.drop_table("analyst_cases")
