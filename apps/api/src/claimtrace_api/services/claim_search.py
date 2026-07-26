"""Claim search use case: profile selection, retrieval, fusion, and hydration.

The flow is deliberately in this order:

1. **Select the index runs** that are compatible with the active profile. Nothing
   outside that set is searched, so vectors from two different models can never
   be ranked against each other.
2. **Retrieve independently** from the dense and lexical channels. Neither sees
   the other's results, so neither can bias the other's ordering.
3. **Fuse by rank**, not by score. See ``retrieval/fusion.py``.
4. **Hydrate only the survivors** with claim text, dependencies, and source
   spans. Candidate generation deals in identities; the expensive join happens
   once, for the handful of claims that will actually be returned.

Step 4 is where the product's premise is enforced: a result is not a result until
it carries the canonical ``(document_id, page_number, start_char, end_char)``
spans that let a reader verify it against the original document.
"""

from __future__ import annotations

import hashlib
import logging
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from claimtrace_api.core.config import Settings
from claimtrace_api.db.models import (
    Claim,
    ClaimDependency,
    ClaimParseResult,
    ClaimSpan,
    ClaimType,
    Document,
)
from claimtrace_api.indexing.embeddings.base import EmbeddingProvider
from claimtrace_api.indexing.profile import IndexProfile, profile_for
from claimtrace_api.retrieval.base import Candidate, FusedCandidate, RetrievalMode
from claimtrace_api.retrieval.dense import DenseRetriever
from claimtrace_api.retrieval.fusion import reciprocal_rank_fusion
from claimtrace_api.retrieval.lexical import LexicalRetriever

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SearchResult:
    """One claim, its provenance, and how each channel ranked it."""

    document_id: uuid.UUID
    document_filename: str
    claim_number: int
    claim_type: ClaimType
    text: str
    depends_on: list[int]
    spans: list[ClaimSpan]
    fused_rank: int
    fused_score: float
    dense_rank: int | None = None
    dense_score: float | None = None
    lexical_rank: int | None = None
    lexical_score: float | None = None


@dataclass(frozen=True, slots=True)
class SearchOutcome:
    """A completed search: what was searched, and what came back."""

    mode: RetrievalMode
    profile: IndexProfile
    #: How many completed index runs the active profile matched. Zero means
    #: nothing has been indexed for this profile yet, which is a different
    #: situation from a query that simply matched nothing.
    searched_index_run_count: int
    dense_candidate_count: int
    lexical_candidate_count: int
    results: list[SearchResult] = field(default_factory=list)


