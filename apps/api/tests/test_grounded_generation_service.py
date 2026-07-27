"""The orchestration service, end to end, with no database and no model.

Every test here runs the *real* pipeline: the real context builder, the real
JSON extraction, the real schema validation, the real citation validator, and
the real span resolution. Only the two edges are replaced - retrieval returns a
scripted outcome, and the provider returns scripted bytes. A test that passes
here has exercised every layer except a socket and a query planner.
"""

from __future__ import annotations

import uuid
from typing import Any, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from claimtrace_api.core.config import Settings
from claimtrace_api.core.errors import AppError, ErrorCode
from claimtrace_api.grounding.draft import InsufficientReason
from claimtrace_api.llm.errors import (
    LLMProviderUnavailableError,
    LLMTimeoutError,
)
from claimtrace_api.llm.fake import FakeLLMProvider
from claimtrace_api.retrieval.base import RetrievalMode
from claimtrace_api.services.claim_search import ClaimSearchService
from claimtrace_api.services.grounded_generation import (
    CITATION_SEMANTICS_NOTE,
    INSUFFICIENT_MESSAGES,
    NO_INDEX_WARNING,
    OMITTED_EVIDENCE_WARNING,
    REPAIR_WARNING,
    GroundedGenerationService,
)
from claimtrace_api.services.llm_generation import LLMGenerationService
from tests.conftest import capture_logs
from tests.grounded_fixtures import (
    CLAIM_ONE,
    CLAIM_THREE,
    CLAIM_TWO,
    DOCUMENT_A,
    DOCUMENT_B,
    INJECTION_CLAIM_TEXTS,
    FailingSearchService,
    StubPageSession,
    StubSearchService,
    draft_json,
    make_outcome,
    make_search_result,
    page_text,
)

QUESTION = "통신부는 어떤 모듈을 포함하는가?"
PAGE = page_text(400)


def settings_for(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "environment": "test",
        "log_level": "WARNING",
        "database_url": "postgresql+psycopg://unused:unused@localhost:5432/unused",
        "embedding_provider": "fake",
        "grounded_max_evidence_candidates": 6,
        "grounded_max_evidence_characters": 5000,
        "grounded_repair_max_attempts": 1,
    }
    return Settings(**{**base, **overrides})


def build_service(
    *,
    outcome: Any = None,
    provider: FakeLLMProvider | None = None,
    session: Any = None,
    search: Any = None,
    settings: Settings | None = None,
) -> tuple[GroundedGenerationService, FakeLLMProvider, Any]:
    resolved_settings = settings or settings_for()
    # Scripted rather than synthesised by default, so a test that is about
    # retrieval wiring is not silently also a test of what the fake provider
    # happens to invent for the schema.
    fake = provider or FakeLLMProvider(
        structured_text=draft_json([("수집부는 복수의 센서로부터 측정값을 수집한다.", ("EV-001",))])
    )
    search_service = search or StubSearchService(
        outcome
        if outcome is not None
        else make_outcome([make_search_result(claim_number=1, text=CLAIM_ONE)])
    )
    page_session = session or StubPageSession({(DOCUMENT_A, 1): PAGE})
    service = GroundedGenerationService(
        search=cast(ClaimSearchService, search_service),
        llm=LLMGenerationService(provider=fake, settings=resolved_settings),
        session=cast(AsyncSession, page_session),
        settings=resolved_settings,
    )
    return service, fake, search_service


def two_claim_outcome() -> Any:
    return make_outcome(
        [
            make_search_result(claim_number=1, text=CLAIM_ONE, fused_rank=1),
            make_search_result(claim_number=2, text=CLAIM_TWO, fused_rank=2),
        ]
    )


