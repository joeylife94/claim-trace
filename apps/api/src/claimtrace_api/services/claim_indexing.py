"""Claim indexing use case.

A third lifecycle, alongside ingestion and claim parsing, and the ordering
mirrors theirs for the same reasons:

1. Refuse anything but a ``completed`` document with a ``completed`` claim parse
   result. Indexing a half-parsed claim set would put text into the search index
   that nothing can cite.
2. Return an existing completed run for the same profile untouched. Re-embedding
   the same claims with the same model produces the same vectors, so a second
   run would only duplicate them.
3. Commit ``processing`` before the model runs. Model loading is the slowest and
   least reliable step in the system; a crash there must leave a record that is
   distinguishable from both "never started" and "finished".
4. Write every search record and the terminal status in **one** transaction. A
   partially embedded claim set must never be visible as a completed index,
   because search would silently return a subset of the document's claims as
   though it were all of them.

Neither ``documents.status`` nor ``claim_parse_results.status`` is ever written
here. A document whose claims cannot be embedded is still a perfectly good
document with a perfectly good claim graph.

**Retry policy.** A run that is ``failed``, or stranded in ``processing`` because
the process died, is retried in place on the next request: its search records are
deleted and the same row is reused. The unique constraint on
``(claim_parse_result_id, profile_key)`` means there is exactly one row per
profile, so attempts cannot accumulate. The row is locked ``FOR UPDATE`` while it
is being retried, so two concurrent index requests for the same document
serialise instead of racing to write the same records.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from claimtrace_api.core.errors import AppError, ErrorCode
from claimtrace_api.db.models import (
    EMBEDDING_DIMENSION,
    Claim,
    ClaimDependency,
    ClaimIndexRun,
    ClaimIndexStatus,
    ClaimParseResult,
    ClaimParseStatus,
    ClaimSearchRecord,
    Document,
    DocumentStatus,
)
from claimtrace_api.indexing.embeddings.base import EmbeddingError, EmbeddingProvider
from claimtrace_api.indexing.normalization import NORMALIZATION_VERSION, build_search_text
from claimtrace_api.indexing.profile import IndexProfile, profile_for

logger = logging.getLogger(__name__)


class ClaimIndexingFailed(AppError):
    """Indexing failed, and the failure is recorded on ``run``."""

    def __init__(self, code: ErrorCode, message: str, run: ClaimIndexRun) -> None:
        super().__init__(code, message)
        self.run = run


@dataclass(frozen=True, slots=True)
class ClaimIndexingOutcome:
    """Result of an index request."""

    run: ClaimIndexRun
    #: False when an existing completed run for this profile was returned, which
    #: the route maps to 200 instead of 201.
    created: bool


class ClaimIndexingService:
    """Coordinates the embedding provider with search-record persistence."""

    def __init__(self, *, session: AsyncSession, provider: EmbeddingProvider) -> None:
        self._session = session
        self._provider = provider

    @property
    def profile(self) -> IndexProfile:
        """The active retrieval profile, derived from the configured provider."""
        return profile_for(self._provider)

    # -- commands -----------------------------------------------------------

    async def index(self, document: Document) -> ClaimIndexingOutcome:
        """Index a document's parsed claims, or return the existing index run.

        Raises:
            AppError: ingestion or claim parsing has not completed, or the
                provider's dimension does not match the stored column.
            ClaimIndexingFailed: embedding or persistence failed; the failed run
                is persisted and attached to the exception.
        """
        if document.status is not DocumentStatus.COMPLETED:
            raise AppError(
                ErrorCode.DOCUMENT_NOT_COMPLETED,
                "Claim indexing needs a document whose ingestion has completed.",
            )

        parse_result = await self._latest_parse_result(document.id)
        if parse_result is None:
            raise AppError(
                ErrorCode.CLAIM_PARSE_NOT_FOUND,
                "This document has not been parsed for claims yet.",
            )
        if parse_result.status is not ClaimParseStatus.COMPLETED:
            # Includes no_claims_found: a document with no claims has nothing to
            # index, and reporting that as an empty success would make an
            # unindexable document look indexed.
            raise AppError(
                ErrorCode.CLAIM_PARSE_NOT_COMPLETED,
                "Claim indexing needs a completed claim parse result. This document's "
                f"claim parsing finished with status '{parse_result.status.value}'.",
            )

        # Checked before any row is written: the provider is configured, and a
        # width the column cannot hold is an operator error, not a run that
        # should be recorded as failed.
        if self._provider.dimension != EMBEDDING_DIMENSION:
            raise AppError(
                ErrorCode.EMBEDDING_DIMENSION_MISMATCH,
                f"The configured embedding provider produces {self._provider.dimension}-"
                f"dimensional vectors but this deployment stores {EMBEDDING_DIMENSION}. "
                "Storing a different width needs a migration.",
            )

        started = time.perf_counter()
        # Captured now, while the instance is certainly live. A rollback on the
        # failure paths below expires every object in the session, and reading an
        # attribute off an expired instance would issue synchronous IO on an
        # async session instead of reporting the failure being handled.
        document_id = document.id
        profile = self.profile
        existing = await self._find_run(parse_result.id, profile.key)

        if existing is not None and existing.status is ClaimIndexStatus.COMPLETED:
            logger.info(
                "claim indexing skipped: existing completed run",
                extra={
                    "document_id": str(document_id),
                    "index_run_id": str(existing.id),
                    "embedding_provider": existing.embedding_provider,
                    "embedding_model": existing.embedding_model,
                    "indexed_claim_count": existing.indexed_claim_count,
                },
            )
            return ClaimIndexingOutcome(run=existing, created=False)

        run = await self._begin(parse_result, profile, existing)

        claims = await self._load_claims(parse_result.id)
        dependencies = await self._load_dependencies(parse_result.id, claims)

        search_texts = [
            build_search_text(
                claim_number=claim.claim_number,
                claim_type=claim.claim_type,
                dependencies=dependencies.get(claim.id, []),
                body=claim.text,
            )
            for claim in claims
        ]

        try:
            vectors = self._provider.embed_documents(search_texts)
        except EmbeddingError as exc:
            failed = await self._mark_failed(run, exc.code, exc.message)
            self._log_outcome(document_id, failed, started)
            raise ClaimIndexingFailed(_error_code(exc.code), exc.message, failed) from exc
        except Exception as exc:
            logger.exception(
                "claim indexing raised an unexpected error",
                extra={"document_id": str(document_id), "index_run_id": str(run.id)},
            )
            failed = await self._mark_failed(
                run, ErrorCode.CLAIM_INDEX_FAILED.value, "Claim indexing failed unexpectedly."
            )
            self._log_outcome(document_id, failed, started)
            raise ClaimIndexingFailed(
                ErrorCode.CLAIM_INDEX_FAILED, failed.error_message or "", failed
            ) from exc

        if len(vectors) != len(claims):
            # A provider that loses or reorders a batch would silently attach the
            # wrong vector to a claim, which is worse than failing.
            failed = await self._mark_failed(
                run,
                ErrorCode.CLAIM_INDEX_FAILED.value,
                "The embedding provider returned a different number of vectors than claims.",
            )
            self._log_outcome(document_id, failed, started)
            raise ClaimIndexingFailed(
                ErrorCode.CLAIM_INDEX_FAILED, failed.error_message or "", failed
            )

        await self._persist(run, document_id, claims, search_texts, vectors)
        self._log_outcome(document_id, run, started)
        return ClaimIndexingOutcome(run=run, created=True)

    # -- queries ------------------------------------------------------------

    async def current_run(self, document_id: uuid.UUID) -> ClaimIndexRun | None:
        """The most recent index run for this document, whatever its profile.

        Deliberately not filtered to the active profile: the document detail page
        has to be able to show a run that was built with a model the deployment
        has since moved away from, rather than claiming the document was never
        indexed.
        """
        statement = (
            select(ClaimIndexRun)
            .join(ClaimParseResult, ClaimParseResult.id == ClaimIndexRun.claim_parse_result_id)
            .where(ClaimParseResult.document_id == document_id)
            .order_by(ClaimIndexRun.created_at.desc(), ClaimIndexRun.id.desc())
            .limit(1)
        )
        return (await self._session.execute(statement)).scalars().first()

    # -- internals ----------------------------------------------------------

    async def _latest_parse_result(self, document_id: uuid.UUID) -> ClaimParseResult | None:
        statement = (
            select(ClaimParseResult)
            .where(ClaimParseResult.document_id == document_id)
            .order_by(ClaimParseResult.created_at.desc())
            .limit(1)
        )
        return (await self._session.execute(statement)).scalars().first()

    async def _find_run(self, parse_result_id: uuid.UUID, profile_key: str) -> ClaimIndexRun | None:
        statement = select(ClaimIndexRun).where(
            ClaimIndexRun.claim_parse_result_id == parse_result_id,
            ClaimIndexRun.profile_key == profile_key,
        )
        return (await self._session.execute(statement)).scalars().first()

    async def _begin(
        self,
        parse_result: ClaimParseResult,
        profile: IndexProfile,
        existing: ClaimIndexRun | None,
    ) -> ClaimIndexRun:
        """Put the run into ``processing`` and commit it before the model runs."""
        if existing is None:
            run = ClaimIndexRun(
                id=uuid.uuid4(),
                claim_parse_result_id=parse_result.id,
                status=ClaimIndexStatus.PROCESSING,
                profile_key=profile.key,
                embedding_provider=profile.embedding_provider,
                embedding_model=profile.embedding_model,
                embedding_model_version=profile.embedding_model_version,
                embedding_dimension=profile.embedding_dimension,
                vectors_normalized=profile.vectors_normalized,
                normalization_version=profile.normalization_version,
                lexical_strategy=profile.lexical_strategy,
                lexical_strategy_version=profile.lexical_strategy_version,
            )
            self._session.add(run)
        else:
            # Retry in place. The lock serialises two concurrent index requests
            # for the same run: without it both would clear and rewrite the same
            # search records.
            run = (
                await self._session.execute(
                    select(ClaimIndexRun).where(ClaimIndexRun.id == existing.id).with_for_update()
                )
            ).scalar_one()
            await self._session.execute(
                delete(ClaimSearchRecord).where(ClaimSearchRecord.index_run_id == run.id)
            )
            run.status = ClaimIndexStatus.PROCESSING

        run.indexed_claim_count = 0
        run.error_code = None
        run.error_message = None
        run.started_at = datetime.now(tz=UTC)
        run.completed_at = None

        await self._session.commit()
        await self._session.refresh(run)
        return run

    async def _load_claims(self, parse_result_id: uuid.UUID) -> list[Claim]:
        return list(
            (
                await self._session.execute(
                    select(Claim)
                    .where(Claim.parse_result_id == parse_result_id)
                    .order_by(Claim.claim_number)
                )
            )
            .scalars()
            .all()
        )

    async def _load_dependencies(
        self, parse_result_id: uuid.UUID, claims: list[Claim]
    ) -> dict[uuid.UUID, list[int]]:
        """Claim id -> referenced claim numbers, ascending."""
        numbers = {claim.id: claim.claim_number for claim in claims}
        edges = (
            (
                await self._session.execute(
                    select(ClaimDependency).where(
                        ClaimDependency.parse_result_id == parse_result_id
                    )
                )
            )
            .scalars()
            .all()
        )

        dependencies: dict[uuid.UUID, list[int]] = {claim.id: [] for claim in claims}
        for edge in edges:
            referenced = numbers.get(edge.referenced_claim_id)
            if referenced is not None:
                dependencies[edge.dependent_claim_id].append(referenced)
        for values in dependencies.values():
            values.sort()
        return dependencies

    async def _persist(
        self,
        run: ClaimIndexRun,
        document_id: uuid.UUID,
        claims: list[Claim],
        search_texts: list[str],
        vectors: list[tuple[float, ...]],
    ) -> None:
        """Write every search record and the terminal status in one transaction."""
        for claim, search_text, vector in zip(claims, search_texts, vectors, strict=True):
            self._session.add(
                ClaimSearchRecord(
                    id=uuid.uuid4(),
                    index_run_id=run.id,
                    claim_id=claim.id,
                    document_id=document_id,
                    claim_number=claim.claim_number,
                    normalized_text=search_text,
                    # Tokenised from exactly the text that was embedded, so the
                    # two channels never disagree about what a record contains.
                    search_vector=func.to_tsvector("simple", search_text),
                    embedding=list(vector),
                )
            )

        run.indexed_claim_count = len(claims)
        run.status = ClaimIndexStatus.COMPLETED
        run.completed_at = datetime.now(tz=UTC)

        try:
            await self._session.commit()
        except Exception:
            # No records, and the status stays 'processing' - a truthful record
            # of an attempt that did not finish. The in-memory object is reset
            # too, so a caller holding it cannot read a 'completed' status that
            # was never committed.
            await self._session.rollback()
            run.status = ClaimIndexStatus.PROCESSING
            run.indexed_claim_count = 0
            run.completed_at = None
            logger.error(
                "claim search record persistence failed",
                extra={"index_run_id": str(run.id), "claim_count": len(claims)},
            )
            raise
        await self._session.refresh(run)

    async def _mark_failed(self, run: ClaimIndexRun, code: str, message: str) -> ClaimIndexRun:
        # Read the id *before* rolling back. A rollback expires every loaded
        # attribute, and reading one afterwards makes SQLAlchemy issue a lazy
        # refresh - synchronous IO on an async session, which fails with
        # MissingGreenlet rather than with the error being handled here.
        run_id = run.id

        await self._session.rollback()
        # Belt and braces. The rollback has already discarded anything this
        # transaction wrote, and _begin cleared any earlier attempt's records, so
        # this should find nothing - but a completed-looking partial index is the
        # one state that must never exist, so it is worth one cheap statement.
        await self._session.execute(
            delete(ClaimSearchRecord).where(ClaimSearchRecord.index_run_id == run_id)
        )
        run.status = ClaimIndexStatus.FAILED
        run.error_code = code[:64]
        run.error_message = message[:512]
        run.indexed_claim_count = 0
        run.completed_at = datetime.now(tz=UTC)
        await self._session.commit()
        await self._session.refresh(run)
        return run

    def _log_outcome(self, document_id: uuid.UUID, run: ClaimIndexRun, started: float) -> None:
        """One structured event per index run. Never includes claim text."""
        logger.info(
            "claim indexing finished",
            extra={
                "document_id": str(document_id),
                "index_run_id": str(run.id),
                "embedding_provider": run.embedding_provider,
                "embedding_model": run.embedding_model,
                "embedding_model_version": run.embedding_model_version,
                "embedding_dimension": run.embedding_dimension,
                "lexical_strategy": run.lexical_strategy,
                "normalization_version": NORMALIZATION_VERSION,
                "indexed_claim_count": run.indexed_claim_count,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                "status": run.status.value,
                "error_code": run.error_code,
            },
        )


def _error_code(value: str) -> ErrorCode:
    """Map a provider's error string back onto the API's taxonomy."""
    try:
        return ErrorCode(value)
    except ValueError:  # pragma: no cover - providers use ErrorCode values
        return ErrorCode.CLAIM_INDEX_FAILED
