"""Claim structural parsing use case.

Ordering, and why:

1. Refuse anything but a ``completed`` document - without page text there is
   nothing to parse.
2. Look for an existing result for this parser version. A finished one is
   returned as-is: re-running a deterministic parser cannot produce a different
   graph, so creating a second one would only duplicate it.
3. Commit ``processing`` before parsing. A crash then leaves a record that is
   distinguishable from a completed result rather than nothing at all.
4. Write claims, spans, edges, counts, and the terminal status in **one**
   transaction. A half-written graph must never be visible as a completed parse.

The document's own status is never touched here. Ingestion succeeded or it did
not; whether claims could be found says nothing about that, and conflating the
two would make a perfectly readable PDF look broken.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from claimtrace_api.core.errors import AppError, ErrorCode
from claimtrace_api.db.models import (
    Claim,
    ClaimDependency,
    ClaimParseResult,
    ClaimParseStatus,
    ClaimSpan,
    Document,
    DocumentPage,
    DocumentStatus,
)
from claimtrace_api.parsing.claims.base import (
    ClaimParser,
    ClaimParserError,
    ParsedClaimSet,
    SourcePage,
)

logger = logging.getLogger(__name__)


class ClaimParsingFailed(AppError):
    """Parsing failed, and the failure is recorded on ``result``."""

    def __init__(self, message: str, result: ClaimParseResult) -> None:
        super().__init__(ErrorCode.CLAIM_PARSE_FAILED, message)
        self.result = result


@dataclass(frozen=True, slots=True)
class ClaimParsingOutcome:
    """Result of a parse request."""

    result: ClaimParseResult
    #: False when an existing result for this parser version was returned, which
    #: the route maps to 200 instead of 201.
    created: bool


@dataclass(frozen=True, slots=True)
class ClaimSetSnapshot:
    """Everything the read endpoints need, loaded in one place."""

    result: ClaimParseResult
    claims: Sequence[Claim]
    #: Claim id -> referenced claim numbers, ascending.
    dependencies: dict[uuid.UUID, list[int]]


class ClaimParsingService:
    """Coordinates the claim parser with persistence."""

    def __init__(self, *, session: AsyncSession, parser: ClaimParser) -> None:
        self._session = session
        self._parser = parser

    async def parse(self, document: Document) -> ClaimParsingOutcome:
        """Parse a document's claims, or return the existing result."""
        if document.status is not DocumentStatus.COMPLETED:
            raise AppError(
                ErrorCode.DOCUMENT_NOT_COMPLETED,
                "Claim parsing needs a document whose ingestion has completed.",
            )

        started = time.perf_counter()
        existing = await self._find_result(document.id)
        if existing is not None and existing.status in _TERMINAL_SUCCESS:
            logger.info(
                "claim parsing skipped: existing result",
                extra={
                    "document_id": str(document.id),
                    "parse_result_id": str(existing.id),
                    "parser_name": self._parser.name,
                    "parser_version": self._parser.version,
                    "status": existing.status.value,
                },
            )
            return ClaimParsingOutcome(result=existing, created=False)

        result = await self._begin(document, existing)
        pages = await self._load_pages(document.id)
        try:
            parsed = self._parser.parse(pages)
        except ClaimParserError as exc:
            failed = await self._mark_failed(result, exc.code, exc.message)
            self._log_outcome(document, failed, started, page_count=len(pages))
            raise ClaimParsingFailed(exc.message, failed) from exc
        except Exception as exc:
            logger.exception(
                "claim parsing raised an unexpected error",
                extra={"document_id": str(document.id), "parse_result_id": str(result.id)},
            )
            failed = await self._mark_failed(
                result,
                ErrorCode.INTERNAL_ERROR.value,
                "Claim parsing failed unexpectedly.",
            )
            self._log_outcome(document, failed, started, page_count=len(pages))
            raise ClaimParsingFailed(failed.error_message or "", failed) from exc

        await self._persist(result, parsed)
        self._log_outcome(
            document,
            result,
            started,
            page_count=len(pages),
            dependency_count=parsed.dependency_count,
        )
        return ClaimParsingOutcome(result=result, created=True)

    async def snapshot(self, document_id: uuid.UUID) -> ClaimSetSnapshot | None:
        """Load the current parse result with its claims, spans, and edges."""
        result = await self._find_result(document_id, any_parser=True)
        if result is None:
            return None
        claims = list(
            (
                await self._session.execute(
                    select(Claim)
                    .where(Claim.parse_result_id == result.id)
                    .options(selectinload(Claim.spans))
                    .order_by(Claim.claim_number)
                )
            )
            .scalars()
            .all()
        )
        numbers = {claim.id: claim.claim_number for claim in claims}
        edges = (
            (
                await self._session.execute(
                    select(ClaimDependency).where(ClaimDependency.parse_result_id == result.id)
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
        return ClaimSetSnapshot(result=result, claims=claims, dependencies=dependencies)

    async def _find_result(
        self, document_id: uuid.UUID, *, any_parser: bool = False
    ) -> ClaimParseResult | None:
        statement = select(ClaimParseResult).where(ClaimParseResult.document_id == document_id)
        if any_parser:
            statement = statement.order_by(ClaimParseResult.created_at.desc()).limit(1)
        else:
            statement = statement.where(
                ClaimParseResult.parser_name == self._parser.name,
                ClaimParseResult.parser_version == self._parser.version,
            )
        return (await self._session.execute(statement)).scalars().first()

    async def _begin(
        self, document: Document, existing: ClaimParseResult | None
    ) -> ClaimParseResult:
        if existing is None:
            result = ClaimParseResult(
                id=uuid.uuid4(),
                document_id=document.id,
                parser_name=self._parser.name,
                parser_version=self._parser.version,
                status=ClaimParseStatus.PROCESSING,
            )
            self._session.add(result)
        else:
            result = existing
            await self._session.execute(delete(Claim).where(Claim.parse_result_id == result.id))
            result.status = ClaimParseStatus.PROCESSING
        result.claim_count = 0
        result.warning_count = 0
        result.warnings = []
        result.error_code = None
        result.error_message = None
        result.started_at = datetime.now(tz=UTC)
        result.completed_at = None
        await self._session.commit()
        await self._session.refresh(result)
        return result

    async def _load_pages(self, document_id: uuid.UUID) -> list[SourcePage]:
        rows = (
            (
                await self._session.execute(
                    select(DocumentPage)
                    .where(DocumentPage.document_id == document_id)
                    .order_by(DocumentPage.page_number)
                )
            )
            .scalars()
            .all()
        )
        return [
            SourcePage(document_id=document_id, page_number=row.page_number, text=row.text)
            for row in rows
        ]

    async def _persist(self, result: ClaimParseResult, parsed: ParsedClaimSet) -> None:
        """Write the whole graph and terminal status, or persist a safe terminal failure."""
        claims_by_number: dict[int, Claim] = {}
        for parsed_claim in parsed.claims:
            claim = Claim(
                id=uuid.uuid4(),
                parse_result_id=result.id,
                claim_number=parsed_claim.claim_number,
                claim_type=parsed_claim.claim_type,
                text=parsed_claim.text,
            )
            self._session.add(claim)
            claims_by_number[parsed_claim.claim_number] = claim
            for span in parsed_claim.spans:
                self._session.add(
                    ClaimSpan(
                        id=uuid.uuid4(),
                        claim_id=claim.id,
                        sequence_number=span.sequence_number,
                        page_number=span.page_number,
                        start_char=span.start_char,
                        end_char=span.end_char,
                    )
                )
        await self._session.flush()
        for parsed_claim in parsed.claims:
            dependent = claims_by_number[parsed_claim.claim_number]
            for referenced_number in parsed_claim.dependencies:
                referenced = claims_by_number.get(referenced_number)
                if referenced is None:
                    continue
                self._session.add(
                    ClaimDependency(
                        id=uuid.uuid4(),
                        parse_result_id=result.id,
                        dependent_claim_id=dependent.id,
                        referenced_claim_id=referenced.id,
                    )
                )
        result.claim_count = parsed.claim_count
        result.warning_count = parsed.warning_count
        result.warnings = [warning.as_dict() for warning in parsed.warnings]
        result.status = (
            ClaimParseStatus.NO_CLAIMS_FOUND if parsed.is_empty else ClaimParseStatus.COMPLETED
        )
        result.completed_at = datetime.now(tz=UTC)
        result_id = result.id
        try:
            await self._session.commit()
        except Exception as exc:
            await self._session.rollback()
            result.status = ClaimParseStatus.FAILED
            result.error_code = ErrorCode.INTERNAL_ERROR.value
            result.error_message = "Claim parsing failed while saving the claim graph."
            result.claim_count = 0
            result.warning_count = 0
            result.warnings = []
            result.completed_at = datetime.now(tz=UTC)
            logger.error(
                "claim graph persistence failed",
                extra={"parse_result_id": str(result_id), "claim_count": parsed.claim_count},
            )
            try:
                await self._session.commit()
            except Exception:
                result.status = ClaimParseStatus.PROCESSING
                result.error_code = None
                result.error_message = None
                result.completed_at = None
                raise
            await self._session.refresh(result)
            raise ClaimParsingFailed(result.error_message or "", result) from exc
        await self._session.refresh(result)

    async def _mark_failed(
        self, result: ClaimParseResult, code: str, message: str
    ) -> ClaimParseResult:
        await self._session.rollback()
        result.status = ClaimParseStatus.FAILED
        result.error_code = code[:64]
        result.error_message = message[:512]
        result.claim_count = 0
        result.warning_count = 0
        result.completed_at = datetime.now(tz=UTC)
        await self._session.commit()
        await self._session.refresh(result)
        return result

    def _log_outcome(
        self,
        document: Document,
        result: ClaimParseResult,
        started: float,
        *,
        page_count: int,
        dependency_count: int = 0,
    ) -> None:
        logger.info(
            "claim parsing finished",
            extra={
                "document_id": str(document.id),
                "parse_result_id": str(result.id),
                "parser_name": result.parser_name,
                "parser_version": result.parser_version,
                "page_count": page_count,
                "claim_count": result.claim_count,
                "dependency_count": dependency_count,
                "warning_count": result.warning_count,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                "status": result.status.value,
                "error_code": result.error_code,
            },
        )


_TERMINAL_SUCCESS = frozenset({ClaimParseStatus.COMPLETED, ClaimParseStatus.NO_CLAIMS_FOUND})