class TestSuccessfulAnswer:
    async def test_an_answerable_question_returns_cited_statements(self):
        provider = FakeLLMProvider(
            structured_text=draft_json(
                [("통신부는 무선 근거리 통신 모듈을 포함한다.", ("EV-002",))]
            )
        )
        service, _, _ = build_service(outcome=two_claim_outcome(), provider=provider)

        answer = await service.answer(query=QUESTION, top_k=6)

        assert answer.insufficient_evidence is False
        assert answer.insufficient_reason is None
        assert len(answer.statements) == 1
        assert answer.statements[0].evidence_ids == ("EV-002",)
        assert answer.answer == "통신부는 무선 근거리 통신 모듈을 포함한다."

    async def test_only_cited_evidence_is_returned(self):
        provider = FakeLLMProvider(
            structured_text=draft_json([("통신부를 포함한다.", ("EV-002",))])
        )
        service, _, _ = build_service(outcome=two_claim_outcome(), provider=provider)

        answer = await service.answer(query=QUESTION, top_k=6)

        assert [evidence.entry.evidence_id for evidence in answer.evidence] == ["EV-002"]
        assert answer.evidence[0].entry.candidate.claim_number == 2
        assert answer.retrieval.included_evidence_count == 2

    async def test_citations_resolve_to_stored_page_text(self):
        provider = FakeLLMProvider(structured_text=draft_json([("수집부가 있다.", ("EV-001",))]))
        service, _, _ = build_service(
            outcome=make_outcome([make_search_result(pages=((1, 10, 60),))]), provider=provider
        )

        answer = await service.answer(query=QUESTION, top_k=6)

        span = answer.evidence[0].spans[0]
        assert span.locator.page_number == 1
        assert span.locator.start_char == 10
        assert span.locator.end_char == 60
        # The quote is the substring at those offsets, read by the server.
        assert span.quote == PAGE[10:60]

    async def test_multi_page_spans_are_resolved_in_order(self):
        provider = FakeLLMProvider(structured_text=draft_json([("수집부가 있다.", ("EV-001",))]))
        service, _, _ = build_service(
            outcome=make_outcome([make_search_result(pages=((1, 300, 400), (2, 0, 50)))]),
            provider=provider,
            session=StubPageSession({(DOCUMENT_A, 1): PAGE, (DOCUMENT_A, 2): PAGE}),
        )

        answer = await service.answer(query=QUESTION, top_k=6)

        spans = answer.evidence[0].spans
        assert [span.locator.page_number for span in spans] == [1, 2]
        assert spans[0].quote == PAGE[300:400]
        assert spans[1].quote == PAGE[0:50]
        assert answer.evidence[0].entry.candidate.crosses_pages

    async def test_the_answer_is_composed_from_statements_only(self):
        provider = FakeLLMProvider(
            structured_text=draft_json(
                [
                    ("수집부는 측정값을 수집한다.", ("EV-001",)),
                    ("통신부는 무선 모듈을 포함한다.", ("EV-002",)),
                ]
            )
        )
        service, _, _ = build_service(outcome=two_claim_outcome(), provider=provider)

        answer = await service.answer(query=QUESTION, top_k=6)

        assert answer.answer == "수집부는 측정값을 수집한다.\n통신부는 무선 모듈을 포함한다."

    async def test_provider_and_model_metadata_are_carried_through(self):
        provider = FakeLLMProvider(
            model="scripted-model",
            model_version="7",
            structured_text=draft_json([("수집부가 있다.", ("EV-001",))]),
        )
        service, _, _ = build_service(provider=provider)

        answer = await service.answer(query=QUESTION, top_k=6)

        assert answer.generation is not None
        assert answer.generation.provider == "fake"
        assert answer.generation.model == "scripted-model"
        assert answer.generation.model_version == "7"
        assert answer.generation.usage.input_tokens is not None

    async def test_the_citation_semantics_note_is_always_attached(self):
        """A grounded answer must not be mistaken for a verified one."""
        provider = FakeLLMProvider(structured_text=draft_json([("수집부가 있다.", ("EV-001",))]))
        service, _, _ = build_service(provider=provider)

        answer = await service.answer(query=QUESTION, top_k=6)

        assert CITATION_SEMANTICS_NOTE in answer.warnings

    async def test_the_unscripted_fake_provider_produces_a_valid_answer(self):
        """The offline default has to work, not merely fail politely.

        ``LLM_PROVIDER=fake`` is what `docker compose up` runs with, and it is
        what CI and any air-gapped checkout have. If the fake could not satisfy
        this schema, the grounded endpoint would need a model server to be
        exercised even once - so this is a guarantee about the project, not a
        detail of the double.
        """
        service, provider, _ = build_service(provider=FakeLLMProvider())

        answer = await service.answer(query=QUESTION, top_k=6)

        assert len(provider.calls) == 1
        assert answer.statements
        assert answer.statements[0].evidence_ids == ("EV-001",)
        assert answer.evidence[0].spans[0].quote == PAGE[0:40]


