"""Claim parsing service behaviour that needs no database.

Covers the paths that are awkward to provoke against a real PostgreSQL: a commit
that fails mid-transaction, a parser that raises, and the structured log event.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from typing import Any

import pytest

from claimtrace_api.core.errors import AppError, ErrorCode
from claimtrace_api.db.models import (
    Claim,
    ClaimDependency,
    ClaimParseResult,
    ClaimParseStatus,
    ClaimSpan,
    ClaimType,
    Document,
    DocumentStatus,
)
from claimtrace_api.parsing.claims.base import (
    ClaimParserError,
    ClaimTextSpan,
    ParsedClaim,
    ParsedClaimSet,
    SourcePage,
)
from claimtrace_api.parsing.claims.korean_rules import KoreanRuleBasedClaimParser
from claimtrace_api.services.claim_parsing import ClaimParsingFailed, ClaimParsingService
from tests.claim_fixtures import KOREAN_CLAIM_SET
from tests.conftest import capture_logs

SERVICE_LOGGER = "claimtrace_api.services.claim_parsing"


class FakeResult:
    def __init__(self, rows: Sequence[Any] = ()) -> None:
        self._rows = list(rows)

    def scalars(self) -> FakeResult:
        return self

    def first(self) -> Any:
        return self._rows[0] if self._rows else None

    def all(self) -> list[Any]:
        return list(self._rows)


class FakeSession:
    """Async session stand-in.

    ``rows`` is consulted by type so one fake can serve the result lookup, the
    page load, and the claim reload without pretending to be a query planner.
    """

    def __init__(self, *, pages: Sequence[Any] = (), existing: Any = None) -> None:
        self.added: list[Any] = []
        self.commits = 0
        self.rollbacks = 0
        self.flushes = 0
        self._pages = list(pages)
        self._existing = existing

    async def execute(self, statement: Any, *_args: Any, **_kwargs: Any) -> FakeResult:
        rendered = str(statement)
        if "claim_parse_results" in rendered and "DELETE" not in rendered:
            return FakeResult([self._existing] if self._existing is not None else [])
        if "document_pages" in rendered:
            return FakeResult(self._pages)
        return FakeResult()

    def add(self, instance: Any) -> None:
        self.added.append(instance)

    async def flush(self) -> None:
        self.flushes += 1

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1

    async def refresh(self, _instance: Any) -> None:
        return None


def make_document(status: DocumentStatus = DocumentStatus.COMPLETED) -> Document:
    return Document(
        id=uuid.uuid4(),
        original_filename="patent.pdf",
        content_type="application/pdf",
        size_bytes=1024,
        sha256="a" * 64,
        storage_key="aa/" + "a" * 64 + ".pdf",
        status=status,
    )


class FakePage:
    def __init__(self, page_number: int, text: str) -> None:
        self.page_number = page_number
        self.text = text


def make_service(session: FakeSession, parser: Any = None) -> ClaimParsingService:
    return ClaimParsingService(
        session=session,  # type: ignore[arg-type]
        parser=parser or KoreanRuleBasedClaimParser(),
    )


# -- preconditions ----------------------------------------------------------


@pytest.mark.parametrize(
    "status",
    [DocumentStatus.UPLOADED, DocumentStatus.PROCESSING, DocumentStatus.FAILED],
)
async def test_only_a_completed_document_can_be_parsed(status: DocumentStatus) -> None:
    service = make_service(FakeSession())

    with pytest.raises(AppError) as excinfo:
        await service.parse(make_document(status))

    assert excinfo.value.code is ErrorCode.DOCUMENT_NOT_COMPLETED
    assert excinfo.value.status_code == 409


async def test_existing_completed_result_is_returned_without_reparsing() -> None:
    document = make_document()
    existing = ClaimParseResult(
        id=uuid.uuid4(),
        document_id=document.id,
        parser_name="korean-rule-based-claims",
        parser_version="0.1.0",
        status=ClaimParseStatus.COMPLETED,
        claim_count=4,
    )
    session = FakeSession(existing=existing)
    service = make_service(session)

    outcome = await service.parse(document)

    assert outcome.created is False
    assert outcome.result is existing
    assert session.added == []
    assert session.commits == 0


async def test_existing_no_claims_result_is_also_idempotent() -> None:
    document = make_document()
    existing = ClaimParseResult(
        id=uuid.uuid4(),
        document_id=document.id,
        parser_name="korean-rule-based-claims",
        parser_version="0.1.0",
        status=ClaimParseStatus.NO_CLAIMS_FOUND,
    )
    service = make_service(FakeSession(existing=existing))

    outcome = await service.parse(document)

    assert outcome.created is False
    assert outcome.result.status is ClaimParseStatus.NO_CLAIMS_FOUND


async def test_a_failed_result_is_retried_in_place() -> None:
    """The unique constraint means one row per parser version, so retries reuse it."""
    document = make_document()
    existing = ClaimParseResult(
        id=uuid.uuid4(),
        document_id=document.id,
        parser_name="korean-rule-based-claims",
        parser_version="0.1.0",
        status=ClaimParseStatus.FAILED,
        error_code="claim_parse_failed",
        error_message="previous attempt",
    )
    session = FakeSession(existing=existing, pages=[FakePage(1, KOREAN_CLAIM_SET)])
    service = make_service(session)

    outcome = await service.parse(document)

    assert outcome.created is True
    assert outcome.result is existing
    assert existing.status is ClaimParseStatus.COMPLETED
    assert existing.error_code is None
    assert existing.claim_count == 4


# -- transaction behaviour --------------------------------------------------


async def test_the_whole_graph_is_written_before_the_terminal_status() -> None:
    document = make_document()
    session = FakeSession(pages=[FakePage(1, KOREAN_CLAIM_SET)])
    service = make_service(session)

    outcome = await service.parse(document)

    claims = [obj for obj in session.added if isinstance(obj, Claim)]
    spans = [obj for obj in session.added if isinstance(obj, ClaimSpan)]
    edges = [obj for obj in session.added if isinstance(obj, ClaimDependency)]
    assert len(claims) == 4
    assert len(spans) == 4
    assert len(edges) == 6
    assert outcome.result.status is ClaimParseStatus.COMPLETED
    assert outcome.result.claim_count == len(claims)
    # One commit puts the result into 'processing', a second makes the graph and
    # the terminal status visible together.
    assert session.commits == 2
    assert session.flushes == 1


async def test_persistence_failure_rolls_back_and_leaves_processing() -> None:
    """A partially written graph must never surface as a completed parse."""

    class FailingSession(FakeSession):
        async def commit(self) -> None:
            await super().commit()
            if self.commits >= 2:
                raise RuntimeError("connection lost")

    document = make_document()
    session = FailingSession(pages=[FakePage(1, KOREAN_CLAIM_SET)])
    service = make_service(session)

    with pytest.raises(RuntimeError, match="connection lost"):
        await service.parse(document)

    assert session.rollbacks == 1
    result = next(obj for obj in session.added if isinstance(obj, ClaimParseResult))
    assert result.status is not ClaimParseStatus.COMPLETED
    # The document itself is untouched by a claim parsing failure.
    assert document.status is DocumentStatus.COMPLETED


async def test_parser_error_marks_the_result_failed_and_keeps_the_document_completed() -> None:
    class ExplodingParser:
        name = "exploding"
        version = "0.0.1"

        def parse(self, pages: Sequence[SourcePage]) -> ParsedClaimSet:
            raise ClaimParserError("overlapping_claim_spans", "Claims 1 and 2 overlap.")

    document = make_document()
    session = FakeSession(pages=[FakePage(1, KOREAN_CLAIM_SET)])
    service = make_service(session, ExplodingParser())

    with pytest.raises(ClaimParsingFailed) as excinfo:
        await service.parse(document)

    failed = excinfo.value.result
    assert failed.status is ClaimParseStatus.FAILED
    assert failed.error_code == "overlapping_claim_spans"
    assert failed.claim_count == 0
    assert excinfo.value.code is ErrorCode.CLAIM_PARSE_FAILED
    assert excinfo.value.status_code == 422
    assert document.status is DocumentStatus.COMPLETED


async def test_unexpected_parser_exception_is_recorded_as_an_internal_error() -> None:
    class BrokenParser:
        name = "broken"
        version = "0.0.1"

        def parse(self, pages: Sequence[SourcePage]) -> ParsedClaimSet:
            raise ZeroDivisionError("bug")

    document = make_document()
    service = make_service(FakeSession(pages=[FakePage(1, "text")]), BrokenParser())

    with pytest.raises(ClaimParsingFailed) as excinfo:
        await service.parse(document)

    assert excinfo.value.result.error_code == ErrorCode.INTERNAL_ERROR.value
    # The client-facing message says nothing about the underlying exception.
    assert "ZeroDivision" not in (excinfo.value.result.error_message or "")
    assert document.status is DocumentStatus.COMPLETED


async def test_no_claims_found_is_persisted_as_its_own_status() -> None:
    document = make_document()
    session = FakeSession(pages=[FakePage(1, "특허와 무관한 사내 문서입니다.")])
    service = make_service(session)

    outcome = await service.parse(document)

    assert outcome.created is True
    assert outcome.result.status is ClaimParseStatus.NO_CLAIMS_FOUND
    assert outcome.result.claim_count == 0
    assert [obj for obj in session.added if isinstance(obj, Claim)] == []


async def test_warnings_are_persisted_with_the_result() -> None:
    document = make_document()
    text = "【청구항 1】\n하우징.\n【청구항 2】\n제9항에 있어서, 금속.\n"
    session = FakeSession(pages=[FakePage(1, text)])
    service = make_service(session)

    outcome = await service.parse(document)

    assert outcome.result.warning_count == 1
    assert outcome.result.warnings[0]["code"] == "unresolved_dependency_reference"
    assert outcome.result.warnings[0]["claim_number"] == 2


async def test_persisted_claim_text_equals_its_ordered_spans() -> None:
    document = make_document()
    page_text = KOREAN_CLAIM_SET
    session = FakeSession(pages=[FakePage(1, page_text)])
    service = make_service(session)

    await service.parse(document)

    claims = {c.claim_number: c for c in session.added if isinstance(c, Claim)}
    spans: dict[uuid.UUID, list[ClaimSpan]] = {}
    for span in (obj for obj in session.added if isinstance(obj, ClaimSpan)):
        spans.setdefault(span.claim_id, []).append(span)

    for claim in claims.values():
        ordered = sorted(spans[claim.id], key=lambda span: span.sequence_number)
        rebuilt = "\n".join(page_text[s.start_char : s.end_char] for s in ordered)
        assert claim.text == rebuilt


# -- observability ----------------------------------------------------------


async def test_parse_event_carries_the_documented_fields() -> None:
    document = make_document()
    session = FakeSession(pages=[FakePage(1, KOREAN_CLAIM_SET)])
    service = make_service(session)

    with capture_logs(SERVICE_LOGGER, logging.INFO) as records:
        outcome = await service.parse(document)

    record = next(r for r in records if r.getMessage() == "claim parsing finished")
    assert record.document_id == str(document.id)
    assert record.parse_result_id == str(outcome.result.id)
    assert record.parser_name == "korean-rule-based-claims"
    assert record.parser_version == "0.1.0"
    assert record.page_count == 1
    assert record.claim_count == 4
    assert record.dependency_count == 6
    assert record.warning_count == 0
    assert record.status == "completed"
    assert record.error_code is None
    assert isinstance(record.duration_ms, float)


async def test_logs_never_contain_claim_text() -> None:
    marker = "기밀유지대상본문"
    document = make_document()
    text = f"【청구항 1】\n{marker}을 포함하는 장치.\n"
    service = make_service(FakeSession(pages=[FakePage(1, text)]))

    with capture_logs("claimtrace_api", logging.DEBUG) as records:
        await service.parse(document)

    assert records, "the capture must not be vacuously empty"
    rendered = " ".join(f"{r.getMessage()} {r.__dict__}" for r in records)
    assert marker not in rendered


async def test_failed_parse_event_reports_the_error_code() -> None:
    class ExplodingParser:
        name = "exploding"
        version = "0.0.1"

        def parse(self, pages: Sequence[SourcePage]) -> ParsedClaimSet:
            raise ClaimParserError("span_out_of_bounds", "Span outside page 1.")

    service = make_service(FakeSession(pages=[FakePage(1, "text")]), ExplodingParser())

    with (
        capture_logs(SERVICE_LOGGER, logging.INFO) as records,
        pytest.raises(ClaimParsingFailed),
    ):
        await service.parse(make_document())

    record = next(r for r in records if r.getMessage() == "claim parsing finished")
    assert record.status == "failed"
    assert record.error_code == "span_out_of_bounds"


# -- guard rails ------------------------------------------------------------


async def test_service_persists_exactly_the_parser_output() -> None:
    """The service adds no interpretation of its own to the parser's result."""

    class StaticParser:
        name = "static"
        version = "9.9.9"

        def parse(self, pages: Sequence[SourcePage]) -> ParsedClaimSet:
            return ParsedClaimSet(
                claims=(
                    ParsedClaim(
                        claim_number=7,
                        claim_type=ClaimType.UNKNOWN,
                        spans=(
                            ClaimTextSpan(
                                sequence_number=0, page_number=1, start_char=0, end_char=4
                            ),
                        ),
                        text="text",
                        dependencies=(),
                    ),
                ),
                parser_name="static",
                parser_version="9.9.9",
            )

    session = FakeSession(pages=[FakePage(1, "text")])
    service = make_service(session, StaticParser())

    await service.parse(make_document())

    claim = next(obj for obj in session.added if isinstance(obj, Claim))
    assert claim.claim_number == 7
    assert claim.claim_type is ClaimType.UNKNOWN
    assert claim.text == "text"
