"""Description evidence retrieval tables.

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-09

D4-01 keeps the persisted page text and its page-relative character offsets as
the only source coordinate system. Description segments are derived artifacts:
search records may be rebuilt or re-embedded, but their source span always
resolves against ``document_pages.text``.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_EMBEDDING_DIMENSION = 384
_DERIVATION_STATUSES = ("completed", "unsupported")


def upgrade() -> None:
    op.create_table(
        "description_derivation_runs",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                *_DERIVATION_STATUSES,
                name="description_derivation_status",
                native_enum=False,
                length=32,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("segmenter_name", sa.String(length=64), nullable=False),
        sa.Column("segmenter_version", sa.String(length=32), nullable=False),
        sa.Column("segment_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "warnings",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_description_derivation_runs_document_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "document_id",
            "segmenter_name",
            "segmenter_version",
            name="uq_description_derivation_runs_document_segmenter",
        ),
        sa.CheckConstraint("segment_count >= 0", name="ck_description_runs_segment_count"),
    )
    op.create_index(
        "ix_description_derivation_runs_document_id",
        "description_derivation_runs",
        ["document_id"],
    )

    op.create_table(
        "description_segments",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("segment_index", sa.Integer(), nullable=False),
        sa.Column("section_heading", sa.String(length=128), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("start_char", sa.Integer(), nullable=False),
        sa.Column("end_char", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "evidence_kind",
            sa.String(length=24),
            nullable=False,
            server_default=sa.text("'description'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["description_derivation_runs.id"],
            name="fk_description_segments_run_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_description_segments_document_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("run_id", "segment_index", name="uq_description_segments_run_index"),
        sa.CheckConstraint("segment_index >= 0", name="ck_description_segments_index"),
        sa.CheckConstraint("page_number >= 1", name="ck_description_segments_page"),
        sa.CheckConstraint("start_char >= 0", name="ck_description_segments_start"),
        sa.CheckConstraint("end_char > start_char", name="ck_description_segments_end"),
        sa.CheckConstraint(
            "evidence_kind = 'description'", name="ck_description_segments_evidence_kind"
        ),
    )
    op.create_index("ix_description_segments_document_id", "description_segments", ["document_id"])
    op.create_index("ix_description_segments_run_id", "description_segments", ["run_id"])

    op.create_table(
        "description_search_records",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("segment_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("segment_index", sa.Integer(), nullable=False),
        sa.Column("profile_key", sa.String(length=512), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=False),
        sa.Column("search_vector", postgresql.TSVECTOR(), nullable=False),
        sa.Column("embedding", Vector(_EMBEDDING_DIMENSION), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["segment_id"],
            ["description_segments.id"],
            name="fk_description_search_records_segment_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_description_search_records_document_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "segment_id", "profile_key", name="uq_description_search_records_segment_profile"
        ),
    )
    op.create_index(
        "ix_description_search_records_document_profile",
        "description_search_records",
        ["document_id", "profile_key"],
    )
    op.create_index(
        "ix_description_search_records_profile_key",
        "description_search_records",
        ["profile_key"],
    )
    op.execute(
        """
        CREATE INDEX ix_description_search_records_embedding_hnsw
        ON description_search_records
        USING hnsw (embedding vector_cosine_ops)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_description_search_records_search_vector
        ON description_search_records USING gin (search_vector)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_description_search_records_normalized_trgm
        ON description_search_records USING gin (normalized_text gin_trgm_ops)
        """
    )


def downgrade() -> None:
    op.drop_table("description_search_records")
    op.drop_table("description_segments")
    op.drop_table("description_derivation_runs")