class TestRetrievalWiring:
    async def test_the_document_filter_reaches_retrieval(self):
        service, _, search = build_service()
        await service.answer(query=QUESTION, document_ids=[DOCUMENT_B], top_k=6)
        assert search.calls[0]["document_ids"] == [DOCUMENT_B]

    async def test_duplicate_document_ids_are_collapsed_deterministically(self):
        service, _, search = build_service()
        await service.answer(
            query=QUESTION, document_ids=[DOCUMENT_B, DOCUMENT_A, DOCUMENT_B], top_k=6
        )
        assert search.calls[0]["document_ids"] == [DOCUMENT_B, DOCUMENT_A]

    @pytest.mark.parametrize("mode", list(RetrievalMode))
    async def test_the_retrieval_mode_reaches_retrieval(self, mode: RetrievalMode):
        service, _, search = build_service()
        await service.answer(query=QUESTION, mode=mode, top_k=6)
        assert search.calls[0]["mode"] is mode

    async def test_candidate_counts_come_from_configuration_not_the_caller(self):
        settings = settings_for(dense_candidate_count=17, lexical_candidate_count=19)
        service, _, search = build_service(settings=settings)
        await service.answer(query=QUESTION, top_k=6)
        assert search.calls[0]["dense_candidate_count"] == 17
        assert search.calls[0]["lexical_candidate_count"] == 19

    async def test_top_k_reaches_retrieval(self):
        service, _, search = build_service()
        await service.answer(query=QUESTION, top_k=3)
        assert search.calls[0]["top_k"] == 3

    async def test_a_retrieval_failure_is_not_swallowed(self):
        service, _, _ = build_service(
            search=FailingSearchService(AppError(ErrorCode.INTERNAL_ERROR, "boom"))
        )
        with pytest.raises(AppError) as caught:
            await service.answer(query=QUESTION, top_k=6)
        assert caught.value.code is ErrorCode.INTERNAL_ERROR


class TestInsufficientEvidence:
    async def test_zero_retrieval_bypasses_the_provider_entirely(self):
        """Asking a model to answer from nothing is asking it to answer from memory."""
        service, provider, _ = build_service(outcome=make_outcome([]))

        answer = await service.answer(query=QUESTION, top_k=6)

        assert provider.calls == []
        assert answer.insufficient_evidence is True
        assert answer.insufficient_reason is InsufficientReason.NO_RETRIEVED_EVIDENCE
        assert answer.generation is None
        assert answer.evidence == ()
        assert answer.answer == INSUFFICIENT_MESSAGES[InsufficientReason.NO_RETRIEVED_EVIDENCE]

    async def test_an_unindexed_corpus_is_reported_as_a_warning(self):
        service, provider, _ = build_service(outcome=make_outcome([], searched_index_run_count=0))
        answer = await service.answer(query=QUESTION, top_k=6)
        assert NO_INDEX_WARNING in answer.warnings
        assert answer.insufficient_evidence is True
        assert provider.calls == []

    async def test_a_model_declared_insufficiency_is_a_successful_outcome(self):
        provider = FakeLLMProvider(
            structured_text=draft_json(
                [], insufficient_evidence=True, insufficient_reason="evidence_not_specific_enough"
            )
        )
        service, _, _ = build_service(provider=provider)

        answer = await service.answer(query=QUESTION, top_k=6)

        assert answer.insufficient_evidence is True
        assert answer.insufficient_reason is InsufficientReason.EVIDENCE_NOT_SPECIFIC_ENOUGH
        assert answer.statements == ()
        # The limitation text is the server's, chosen by enum - never model prose.
        assert (
            answer.answer == INSUFFICIENT_MESSAGES[InsufficientReason.EVIDENCE_NOT_SPECIFIC_ENOUGH]
        )

    async def test_a_partial_answer_keeps_its_validated_statements(self):
        provider = FakeLLMProvider(
            structured_text=draft_json(
                [("통신부는 무선 모듈을 포함한다.", ("EV-001",))],
                insufficient_evidence=True,
                insufficient_reason="conflicting_evidence",
            )
        )
        service, _, _ = build_service(provider=provider)

        answer = await service.answer(query=QUESTION, top_k=6)

        assert answer.insufficient_evidence is True
        assert len(answer.statements) == 1
        assert answer.answer.startswith(
            INSUFFICIENT_MESSAGES[InsufficientReason.CONFLICTING_EVIDENCE]
        )
        assert "통신부는 무선 모듈을 포함한다." in answer.answer


