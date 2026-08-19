"""Versioned claim element decomposition tables.

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-19

Machine decomposition remains separate from future human-review state. One claim
has at most one run for one parser name/version, making the persistence identity
explicit and database-enforced.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "element_decomposition_runs",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("claim_id", sa.Uuid(), nullable=False),
        sa.Column("parser_name", sa.String(length=64), nullable=False),
        sa.Column("parser_version", sa.String(length=32), nullable=False),
        sa.Column("element_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("warning_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "warnings",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["claim_id"], ["claims.id"], name="fk_element_runs_claim_id", ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "claim_id", "parser_name", "parser_version", name="uq_element_runs_claim_parser"
        ),
        sa.CheckConstraint("element_count >= 0", name="ck_element_runs_element_count"),
        sa.CheckConstraint("warning_count >= 0", name="ck_element_runs_warning_count"),
    )
    op.create_index(
        "ix_element_decomposition_runs_claim_id",
        "element_decomposition_runs",
        ["claim_id"],
    )

    op.create_table(
        "claim_elements",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["element_decomposition_runs.id"],
            name="fk_claim_elements_run_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("run_id", "sequence_number", name="uq_claim_elements_run_sequence"),
        sa.CheckConstraint("sequence_number >= 0", name="ck_claim_elements_sequence_non_negative"),
        sa.CheckConstraint("length(text) > 0", name="ck_claim_elements_text_non_empty"),
    )
    op.create_index("ix_claim_elements_run_id", "claim_elements", ["run_id"])

    op.create_table(
        "claim_element_spans",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("element_id", sa.Uuid(), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("start_char", sa.Integer(), nullable=False),
        sa.Column("end_char", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["element_id"],
            ["claim_elements.id"],
            name="fk_element_spans_element_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "element_id", "sequence_number", name="uq_element_spans_element_sequence"
        ),
        sa.CheckConstraint("sequence_number >= 0", name="ck_element_spans_sequence_non_negative"),
        sa.CheckConstraint("page_number >= 1", name="ck_element_spans_page_positive"),
        sa.CheckConstraint("start_char >= 0", name="ck_element_spans_start_non_negative"),
        sa.CheckConstraint("end_char > start_char", name="ck_element_spans_end_after_start"),
    )
    op.create_index("ix_claim_element_spans_element_id", "claim_element_spans", ["element_id"])


def downgrade() -> None:
    op.drop_table("claim_element_spans")
    op.drop_table("claim_elements")
    op.drop_table("element_decomposition_runs")
