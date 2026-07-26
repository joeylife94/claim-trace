"""Claim hybrid retrieval tables

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-26

Adds the two tables claim indexing and hybrid retrieval need, plus the pg_trgm
extension. Nothing else: there are no chunks, no claim elements, and no place to
put a generated answer.

Three decisions are worth reading rather than skimming:

* ``claim_index_runs`` is unique on ``(claim_parse_result_id, profile_key)``.
  ``profile_key`` is the canonical join of the whole retrieval profile - embedding
  provider, model, model version, dimension, normalisation policy and version,
  lexical strategy and version. That single column *is* the idempotency rule, and
  it lets search select one profile with an indexed equality instead of matching
  nine columns. Two models of the same width can therefore coexist as two runs.
* ``claim_search_records.embedding`` is ``vector(384)``, the width of the model
  this phase was validated with. A model of a different width needs a new
  migration; this is a deliberate MVP limitation, documented rather than hidden
  behind a speculative multi-dimension design.
* Lexical retrieval uses the ``simple`` text-search configuration plus pg_trgm.
  ``simple`` splits on whitespace and punctuation and does no Korean
  morphological analysis, so the trigram index is not an optimisation here - it
  is the channel that recovers Korean compounds and josa-attached tokens that
  full-text search alone cannot match.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEX_STATUSES = ("processing", "completed", "failed")

#: Must match claimtrace_api.db.models.EMBEDDING_DIMENSION.
_EMBEDDING_DIMENSION = 384


def upgrade() -> None:
    # Trigram matching for the lexical channel. IF NOT EXISTS because the initdb
    # script in infra/postgres/init may already have run as superuser.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_table(
        "claim_index_runs",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("claim_parse_result_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            # VARCHAR + CHECK, consistent with documents.status and
            # claim_parse_results.status.
            sa.Enum(
                *_INDEX_STATUSES,
                name="claim_index_status",
                native_enum=False,
                length=32,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("profile_key", sa.String(length=512), nullable=False),
        sa.Column("embedding_provider", sa.String(length=64), nullable=False),
        sa.Column("embedding_model", sa.String(length=255), nullable=False),
        sa.Column("embedding_model_version", sa.String(length=64), nullable=False),
        sa.Column("embedding_dimension", sa.Integer(), nullable=False),
        sa.Column("vectors_normalized", sa.Boolean(), nullable=False),
        sa.Column("normalization_version", sa.String(length=32), nullable=False),
        sa.Column("lexical_strategy", sa.String(length=64), nullable=False),
        sa.Column("lexical_strategy_version", sa.String(length=32), nullable=False),
        sa.Column("indexed_claim_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
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
        # An index run is derived from a parse result: re-parsing invalidates it,
        # and deleting the parse result must not leave it searchable.
        sa.ForeignKeyConstraint(
            ["claim_parse_result_id"],
            ["claim_parse_results.id"],
            name="fk_claim_index_runs_parse_result_id",
            ondelete="CASCADE",
        ),
        # The idempotency policy, enforced by the database rather than by the
        # service's pre-check alone.
        sa.UniqueConstraint(
            "claim_parse_result_id", "profile_key", name="uq_claim_index_runs_result_profile"
        ),
        sa.CheckConstraint(
            "embedding_dimension > 0", name="ck_claim_index_runs_dimension_positive"
        ),
        sa.CheckConstraint("indexed_claim_count >= 0", name="ck_claim_index_runs_claim_count"),
    )
    op.create_index(
        "ix_claim_index_runs_claim_parse_result_id", "claim_index_runs", ["claim_parse_result_id"]
    )
    op.create_index("ix_claim_index_runs_status", "claim_index_runs", ["status"])
    op.create_index("ix_claim_index_runs_created_at", "claim_index_runs", ["created_at"])
    # The search-side lookup: completed runs for the active profile.
    op.create_index(
        "ix_claim_index_runs_profile_status", "claim_index_runs", ["profile_key", "status"]
    )

    op.create_table(
        "claim_search_records",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("index_run_id", sa.Uuid(), nullable=False),
        sa.Column("claim_id", sa.Uuid(), nullable=False),
        # Denormalised so document scoping costs no join on the search path.
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("claim_number", sa.Integer(), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=False),
        sa.Column("search_vector", postgresql.TSVECTOR(), nullable=False),
        sa.Column("embedding", Vector(_EMBEDDING_DIMENSION), nullable=False),
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
            ["index_run_id"],
            ["claim_index_runs.id"],
            name="fk_claim_search_records_index_run_id",
            ondelete="CASCADE",
        ),
        # A search record must never outlive the claim it projects, or a query
        # could return text the operator believes was deleted.
        sa.ForeignKeyConstraint(
            ["claim_id"],
            ["claims.id"],
            name="fk_claim_search_records_claim_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_claim_search_records_document_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("index_run_id", "claim_id", name="uq_claim_search_records_run_claim"),
    )

    op.create_index(
        "ix_claim_search_records_index_run_id", "claim_search_records", ["index_run_id"]
    )
    op.create_index("ix_claim_search_records_claim_id", "claim_search_records", ["claim_id"])
    op.create_index("ix_claim_search_records_document_id", "claim_search_records", ["document_id"])

    # Dense channel. HNSW rather than IVFFlat: it needs no training pass and no
    # list-count tuning, which matters when a corpus starts at a handful of
    # claims and grows. vector_cosine_ops matches the stored unit vectors.
    op.execute(
        """
        CREATE INDEX ix_claim_search_records_embedding_hnsw
        ON claim_search_records
        USING hnsw (embedding vector_cosine_ops)
        """
    )

    # Lexical channel: full-text tokens and trigrams over the same column.
    op.execute(
        """
        CREATE INDEX ix_claim_search_records_search_vector
        ON claim_search_records USING gin (search_vector)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_claim_search_records_normalized_trgm
        ON claim_search_records USING gin (normalized_text gin_trgm_ops)
        """
    )


def downgrade() -> None:
    op.drop_table("claim_search_records")
    op.drop_index("ix_claim_index_runs_profile_status", table_name="claim_index_runs")
    op.drop_index("ix_claim_index_runs_created_at", table_name="claim_index_runs")
    op.drop_index("ix_claim_index_runs_status", table_name="claim_index_runs")
    op.drop_index("ix_claim_index_runs_claim_parse_result_id", table_name="claim_index_runs")
    op.drop_table("claim_index_runs")
    # pg_trgm and vector are left in place: dropping a shared extension is not
    # safe to automate, and other objects may depend on either.