class TestInvalidModelOutput:
    async def test_an_unknown_evidence_id_is_rejected_after_repair(self):
        provider = FakeLLMProvider(structured_text=draft_json([("침해한다.", ("EV-999",))]))
        service, _, _ = build_service(provider=provider)

        with pytest.raises(AppError) as caught:
            await service.answer(query=QUESTION, top_k=6)
        assert caught.value.code is ErrorCode.GROUNDED_REPAIR_FAILED

    async def test_an_unknown_id_without_repair_reports_the_specific_code(self):
        provider = FakeLLMProvider(structured_text=draft_json([("침해한다.", ("EV-999",))]))
        service, _, _ = build_service(
            provider=provider, settings=settings_for(grounded_repair_max_attempts=0)
        )

        with pytest.raises(AppError) as caught:
            await service.answer(query=QUESTION, top_k=6)
        assert caught.value.code is ErrorCode.GROUNDED_UNKNOWN_EVIDENCE_ID
        assert len(provider.calls) == 1

    async def test_malformed_json_surfaces_the_provider_error(self):
        provider = FakeLLMProvider(structured_text="{not json at all")
        service, _, _ = build_service(provider=provider)

        with pytest.raises(AppError) as caught:
            await service.answer(query=QUESTION, top_k=6)
        assert caught.value.code is ErrorCode.LLM_MALFORMED_JSON

    async def test_valid_json_of_the_wrong_shape_surfaces_a_schema_error(self):
        provider = FakeLLMProvider(structured_text='{"answer": "침해에 해당합니다"}')
        service, _, _ = build_service(provider=provider)

        with pytest.raises(AppError) as caught:
            await service.answer(query=QUESTION, top_k=6)
        assert caught.value.code is ErrorCode.LLM_STRUCTURED_OUTPUT_VALIDATION_FAILED

    async def test_a_contradictory_answer_without_repair_is_invalid_output(self):
        provider = FakeLLMProvider(structured_text=draft_json([], insufficient_evidence=True))
        service, _, _ = build_service(
            provider=provider, settings=settings_for(grounded_repair_max_attempts=0)
        )

        with pytest.raises(AppError) as caught:
            await service.answer(query=QUESTION, top_k=6)
        assert caught.value.code is ErrorCode.GROUNDED_OUTPUT_INVALID

    async def test_no_invalid_output_is_partially_returned(self):
        """One good statement beside one fabricated citation returns nothing."""
        provider = FakeLLMProvider(
            structured_text=draft_json(
                [
                    ("수집부는 측정값을 수집한다.", ("EV-001",)),
                    ("따라서 침해에 해당한다.", ("EV-999",)),
                ]
            )
        )
        service, _, _ = build_service(
            provider=provider, settings=settings_for(grounded_repair_max_attempts=0)
        )
        with pytest.raises(AppError):
            await service.answer(query=QUESTION, top_k=6)


