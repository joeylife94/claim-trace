"""Document ingestion tables

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-26

Creates the two tables the ingestion boundary needs and nothing more. Sections,
claims, chunks, and embeddings arrive in later phases with their own revisions.

The unique index on documents.sha256 is what makes ingestion idempotent: it is
the constraint behind the duplicate policy, not just an optimisation.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DOCUMENT_STATUSES = ("uploaded", "processing", "completed", "failed")


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("original_filename", sa.String(length=512), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column(
            "status",
            # VARCHAR + CHECK rather than a native enum: adding a lifecycle state
            # later is then a normal migration instead of an ALTER TYPE.
            sa.Enum(
                *_DOCUMENT_STATUSES,
                name="document_status",
                native_enum=False,
                length=32,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("extracted_character_count", sa.Integer(), nullable=True),
        sa.Column("parser_name", sa.String(length=64), nullable=True),
        sa.Column("parser_version", sa.String(length=64), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.String(length=512), nullable=True),
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
        sa.CheckConstraint("size_bytes > 0", name="ck_documents_size_bytes_positive"),
        sa.CheckConstraint(
            "page_count IS NULL OR page_count >= 0",
            name="ck_documents_page_count_non_negative",
        ),
    )
    op.create_index("ix_documents_sha256", "documents", ["sha256"], unique=True)
    op.create_index("ix_documents_status", "documents", ["status"])
    op.create_index("ix_documents_created_at", "documents", ["created_at"])

    op.create_table(
        "document_pages",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("character_count", sa.Integer(), nullable=False),
        sa.Column("text_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # Pages have no meaning without their document, so they are removed with it.
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_document_pages_document_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("document_id", "page_number", name="uq_document_pages_document_page"),
        sa.CheckConstraint("page_number >= 1", name="ck_document_pages_page_number_positive"),
        sa.CheckConstraint(
            "character_count >= 0", name="ck_document_pages_char_count_non_negative"
        ),
    )
    op.create_index("ix_document_pages_document_id", "document_pages", ["document_id"])


def downgrade() -> None:
    op.drop_index("ix_document_pages_document_id", table_name="document_pages")
    op.drop_table("document_pages")
    op.drop_index("ix_documents_created_at", table_name="documents")
    op.drop_index("ix_documents_status", table_name="documents")
    op.drop_index("ix_documents_sha256", table_name="documents")
    op.drop_table("documents")
