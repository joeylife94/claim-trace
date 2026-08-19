"""Versioned, idempotent persistence for deterministic claim elements."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from claimtrace_api.db.element_models import (
    ClaimElement,
    ClaimElementSpan,
    ElementDecompositionRun,
)
from claimtrace_api.db.models import Claim, ClaimParseResult, DocumentPage
from claimtrace_api.parsing.claims.base import ClaimTextSpan, ParsedClaim, SourcePage
from claimtrace_api.parsing.elements import DeterministicElementParser


@dataclass(frozen=True, slots=True)
class ElementDecompositionOutcome:
    run: ElementDecompositionRun
    created: bool


class ClaimElementService:
    """Persist one deterministic decomposition per claim/parser version."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        parser: DeterministicElementParser,
    ) -> None:
        self._session = session
        self._parser = parser

    async def decompose(self, claim_id: uuid.UUID) -> ElementDecompositionOutcome:
        existing = await self._find_run(claim_id)
        if existing is not None:
            return ElementDecompositionOutcome(run=existing, created=False)

        claim = await self._load_claim(claim_id)
        parse_result = await self._session.get(ClaimParseResult, claim.parse_result_id)
        if parse_result is None:  # pragma: no cover - foreign key guarantees this
            raise ValueError("claim parse result is missing")

        pages = await self._load_pages(parse_result.document_id)
        parsed_claim = ParsedClaim(
            claim_number=claim.claim_number,
            claim_type=claim.claim_type,
            spans=tuple(
                ClaimTextSpan(
                    sequence_number=span.sequence_number,
                    page_number=span.page_number,
                    start_char=span.start_char,
                    end_char=span.end_char,
                )
                for span in claim.spans
            ),
            text=claim.text,
        )
        decomposition = self._parser.parse(claim=parsed_claim, pages=pages)

        run = ElementDecompositionRun(
            id=uuid.uuid4(),
            claim_id=claim.id,
            parser_name=self._parser.name,
            parser_version=self._parser.version,
            element_count=len(decomposition.elements),
            warning_count=len(decomposition.warnings),
            warnings=[
                {"code": warning.code.value, "message": warning.message}
                for warning in decomposition.warnings
            ],
        )
        self._session.add(run)

        for parsed_element in decomposition.elements:
            element = ClaimElement(
                id=uuid.uuid4(),
                run_id=run.id,
                sequence_number=parsed_element.sequence_number,
                text=parsed_element.text,
            )
            self._session.add(element)
            for sequence_number, span in enumerate(parsed_element.spans):
                self._session.add(
                    ClaimElementSpan(
                        id=uuid.uuid4(),
                        element_id=element.id,
                        sequence_number=sequence_number,
                        page_number=span.page_number,
                        start_char=span.start_char,
                        end_char=span.end_char,
                    )
                )

        await self._session.commit()
        return ElementDecompositionOutcome(
            run=await self._require_loaded_run(run.id),
            created=True,
        )

    async def _find_run(self, claim_id: uuid.UUID) -> ElementDecompositionRun | None:
        statement = (
            select(ElementDecompositionRun)
            .where(
                ElementDecompositionRun.claim_id == claim_id,
                ElementDecompositionRun.parser_name == self._parser.name,
                ElementDecompositionRun.parser_version == self._parser.version,
            )
            .options(selectinload(ElementDecompositionRun.elements).selectinload(ClaimElement.spans))
        )
        return (await self._session.execute(statement)).scalars().first()

    async def _require_loaded_run(self, run_id: uuid.UUID) -> ElementDecompositionRun:
        statement = (
            select(ElementDecompositionRun)
            .where(ElementDecompositionRun.id == run_id)
            .options(selectinload(ElementDecompositionRun.elements).selectinload(ClaimElement.spans))
        )
        run = (await self._session.execute(statement)).scalars().one()
        return run

    async def _load_claim(self, claim_id: uuid.UUID) -> Claim:
        statement = select(Claim).where(Claim.id == claim_id).options(selectinload(Claim.spans))
        claim = (await self._session.execute(statement)).scalars().first()
        if claim is None:
            raise ValueError("claim not found")
        return claim

    async def _load_pages(self, document_id: uuid.UUID) -> tuple[SourcePage, ...]:
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
        return tuple(
            SourcePage(document_id=document_id, page_number=row.page_number, text=row.text)
            for row in rows
        )