class TestProviderFailures:
    async def test_an_unavailable_provider_maps_to_the_existing_taxonomy(self):
        provider = FakeLLMProvider(
            fail_with=LLMProviderUnavailableError("down", provider="fake", model="m")
        )
        service, _, _ = build_service(provider=provider)

        with pytest.raises(AppError) as caught:
            await service.answer(query=QUESTION, top_k=6)
        assert caught.value.code is ErrorCode.LLM_PROVIDER_UNAVAILABLE

    async def test_a_timeout_is_never_repaired(self):
        """Repair corrects a rule violation. A timeout is not one.

        Retrying it here would double the wait a caller already gave up on, and
        the transport layer already has a retry policy for what it can replay.
        """
        provider = FakeLLMProvider(
            fail_with=LLMTimeoutError("too slow", provider="fake", model="m")
        )
        service, _, _ = build_service(provider=provider)

        with pytest.raises(AppError) as caught:
            await service.answer(query=QUESTION, top_k=6)
        assert caught.value.code is ErrorCode.LLM_REQUEST_TIMEOUT
        assert len(provider.calls) == 1

    async def test_grounded_generation_can_be_turned_off(self):
        service, provider, search = build_service(
            settings=settings_for(grounded_generation_enabled=False)
        )
        with pytest.raises(AppError) as caught:
            await service.answer(query=QUESTION, top_k=6)
        assert caught.value.code is ErrorCode.GROUNDED_GENERATION_UNAVAILABLE
        # Nothing was searched and nothing was generated.
        assert search.calls == []
        assert provider.calls == []


class TestRepair:
    def scripted(self, first: str, second: str) -> FakeLLMProvider:
        return FakeLLMProvider(structured_text=[first, second])

    async def test_an_unknown_id_is_corrected_on_one_repair(self):
        provider = self.scripted(
            draft_json([("통신부를 포함한다.", ("EV-999",))]),
            draft_json([("통신부는 무선 근거리 통신 모듈을 포함한다.", ("EV-002",))]),
        )
        service, _, _ = build_service(outcome=two_claim_outcome(), provider=provider)

        answer = await service.answer(query=QUESTION, top_k=6)

        assert len(provider.calls) == 2
        assert answer.statements[0].evidence_ids == ("EV-002",)
        assert REPAIR_WARNING in answer.warnings

    async def test_a_contradictory_flag_is_corrected_on_one_repair(self):
        provider = self.scripted(
            draft_json([], insufficient_evidence=True),
            draft_json([], insufficient_evidence=True, insufficient_reason="conflicting_evidence"),
        )
        service, _, _ = build_service(provider=provider)

        answer = await service.answer(query=QUESTION, top_k=6)

        assert answer.insufficient_reason is InsufficientReason.CONFLICTING_EVIDENCE
        assert len(provider.calls) == 2

    async def test_repair_reuses_the_same_evidence_and_adds_only_safe_feedback(self):
        provider = self.scripted(
            draft_json([("통신부를 포함한다.", ("EV-999",))]),
            draft_json([("통신부는 무선 모듈을 포함한다.", ("EV-001",))]),
        )
        service, _, _ = build_service(outcome=two_claim_outcome(), provider=provider)

        await service.answer(query=QUESTION, top_k=6)

        first, second = (call.request for call in provider.calls)
        assert first is not None and second is not None
        first_prompt = first.messages[-1].content
        second_prompt = second.messages[-1].content

        # Same evidence, same ids, one appended instruction.
        assert second_prompt.startswith(first_prompt)
        assert second_prompt.count("<evidence id=") == first_prompt.count("<evidence id=")
        assert "EV-001, EV-002" in second_prompt
        # The rejected statement is not echoed back into the prompt.
        assert "통신부를 포함한다." not in second_prompt[len(first_prompt) :]
        # The system instructions are unchanged between attempts.
        assert first.messages[0].content == second.messages[0].content

    async def test_repair_does_not_run_retrieval_again(self):
        provider = self.scripted(
            draft_json([("통신부를 포함한다.", ("EV-999",))]),
            draft_json([("통신부는 무선 모듈을 포함한다.", ("EV-001",))]),
        )
        service, _, search = build_service(provider=provider)

        await service.answer(query=QUESTION, top_k=6)

        assert len(search.calls) == 1

    async def test_a_failed_repair_reports_the_repair_code(self):
        provider = self.scripted(
            draft_json([("가짜.", ("EV-999",))]),
            draft_json([("여전히 가짜입니다.", ("EV-888",))]),
        )
        service, _, _ = build_service(provider=provider)

        with pytest.raises(AppError) as caught:
            await service.answer(query=QUESTION, top_k=6)
        assert caught.value.code is ErrorCode.GROUNDED_REPAIR_FAILED
        assert len(provider.calls) == 2

    async def test_repair_is_bounded_by_configuration(self):
        provider = FakeLLMProvider(structured_text=draft_json([("가짜입니다.", ("EV-999",))]))
        service, _, _ = build_service(
            provider=provider, settings=settings_for(grounded_repair_max_attempts=2)
        )

        with pytest.raises(AppError):
            await service.answer(query=QUESTION, top_k=6)
        # Three calls: the original plus two repairs, and no more.
        assert len(provider.calls) == 3

    async def test_no_repair_is_attempted_when_the_first_answer_is_valid(self):
        provider = FakeLLMProvider(structured_text=draft_json([("수집부가 있다.", ("EV-001",))]))
        service, _, _ = build_service(provider=provider)

        answer = await service.answer(query=QUESTION, top_k=6)

        assert len(provider.calls) == 1
        assert REPAIR_WARNING not in answer.warnings


