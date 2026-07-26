"""Dense retrieval over pgvector.

Similarity is **cosine**, expressed through pgvector's ``<=>`` distance operator
and reported as ``1 - distance``. Cosine is the right metric because the stored
vectors are unit length: the provider normalises them at encode time, so cosine
and inner product agree and no scaling is needed at query time. Reporting a
similarity rather than a distance means a larger number is a better match, which
matches how the lexical channel and the fused score already read.

The ANN index is HNSW (``vector_cosine_ops``), created in migration 0004. HNSW
was chosen over IVFFlat because it needs no training pass over an existing
corpus and no list-count tuning - relevant when an index starts at a handful of
claims and grows, since an IVFFlat index built on a small corpus stays badly
tuned until it is rebuilt.

**All similarity is computed in PostgreSQL.** No vector is ever pulled into
Python to be compared: the embedding column is not even selected.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from pgvector.sqlalchemy import Vector
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from claimtrace_api.db.models import EMBEDDING_DIMENSION
from claimtrace_api.retrieval.base import Candidate


class DenseRetriever:
    """Ranks claim search records by cosine similarity to the query vector."""

    def __init__(self, *, session: AsyncSession) -> None:
        self._session = session

    async def retrieve(
        self,
        *,
        query_vector: Sequence[float],
        index_run_ids: Sequence[uuid.UUID],
        limit: int,
    ) -> list[Candidate]:
        """Return up to ``limit`` dense candidates, most similar first."""
        if not index_run_ids or limit <= 0:
            return []

        # The inner query orders by the distance operator alone, which is the
        # only form pgvector's HNSW index can serve; adding the tie-break columns
        # there would silently turn the whole thing into a sequential scan. The
        # outer query re-sorts that small candidate set deterministically, so
        # equidistant vectors always come back in the same order.
        statement = text(
            """
            SELECT claim_id, document_id, claim_number, distance
            FROM (
                SELECT
                    r.claim_id,
                    r.document_id,
                    r.claim_number,
                    r.embedding <=> :query_vector AS distance
                FROM claim_search_records AS r
                WHERE r.index_run_id = ANY(:index_run_ids)
                ORDER BY r.embedding <=> :query_vector
                LIMIT :limit
            ) AS nearest
            ORDER BY distance ASC, claim_number ASC, claim_id ASC
            """
        ).bindparams(
            bindparam("index_run_ids", value=list(index_run_ids)),
            # Typed as a vector, not left to the driver: an untyped parameter is
            # sent as text, and "vector <=> varchar" is not an operator that
            # exists, so the query would fail at execution rather than compare.
            bindparam("query_vector", value=list(query_vector), type_=Vector(EMBEDDING_DIMENSION)),
            bindparam("limit", value=limit),
        )

        rows = (await self._session.execute(statement)).all()

        return [
            Candidate(
                claim_id=row.claim_id,
                document_id=row.document_id,
                claim_number=row.claim_number,
                rank=position,
                # Cosine distance is in [0, 2]; for unit vectors of realistic
                # text it stays in [0, 1], and 1 - d reads as a similarity.
                score=1.0 - float(row.distance),
            )
            for position, row in enumerate(rows, start=1)
        ]
