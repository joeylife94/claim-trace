"""Bounded claim-to-claim comparison over the existing retrieval pipeline.

The target claim's persisted text becomes the retrieval query. Retrieval is forced
to exactly one reference document, then every result is checked again before it is
returned. This is intentionally a textual-correspondence service: it ranks stored
claims and preserves provenance; it does not decide equivalence or any legal issue.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from claimtrace_api.core.config import Settings
from claimtrace_api.core.errors import AppError, ErrorCode
from claimtrace_api.db.models import ClaimSpan, ClaimType, Document
from claimtrace_api.indexing.profile import IndexProfile
from claimtrace_api.retrieval.base import RetrievalMode
from claimtrace_api.services.claim_parsing import ClaimParsingService
from claimtrace_api.services.claim_search import ClaimSearchService, SearchResult


@dataclass(frozen=True, slots=True)
class ComparisonTarget:
    """The stored target claim and its provenance."""

    document_id: uuid.UUID
    claim_number: int
    claim_type: ClaimType
    text: str
    depends_on: list[int]
    spans: tuple[ClaimSpan, ...]


@dataclass(frozen=True, slots=True)
class ClaimComparisonOutcome:
    """One strictly document-scoped comparison run."""

    target: ComparisonTarget
    reference_document_id: uuid.UUID
    mode: RetrievalMode
    profile: IndexProfile
    searched_index_run_count: int
    no_correspondence_reason: str | None
    matches: list[SearchResult] = field(default_factory=list)


class ClaimComparisonService:
    """Retrieve textual correspondences for one claim in one reference document."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        parsing: ClaimParsingService,
        search: ClaimSearchService,
        settings: Settings,
    ) -> None:
        self._session = session
        self._parsing = parsing
        self._search = search
        self._settings = settings

    async def compare(
        self,
        *,
        target_document_id: uuid.UUID,
        target_claim_number: int,
        reference_document_id: uuid.UUID,
        mode: RetrievalMode,
        top_k: int,
    ) -> ClaimComparisonOutcome:
        """Compare one stored target claim against one reference document.

        The caller cannot provide arbitrary query text. The query is exactly the
        target claim text already persisted by ClaimTrace, so the target side of
        the comparison always has a source locator.
        """
        if target_document_id == reference_document_id:
            raise AppError(
                ErrorCode.COMPARISON_INVALID_REQUEST,
                "Target and reference documents must be different.",
            )

        await self._require_document(target_document_id)
        await self._require_document(reference_document_id)

        snapshot = await self._parsing.snapshot(target_document_id)
        if snapshot is None:
            raise AppError(
                ErrorCode.CLAIM_PARSE_NOT_FOUND,
                "The target document has not been parsed for claims yet.",
            )

        target_claim = next(
            (claim for claim in snapshot.claims if claim.claim_number == target_claim_number),
            None,
        )
        if target_claim is None:
            raise AppError(
                ErrorCode.CLAIM_NOT_FOUND,
                f"Claim {target_claim_number} is not in the target document.",
            )

        outcome = await self._search.search(
            query=target_claim.text,
            mode=mode,
            document_ids=[reference_document_id],
            top_k=min(top_k, self._settings.search_top_k_max),
            dense_candidate_count=self._settings.dense_candidate_count,
            lexical_candidate_count=self._settings.lexical_candidate_count,
        )

        # Search already scopes by index run. Keep a second service-level invariant
        # because returning one claim from a different document would turn a
        # comparison into a provenance leak rather than merely a ranking defect.
        leaked = [result for result in outcome.results if result.document_id != reference_document_id]
        if leaked:
            raise AppError(
                ErrorCode.INTERNAL_ERROR,
                "Claim comparison retrieval returned evidence outside the requested reference document.",
            )

        if outcome.results:
            reason = None
        elif outcome.searched_index_run_count == 0:
            reason = "reference_not_indexed"
        else:
            reason = "no_matches"

        return ClaimComparisonOutcome(
            target=ComparisonTarget(
                document_id=target_document_id,
                claim_number=target_claim.claim_number,
                claim_type=target_claim.claim_type,
                text=target_claim.text,
                depends_on=list(snapshot.dependencies.get(target_claim.id, [])),
                spans=tuple(sorted(target_claim.spans, key=lambda span: span.sequence_number)),
            ),
            reference_document_id=reference_document_id,
            mode=outcome.mode,
            profile=outcome.profile,
            searched_index_run_count=outcome.searched_index_run_count,
            no_correspondence_reason=reason,
            matches=outcome.results,
        )

    async def _require_document(self, document_id: uuid.UUID) -> Document:
        document = await self._session.get(Document, document_id)
        if document is None:
            raise AppError(ErrorCode.DOCUMENT_NOT_FOUND, "Document not found.")
        return document