class TestContextBudget:
    async def test_lower_ranked_evidence_is_omitted_and_reported(self):
        outcome = make_outcome(
            [make_search_result(claim_number=n, text=CLAIM_ONE, fused_rank=n) for n in range(1, 6)]
        )
        provider = FakeLLMProvider(structured_text=draft_json([("수집부가 있다.", ("EV-001",))]))
        service, _, _ = build_service(
            outcome=outcome,
            provider=provider,
            settings=settings_for(grounded_max_evidence_candidates=2),
        )

        answer = await service.answer(query=QUESTION, top_k=6)

        assert answer.retrieval.retrieved_candidate_count == 5
        assert answer.retrieval.included_evidence_count == 2
        assert answer.retrieval.omitted_evidence_count == 3
        assert OMITTED_EVIDENCE_WARNING in answer.warnings

    async def test_an_oversize_top_claim_is_a_context_error(self):
        outcome = make_outcome([make_search_result(text="가" * 4000)])
        service, _, _ = build_service(
            outcome=outcome, settings=settings_for(grounded_max_evidence_characters=500)
        )

        with pytest.raises(AppError) as caught:
            await service.answer(query=QUESTION, top_k=6)
        assert caught.value.code is ErrorCode.GROUNDED_CONTEXT_TOO_LARGE

    async def test_an_oversize_question_is_a_context_error(self):
        service, _, _ = build_service(settings=settings_for(grounded_max_question_characters=32))
        with pytest.raises(AppError) as caught:
            await service.answer(query="질" * 100, top_k=6)
        assert caught.value.code is ErrorCode.GROUNDED_CONTEXT_TOO_LARGE

    async def test_an_empty_question_is_refused_before_retrieval(self):
        service, provider, search = build_service()
        with pytest.raises(AppError) as caught:
            await service.answer(query="   ", top_k=6)
        assert caught.value.code is ErrorCode.LLM_INVALID_REQUEST
        assert search.calls == []
        assert provider.calls == []


