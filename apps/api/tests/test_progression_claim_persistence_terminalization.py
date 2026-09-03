"""P13 regression for recoverable claim-graph persistence failure."""

from __future__ import annotations

from claimtrace_api.core.errors import ErrorCode
from claimtrace_api.db.models import ClaimParseResult, ClaimParseStatus, DocumentStatus
from claimtrace_api.services.claim_parsing import ClaimParsingFailed
from tests.claim_fixtures import KOREAN_CLAIM_SET
from tests.test_claim_parsing_service import FakePage, FakeSession, make_document, make_service


class FailGraphCommitOnceSession(FakeSession):
    """Fail exactly the graph/final-status commit; allow recovery persistence."""

    async def commit(self) -> None:
        await super().commit()
        if self.commits == 2:
            raise RuntimeError("synthetic database detail: graph commit lost")


async def test_recoverable_graph_commit_failure_terminalizes_same_result() -> None:
    document = make_document()
    session = FailGraphCommitOnceSession(pages=[FakePage(1, KOREAN_CLAIM_SET)])
    service = make_service(session)

    try:
        await service.parse(document)
    except ClaimParsingFailed as exc:
        failed = exc.result
    else:  # pragma: no cover - makes the acceptance failure explicit
        raise AssertionError("graph persistence failure must surface as ClaimParsingFailed")

    created = [obj for obj in session.added if isinstance(obj, ClaimParseResult)]
    assert created == [failed]
    assert failed.status is ClaimParseStatus.FAILED
    assert failed.error_code == ErrorCode.INTERNAL_ERROR.value
    assert failed.claim_count == 0
    assert failed.warning_count == 0
    assert failed.completed_at is not None
    assert "synthetic database detail" not in (failed.error_message or "")
    assert document.status is DocumentStatus.COMPLETED
    assert session.commits == 3
    assert session.rollbacks == 1

    # The fake query layer does not automatically expose newly committed rows.
    # Point it at the recovered row so the retry exercises real in-place reuse.
    session._existing = failed
    outcome = await service.parse(document)
    assert outcome.created is True
    assert outcome.result is failed
    assert failed.status is ClaimParseStatus.COMPLETED
    assert failed.error_code is None
