"""PostgreSQL proof for versioned, idempotent claim-element persistence."""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from claimtrace_api.core.config import Settings
from claimtrace_api.db.element_models import ClaimElement, ClaimElementSpan, ElementDecompositionRun
from claimtrace_api.db.models import (
    Claim,
    ClaimParseResult,
    ClaimParseStatus,
    ClaimSpan,
    ClaimType,
    Document,
    DocumentPage,
    DocumentStatus,
)
from claimtrace_api.db.session import create_engine, create_session_factory
from claimtrace_api.parsing.elements import DeterministicElementParser
from claimtrace_api.services.claim_elements import ClaimElementService

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _seed_claim(session: AsyncSession) -> tuple[uuid.UUID, str]:
    document_id = uuid.uuid4()
    parse_result_id = uuid.uuid4()
    claim_id = uuid.uuid4()
    text = "센서부; 통신부"

    session.add(
        Document(
            id=document_id,
            original_filename="element-persistence.pdf",
            content_type="application/pdf",
            size_bytes=100,
            sha256=uuid.uuid4().hex + uuid.uuid4().hex,
            storage_key=f"test/{document_id}.pdf",
            status=DocumentStatus.COMPLETED,
            page_count=1,
            extracted_character_count=len(text),
        )
    )
    session.add(
        DocumentPage(
            id=uuid.uuid4(),
            document_id=document_id,
            page_number=1,
            text=text,
            character_count=len(text),
            text_sha256="0" * 64,
        )
    )
    session.add(
        ClaimParseResult(
            id=parse_result_id,
            document_id=document_id,
            status=ClaimParseStatus.COMPLETED,
            parser_name="test-claim-parser",
            parser_version="1",
            claim_count=1,
        )
    )
    session.add(
        Claim(
            id=claim_id,
            parse_result_id=parse_result_id,
            claim_number=1,
            claim_type=ClaimType.INDEPENDENT,
            text=text,
        )
    )
    session.add(
        ClaimSpan(
            id=uuid.uuid4(),
            claim_id=claim_id,
            sequence_number=0,
            page_number=1,
            start_char=0,
            end_char=len(text),
        )
    )
    await session.commit()
    return claim_id, text


async def test_same_parser_version_is_idempotent_and_preserves_source(
    integration_settings: Settings,
    clean_database: None,
) -> None:
    engine = create_engine(integration_settings)
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            claim_id, source_text = await _seed_claim(session)
            service = ClaimElementService(
                session=session,
                parser=DeterministicElementParser(),
            )

            first = await service.decompose(claim_id)
            second = await service.decompose(claim_id)

            assert first.created is True
            assert second.created is False
            assert second.run.id == first.run.id
            assert [element.sequence_number for element in first.run.elements] == [0, 1]
            assert [element.text for element in first.run.elements] == ["센서부;", "통신부"]

            run_count = await session.scalar(
                sa.select(sa.func.count()).select_from(ElementDecompositionRun)
            )
            element_count = await session.scalar(
                sa.select(sa.func.count()).select_from(ClaimElement)
            )
            span_count = await session.scalar(
                sa.select(sa.func.count()).select_from(ClaimElementSpan)
            )
            assert run_count == 1
            assert element_count == 2
            assert span_count == 2

            for element in first.run.elements:
                assert element.spans
                resolved = "".join(
                    source_text[span.start_char : span.end_char] for span in element.spans
                )
                assert resolved == element.text
                assert all(
                    0 <= span.start_char < span.end_char <= len(source_text)
                    for span in element.spans
                )
    finally:
        await engine.dispose()


async def test_new_parser_version_coexists_without_overwriting_prior_run(
    integration_settings: Settings,
    clean_database: None,
) -> None:
    class VersionTwoParser(DeterministicElementParser):
        version = "2"

    engine = create_engine(integration_settings)
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            claim_id, _ = await _seed_claim(session)
            first = await ClaimElementService(
                session=session,
                parser=DeterministicElementParser(),
            ).decompose(claim_id)
            second = await ClaimElementService(
                session=session,
                parser=VersionTwoParser(),
            ).decompose(claim_id)

            assert first.run.id != second.run.id
            assert first.run.parser_version == "1"
            assert second.run.parser_version == "2"
            run_count = await session.scalar(
                sa.select(sa.func.count()).select_from(ElementDecompositionRun)
            )
            assert run_count == 2
    finally:
        await engine.dispose()