class TestCitationResolution:
    async def test_a_span_that_does_not_fit_its_page_is_an_error(self):
        """The stored spans and the stored page text disagreeing is a real fault.

        Reported rather than truncated: a clipped quote is exactly the failure
        the locator system exists to prevent.
        """
        provider = FakeLLMProvider(structured_text=draft_json([("수집부가 있다.", ("EV-001",))]))
        service, _, _ = build_service(
            outcome=make_outcome([make_search_result(pages=((1, 0, 9999),))]),
            provider=provider,
        )

        with pytest.raises(AppError) as caught:
            await service.answer(query=QUESTION, top_k=6)
        assert caught.value.code is ErrorCode.GROUNDED_CITATION_RESOLUTION_FAILED

    async def test_a_missing_page_is_an_error(self):
        provider = FakeLLMProvider(structured_text=draft_json([("수집부가 있다.", ("EV-001",))]))
        service, _, _ = build_service(
            outcome=make_outcome([make_search_result(pages=((9, 0, 10),))]),
            provider=provider,
        )

        with pytest.raises(AppError) as caught:
            await service.answer(query=QUESTION, top_k=6)
        assert caught.value.code is ErrorCode.GROUNDED_CITATION_RESOLUTION_FAILED

    async def test_uncited_evidence_is_never_resolved(self):
        """Resolution costs a query, and unused evidence is not part of the answer."""
        provider = FakeLLMProvider(structured_text=draft_json([("수집부가 있다.", ("EV-001",))]))
        service, _, _ = build_service(
            outcome=make_outcome(
                [
                    make_search_result(claim_number=1, fused_rank=1),
                    # Only reachable through a page the stub does not serve, so
                    # resolving it would fail loudly rather than pass quietly.
                    make_search_result(claim_number=2, fused_rank=2, pages=((77, 0, 10),)),
                ]
            ),
            provider=provider,
        )

        answer = await service.answer(query=QUESTION, top_k=6)

        assert [evidence.entry.evidence_id for evidence in answer.evidence] == ["EV-001"]


class TestPromptInjection:
    async def test_hostile_claim_text_cannot_authorise_a_citation(self):
        """The whole corpus as evidence, and a model that does what it is told.

        The forged id is the one the injected text demanded. It resolves to
        nothing, so the answer is refused rather than served with a fake source.
        """
        outcome = make_outcome(
            [
                make_search_result(claim_number=number, text=text, fused_rank=number)
                for number, text in enumerate(INJECTION_CLAIM_TEXTS.values(), start=1)
            ]
        )
        provider = FakeLLMProvider(structured_text=draft_json([("침해에 해당한다.", ("EV-999",))]))
        service, _, _ = build_service(
            outcome=outcome,
            provider=provider,
            settings=settings_for(
                grounded_repair_max_attempts=0, grounded_max_evidence_candidates=10
            ),
        )

        with pytest.raises(AppError) as caught:
            await service.answer(query=QUESTION, top_k=10)
        assert caught.value.code is ErrorCode.GROUNDED_UNKNOWN_EVIDENCE_ID

    async def test_hostile_claim_text_is_still_ordinary_citable_evidence(self):
        """It is evidence, not a threat to be filtered out.

        A claim that contains an injection attempt is still a real claim in a
        real document, and a statement citing it resolves to its real span.
        """
        outcome = make_outcome(
            [make_search_result(text=INJECTION_CLAIM_TEXTS["ignore_previous"], pages=((1, 0, 30),))]
        )
        provider = FakeLLMProvider(
            structured_text=draft_json(
                [("이 청구항은 지시문 형태의 문장을 포함한다.", ("EV-001",))]
            )
        )
        service, _, _ = build_service(outcome=outcome, provider=provider)

        answer = await service.answer(query=QUESTION, top_k=6)

        assert answer.evidence[0].spans[0].quote == PAGE[0:30]

    async def test_a_model_generated_locator_has_nowhere_to_go(self):
        """Even a model that tries to supply one is rejected by the schema."""
        provider = FakeLLMProvider(
            structured_text=draft_json(
                [("수집부가 있다.", ("EV-001",))],
                extra={"page_number": 4, "start_char": 0, "end_char": 100},
            )
        )
        service, _, _ = build_service(provider=provider)

        with pytest.raises(AppError) as caught:
            await service.answer(query=QUESTION, top_k=6)
        assert caught.value.code is ErrorCode.LLM_STRUCTURED_OUTPUT_VALIDATION_FAILED