class ClaimSearchService:
    """Runs a claim search against the active retrieval profile."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        provider: EmbeddingProvider,
        settings: Settings,
    ) -> None:
        self._session = session
        self._provider = provider
        self._settings = settings

    async def search(
        self,
        *,
        query: str,
        mode: RetrievalMode = RetrievalMode.HYBRID,
        document_ids: Sequence[uuid.UUID] | None = None,
        top_k: int,
        dense_candidate_count: int,
        lexical_candidate_count: int,
    ) -> SearchOutcome:
        """Retrieve claims matching ``query``, best first."""
        started = time.perf_counter()
        profile = profile_for(self._provider)

        index_run_ids = await self._active_index_runs(profile, document_ids)
        if not index_run_ids:
            self._log_search(query, mode, profile, started, run_count=0, result_count=0)
            return SearchOutcome(
                mode=mode,
                profile=profile,
                searched_index_run_count=0,
                dense_candidate_count=0,
                lexical_candidate_count=0,
            )

        dense: list[Candidate] = []
        lexical: list[Candidate] = []

        if mode in (RetrievalMode.HYBRID, RetrievalMode.DENSE):
            query_vector = self._provider.embed_query(query)
            dense = await DenseRetriever(session=self._session).retrieve(
                query_vector=query_vector,
                index_run_ids=index_run_ids,
                limit=dense_candidate_count,
            )

        if mode in (RetrievalMode.HYBRID, RetrievalMode.LEXICAL):
            lexical = await LexicalRetriever(session=self._session).retrieve(
                query=query,
                index_run_ids=index_run_ids,
                limit=lexical_candidate_count,
            )

        # Single-channel modes go through fusion too. 1/(k + rank) is strictly
        # decreasing in rank, so the fused order is exactly the channel's own
        # order - and the response shape stays identical across all three modes
        # instead of having a fused score that sometimes exists.
        fused = reciprocal_rank_fusion(
            dense=dense,
            lexical=lexical,
            k=self._settings.rrf_k,
            top_k=top_k,
        )

        results = await self._hydrate(fused)
        self._log_search(
            query,
            mode,
            profile,
            started,
            run_count=len(index_run_ids),
            result_count=len(results),
            dense_count=len(dense),
            lexical_count=len(lexical),
        )

        return SearchOutcome(
            mode=mode,
            profile=profile,
            searched_index_run_count=len(index_run_ids),
            dense_candidate_count=len(dense),
            lexical_candidate_count=len(lexical),
            results=results,
        )

    # -- internals ----------------------------------------------------------

    async def _active_index_runs(
        self, profile: IndexProfile, document_ids: Sequence[uuid.UUID] | None
    ) -> list[uuid.UUID]:
        """Choose exactly one completed index run per document.

        A document can have several parse results - one per claim parser version
        - and therefore several index runs under the same profile. Searching all
        of them would return the same claim once per parser version. ``DISTINCT
        ON`` keeps the newest run per document, so an upgraded parser's index
        supersedes its predecessor without the old rows having to be deleted.

        Only runs whose ``profile_key`` equals the active profile's are eligible,
        which is what stops two embedding models from being mixed.
        """
        statement = text(
            """
            SELECT DISTINCT ON (pr.document_id) ir.id
            FROM claim_index_runs AS ir
            JOIN claim_parse_results AS pr ON pr.id = ir.claim_parse_result_id
            WHERE ir.status = 'completed'
              AND ir.profile_key = :profile_key
              AND (:scoped = false OR pr.document_id = ANY(:document_ids))
            ORDER BY pr.document_id, ir.created_at DESC, ir.id DESC
            """
        )
        rows = await self._session.execute(
            statement,
            {
                "profile_key": profile.key,
                "scoped": bool(document_ids),
                # ANY() needs a well-typed empty array even when unused, or
                # PostgreSQL cannot infer the element type of the parameter.
                "document_ids": list(document_ids) if document_ids else [uuid.UUID(int=0)],
            },
        )
        return [row.id for row in rows.all()]

    async def _hydrate(self, fused: Sequence[FusedCandidate]) -> list[SearchResult]:
        """Attach claim text, dependencies, spans, and document name."""
        if not fused:
            return []

        claim_ids = [candidate.claim_id for candidate in fused]

        rows = (
            (
                await self._session.execute(
                    select(Claim, Document.original_filename, ClaimParseResult.id)
                    .join(ClaimParseResult, ClaimParseResult.id == Claim.parse_result_id)
                    .join(Document, Document.id == ClaimParseResult.document_id)
                    .where(Claim.id.in_(claim_ids))
                    .options(selectinload(Claim.spans))
                )
            )
            .tuples()
            .all()
        )
        claims = {claim.id: (claim, filename) for claim, filename, _ in rows}
        parse_result_ids = {parse_result_id for _, _, parse_result_id in rows}

        dependencies = await self._dependency_numbers(parse_result_ids)

        results: list[SearchResult] = []
        for candidate in fused:
            found = claims.get(candidate.claim_id)
            if found is None:  # pragma: no cover - FK CASCADE keeps these in step
                continue
            claim, filename = found
            results.append(
                SearchResult(
                    document_id=candidate.document_id,
                    document_filename=filename,
                    claim_number=claim.claim_number,
                    claim_type=claim.claim_type,
                    # The original stored claim text, never the normalised form:
                    # what is shown must be what the document says.
                    text=claim.text,
                    depends_on=dependencies.get(claim.id, []),
                    spans=sorted(claim.spans, key=lambda span: span.sequence_number),
                    fused_rank=candidate.fused_rank,
                    fused_score=candidate.fused_score,
                    dense_rank=candidate.dense_rank,
                    dense_score=candidate.dense_score,
                    lexical_rank=candidate.lexical_rank,
                    lexical_score=candidate.lexical_score,
                )
            )
        return results

    async def _dependency_numbers(
        self, parse_result_ids: set[uuid.UUID]
    ) -> dict[uuid.UUID, list[int]]:
        """Claim id -> referenced claim numbers, for the results' parse results."""
        if not parse_result_ids:
            return {}

        edges = (
            (
                await self._session.execute(
                    select(ClaimDependency).where(
                        ClaimDependency.parse_result_id.in_(parse_result_ids)
                    )
                )
            )
            .scalars()
            .all()
        )
        if not edges:
            return {}

        referenced_ids = {edge.referenced_claim_id for edge in edges}
        numbers = dict(
            (
                await self._session.execute(
                    select(Claim.id, Claim.claim_number).where(Claim.id.in_(referenced_ids))
                )
            )
            .tuples()
            .all()
        )

        dependencies: dict[uuid.UUID, list[int]] = {}
        for edge in edges:
            number = numbers.get(edge.referenced_claim_id)
            if number is not None:
                dependencies.setdefault(edge.dependent_claim_id, []).append(number)
        for values in dependencies.values():
            values.sort()
        return dependencies

    def _log_search(
        self,
        query: str,
        mode: RetrievalMode,
        profile: IndexProfile,
        started: float,
        *,
        run_count: int,
        result_count: int,
        dense_count: int = 0,
        lexical_count: int = 0,
    ) -> None:
        """One structured event per search.

        The query itself is never logged. A patent search query is a statement of
        what someone is working on, which in this domain is confidential before
        anything is filed - and logs outlive requests and get shipped elsewhere.
        The length and a short digest prefix are enough to correlate a report
        ("my search returned nothing") with a log line, and not enough to
        reconstruct the query.
        """
        logger.info(
            "claim search finished",
            extra={
                "query_length": len(query),
                "query_hash_prefix": hashlib.sha256(query.encode("utf-8")).hexdigest()[:12],
                "retrieval_mode": mode.value,
                "embedding_provider": profile.embedding_provider,
                "embedding_model": profile.embedding_model,
                "lexical_strategy": profile.lexical_strategy,
                "index_run_count": run_count,
                "dense_candidate_count": dense_count,
                "lexical_candidate_count": lexical_count,
                "result_count": result_count,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            },
        )
