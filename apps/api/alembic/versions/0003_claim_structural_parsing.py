"""Claim structural parsing tables

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-26

Adds the four tables claim parsing needs, and nothing else.

Two things are worth reading rather than skimming:

* ``claim_parse_results`` is unique on ``(document_id, parser_name,
  parser_version)``. That constraint *is* the idempotency policy: re-running a
  parser version cannot create a second graph, and a future version lands beside
  the current one instead of overwriting results that citations may reference.
* ``claim_dependencies`` carries ``parse_result_id`` and references
  ``claims (id, parse_result_id)`` twice. Without it, nothing at the database
  level would stop an edge from pointing at another document's claim.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PARSE_STATUSES = ("processing", "completed", "no_claims_found", "failed")
_CLAIM_TYPES = ("independent", "dependent", "multiple_dependent", "unknown")


def upgrade() -> None:
    op.create_table(
        "claim_parse_results",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            # VARCHAR + CHECK, consistent with documents.status.
            sa.Enum(
                *_PARSE_STATUSES,
                name="claim_parse_status",
                native_enum=False,
                length=32,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("parser_name", sa.String(length=64), nullable=False),
        sa.Column("parser_version", sa.String(length=32), nullable=False),
        sa.Column("claim_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("warning_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "warnings",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.String(length=512), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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
        # A parse result is meaningless without its document, as with pages.
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_claim_parse_results_document_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "document_id",
            "parser_name",
            "parser_version",
            name="uq_claim_parse_results_document_parser",
        ),
        sa.CheckConstraint("claim_count >= 0", name="ck_claim_parse_results_claim_count"),
        sa.CheckConstraint("warning_count >= 0", name="ck_claim_parse_results_warning_count"),
    )
    op.create_index("ix_claim_parse_results_document_id", "claim_parse_results", ["document_id"])
    op.create_index("ix_claim_parse_results_status", "claim_parse_results", ["status"])
    op.create_index("ix_claim_parse_results_created_at", "claim_parse_results", ["created_at"])

    op.create_table(
        "claims",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("parse_result_id", sa.Uuid(), nullable=False),
        sa.Column("claim_number", sa.Integer(), nullable=False),
        sa.Column(
            "claim_type",
            sa.Enum(
                *_CLAIM_TYPES,
                name="claim_type",
                native_enum=False,
                length=24,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("text", sa.Text(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["parse_result_id"],
            ["claim_parse_results.id"],
            name="fk_claims_parse_result_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("parse_result_id", "claim_number", name="uq_claims_result_number"),
        # Target of the composite foreign keys in claim_dependencies.
        sa.UniqueConstraint("id", "parse_result_id", name="uq_claims_id_result"),
        sa.CheckConstraint("claim_number >= 1", name="ck_claims_number_positive"),
    )
    op.create_index("ix_claims_parse_result_id", "claims", ["parse_result_id"])

    op.create_table(
        "claim_spans",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("claim_id", sa.Uuid(), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("start_char", sa.Integer(), nullable=False),
        sa.Column("end_char", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["claim_id"], ["claims.id"], name="fk_claim_spans_claim_id", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("claim_id", "sequence_number", name="uq_claim_spans_claim_sequence"),
        sa.CheckConstraint("sequence_number >= 0", name="ck_claim_spans_sequence_non_negative"),
        sa.CheckConstraint("page_number >= 1", name="ck_claim_spans_page_number_positive"),
        sa.CheckConstraint("start_char >= 0", name="ck_claim_spans_start_non_negative"),
        sa.CheckConstraint("end_char > start_char", name="ck_claim_spans_end_after_start"),
    )
    op.create_index("ix_claim_spans_claim_id", "claim_spans", ["claim_id"])

    op.create_table(
        "claim_dependencies",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("parse_result_id", sa.Uuid(), nullable=False),
        sa.Column("dependent_claim_id", sa.Uuid(), nullable=False),
        sa.Column("referenced_claim_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # Both endpoints must belong to the same parse result.
        sa.ForeignKeyConstraint(
            ["dependent_claim_id", "parse_result_id"],
            ["claims.id", "claims.parse_result_id"],
            name="fk_claim_dependencies_dependent_in_result",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["referenced_claim_id", "parse_result_id"],
            ["claims.id", "claims.parse_result_id"],
            name="fk_claim_dependencies_referenced_in_result",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "dependent_claim_id", "referenced_claim_id", name="uq_claim_dependencies_pair"
        ),
        sa.CheckConstraint(
            "dependent_claim_id <> referenced_claim_id",
            name="ck_claim_dependencies_no_self_reference",
        ),
    )
    op.create_index(
        "ix_claim_dependencies_parse_result_id", "claim_dependencies", ["parse_result_id"]
    )
    op.create_index(
        "ix_claim_dependencies_dependent_claim_id", "claim_dependencies", ["dependent_claim_id"]
    )
    op.create_index(
        "ix_claim_dependencies_referenced", "claim_dependencies", ["referenced_claim_id"]
    )


def downgrade() -> None:
    op.drop_table("claim_dependencies")
    op.drop_index("ix_claim_spans_claim_id", table_name="claim_spans")
    op.drop_table("claim_spans")
    op.drop_index("ix_claims_parse_result_id", table_name="claims")
    op.drop_table("claims")
    op.drop_index("ix_claim_parse_results_created_at", table_name="claim_parse_results")
    op.drop_index("ix_claim_parse_results_status", table_name="claim_parse_results")
    op.drop_index("ix_claim_parse_results_document_id", table_name="claim_parse_results")
    op.drop_table("claim_parse_results")