class TestSideEffects:
    async def test_nothing_is_written(self):
        """The session is used for reading page text and for nothing else."""
        session = StubPageSession({(DOCUMENT_A, 1): PAGE})
        provider = FakeLLMProvider(structured_text=draft_json([("수집부가 있다.", ("EV-001",))]))
        service, _, _ = build_service(provider=provider, session=session)

        await service.answer(query=QUESTION, top_k=6)

        # A write would have raised AttributeError: the stub has no add, no
        # add_all, and no commit, which is the assertion.
        assert not hasattr(session, "commit")
        assert not hasattr(session, "add")

    async def test_the_service_holds_no_state_between_questions(self):
        provider = FakeLLMProvider(structured_text=draft_json([("수집부가 있다.", ("EV-001",))]))
        service, _, _ = build_service(provider=provider)

        first = await service.answer(query=QUESTION, top_k=6)
        second = await service.answer(query="다른 질문입니다.", top_k=6)

        assert first.answer == second.answer
        assert first.evidence[0].entry.evidence_id == second.evidence[0].entry.evidence_id


class TestLogging:
    async def test_the_log_line_carries_counts_and_never_content(self):
        provider = FakeLLMProvider(
            structured_text=draft_json([("통신부는 무선 모듈을 포함한다.", ("EV-001",))])
        )
        service, _, _ = build_service(outcome=two_claim_outcome(), provider=provider)

        with capture_logs("claimtrace_api.services.grounded_generation") as records:
            await service.answer(query=QUESTION, top_k=6)

        finished = [r for r in records if r.getMessage() == "grounded answer finished"]
        assert len(finished) == 1
        record = finished[0]

        assert record.question_length == len(QUESTION)
        assert len(record.question_hash_prefix) == 12
        assert record.statement_count == 1
        assert record.cited_evidence_count == 1
        assert record.included_evidence_count == 2
        assert record.insufficient_evidence is False
        assert record.repair_attempts == 0
        assert record.provider == "fake"

        rendered = str(record.__dict__)
        for secret in (QUESTION, CLAIM_ONE, CLAIM_TWO, "통신부는 무선 모듈을 포함한다."):
            assert secret not in rendered

    async def test_a_rejected_answer_logs_the_violation_and_no_text(self):
        provider = FakeLLMProvider(
            structured_text=draft_json([("이 문장은 로그에 남으면 안 된다.", ("EV-999",))])
        )
        service, _, _ = build_service(
            provider=provider, settings=settings_for(grounded_repair_max_attempts=0)
        )

        with (
            capture_logs("claimtrace_api.services.grounded_generation") as records,
            pytest.raises(AppError),
        ):
            await service.answer(query=QUESTION, top_k=6)

        rejected = [r for r in records if r.getMessage() == "grounded output rejected"]
        assert len(rejected) == 1
        assert rejected[0].violation == "unknown_evidence_id"
        assert "이 문장은 로그에 남으면 안 된다." not in str(rejected[0].__dict__)


async def test_a_claim_type_and_dependency_graph_reach_the_answer():
    from claimtrace_api.db.models import ClaimType

    outcome = make_outcome(
        [
            make_search_result(
                claim_number=3,
                text=CLAIM_THREE,
                claim_type=ClaimType.DEPENDENT,
                depends_on=[1],
            )
        ]
    )
    provider = FakeLLMProvider(structured_text=draft_json([("온도 센서를 포함한다.", ("EV-001",))]))
    service, _, _ = build_service(outcome=outcome, provider=provider)

    answer = await service.answer(query=QUESTION, top_k=6)

    evidence = answer.evidence[0]
    assert evidence.entry.candidate.claim_type is ClaimType.DEPENDENT
    assert evidence.entry.candidate.depends_on == (1,)
    assert evidence.entry.candidate.claim_number == 3
    assert isinstance(evidence.entry.candidate.document_id, uuid.UUID)
