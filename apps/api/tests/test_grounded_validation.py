"""Post-generation validation: which drafts become answers.

The schema proved the draft had the right shape. These tests are about whether it
has the right content, which for this phase means one thing - that every
statement is attached to an identifier this request issued.
"""

from __future__ import annotations

import pytest

from claimtrace_api.grounding.draft import GroundedAnswerDraft, InsufficientReason
from claimtrace_api.grounding.evidence import EvidenceCatalog
from claimtrace_api.grounding.validation import (
    GroundedOutputError,
    GroundedViolation,
    OutputLimits,
    validate_draft,
)
from tests.grounded_fixtures import CLAIM_ONE, DOCUMENT_B, make_candidate, make_catalog

LIMITS = OutputLimits(
    max_statements=8, max_statement_characters=600, max_evidence_ids_per_statement=4
)

#: Ordinary statement text for cases that are about something other than the
#: statement. Real sentences rather than placeholders, because the filler policy
#: correctly drops a one-syllable "가." and would quietly change what these
#: tests are exercising.
STATEMENT = "수집부는 복수의 센서로부터 측정값을 수집한다."
SECOND_STATEMENT = "통신부는 무선 근거리 통신 모듈을 포함한다."
THIRD_STATEMENT = "저장부는 측정값을 저장한다."


def draft(
    statements: list[tuple[str, list[str]]],
    *,
    insufficient_evidence: bool = False,
    insufficient_reason: str | None = None,
) -> GroundedAnswerDraft:
    return GroundedAnswerDraft.model_validate(
        {
            "supported_statements": [
                {"text": text, "evidence_ids": ids} for text, ids in statements
            ],
            "insufficient_evidence": insufficient_evidence,
            "insufficient_reason": insufficient_reason,
        }
    )


def validate(
    draft_value: GroundedAnswerDraft,
    *,
    catalog: EvidenceCatalog | None = None,
    limits: OutputLimits = LIMITS,
):
    return validate_draft(draft_value, catalog=catalog or make_catalog(3), limits=limits)


class TestAcceptedAnswers:
    def test_statements_citing_issued_ids_are_accepted(self):
        answer = validate(
            draft(
                [
                    ("수집부는 복수의 센서로부터 측정값을 수집한다.", ["EV-001"]),
                    ("통신부는 무선 근거리 통신 모듈을 포함한다.", ["EV-002"]),
                ]
            )
        )
        assert [statement.text for statement in answer.statements] == [
            "수집부는 복수의 센서로부터 측정값을 수집한다.",
            "통신부는 무선 근거리 통신 모듈을 포함한다.",
        ]
        assert answer.insufficient_evidence is False

    def test_statement_text_is_stripped(self):
        answer = validate(draft([("  온도 센서를 포함한다.  \n", ["EV-001"])]))
        assert answer.statements[0].text == "온도 센서를 포함한다."

    def test_only_cited_evidence_is_returned(self):
        """Retrieved-but-unused evidence is not part of the answer.

        Returning it would present claims the model never relied on as though
        they supported something.
        """
        answer = validate(draft([("수집부가 있다.", ["EV-003"])]))
        assert [entry.evidence_id for entry in answer.cited] == ["EV-003"]

    def test_cited_evidence_is_ordered_by_catalog_not_by_mention(self):
        answer = validate(
            draft(
                [
                    (STATEMENT, ["EV-003"]),
                    (SECOND_STATEMENT, ["EV-001"]),
                    (THIRD_STATEMENT, ["EV-002"]),
                ]
            )
        )
        assert [entry.evidence_id for entry in answer.cited] == ["EV-001", "EV-002", "EV-003"]

    def test_insufficient_evidence_with_a_reason_is_accepted(self):
        answer = validate(
            draft([], insufficient_evidence=True, insufficient_reason="conflicting_evidence")
        )
        assert answer.insufficient_evidence is True
        assert answer.insufficient_reason is InsufficientReason.CONFLICTING_EVIDENCE
        assert answer.statements == ()
        assert answer.cited == ()

    def test_insufficient_evidence_may_still_carry_validated_statements(self):
        """A partial answer is allowed - and its statements pass the same check."""
        answer = validate(
            draft(
                [("통신부를 포함한다.", ["EV-001"])],
                insufficient_evidence=True,
                insufficient_reason="evidence_not_specific_enough",
            )
        )
        assert answer.insufficient_evidence is True
        assert len(answer.statements) == 1
        assert [entry.evidence_id for entry in answer.cited] == ["EV-001"]


class TestEvidenceIdRejection:
    def test_an_unknown_id_is_rejected(self):
        with pytest.raises(GroundedOutputError) as caught:
            validate(draft([("침해에 해당한다.", ["EV-999"])]))
        assert caught.value.violation is GroundedViolation.UNKNOWN_EVIDENCE_ID

    def test_an_id_beyond_the_catalog_is_rejected(self):
        """EV-004 is well formed and was not issued for a three-entry catalog."""
        with pytest.raises(GroundedOutputError) as caught:
            validate(draft([(STATEMENT, ["EV-004"])]), catalog=make_catalog(3))
        assert caught.value.violation is GroundedViolation.UNKNOWN_EVIDENCE_ID

    @pytest.mark.parametrize("value", ["ev-001", "EV-1", " EV-001", "EV-001 ", "EV-0001"])
    def test_a_malformed_id_is_rejected_rather_than_normalised(self, value: str):
        with pytest.raises(GroundedOutputError) as caught:
            validate(draft([(STATEMENT, [value])]))
        assert caught.value.violation is GroundedViolation.MALFORMED_EVIDENCE_ID

    def test_a_claim_number_is_not_accepted_as_an_evidence_id(self):
        with pytest.raises(GroundedOutputError) as caught:
            validate(draft([("청구항 1은 센서를 포함한다.", ["1"])]))
        assert caught.value.violation is GroundedViolation.MALFORMED_EVIDENCE_ID

    def test_an_id_from_another_request_is_rejected(self):
        """A three-entry catalog does not resolve the fifth id of another one."""
        with pytest.raises(GroundedOutputError) as caught:
            validate(draft([(STATEMENT, ["EV-005"])]), catalog=make_catalog(3))
        assert caught.value.violation is GroundedViolation.UNKNOWN_EVIDENCE_ID

    def test_one_bad_id_invalidates_the_whole_answer(self):
        """No partial success. Returning only the statements that happened to
        validate would answer the question from a subset the model did not pick.
        """
        with pytest.raises(GroundedOutputError):
            validate(
                draft(
                    [
                        ("수집부가 있다.", ["EV-001"]),
                        ("침해한다.", ["EV-777"]),
                    ]
                )
            )

    def test_duplicate_ids_are_collapsed_in_first_mentioned_order(self):
        answer = validate(draft([(STATEMENT, ["EV-002", "EV-001", "EV-002"])]))
        assert answer.statements[0].evidence_ids == ("EV-002", "EV-001")

    def test_too_many_ids_for_one_statement_is_rejected(self):
        limits = OutputLimits(
            max_statements=8, max_statement_characters=600, max_evidence_ids_per_statement=2
        )
        with pytest.raises(GroundedOutputError) as caught:
            validate(draft([(STATEMENT, ["EV-001", "EV-002", "EV-003"])]), limits=limits)
        assert caught.value.violation is GroundedViolation.TOO_MANY_EVIDENCE_IDS


class TestInsufficiencyInvariants:
    def test_sufficient_evidence_with_no_statements_is_rejected(self):
        with pytest.raises(GroundedOutputError) as caught:
            validate(draft([]))
        assert caught.value.violation is GroundedViolation.NO_SUPPORTED_STATEMENTS

    def test_a_flag_without_a_reason_is_rejected(self):
        with pytest.raises(GroundedOutputError) as caught:
            validate(draft([], insufficient_evidence=True))
        assert caught.value.violation is GroundedViolation.CONTRADICTORY_INSUFFICIENCY

    def test_a_reason_without_the_flag_is_rejected(self):
        with pytest.raises(GroundedOutputError) as caught:
            validate(
                draft(
                    [(STATEMENT, ["EV-001"])],
                    insufficient_evidence=False,
                    insufficient_reason="conflicting_evidence",
                )
            )
        assert caught.value.violation is GroundedViolation.CONTRADICTORY_INSUFFICIENCY


class TestOutputLimits:
    def test_the_configured_statement_cap_is_enforced_after_generation(self):
        """Lower than the schema's cap, because a deployment may lower it.

        Constrained decoding enforces structure, not values: the schema asks for
        at most eight statements and does not guarantee it.
        """
        limits = OutputLimits(
            max_statements=2, max_statement_characters=600, max_evidence_ids_per_statement=4
        )
        with pytest.raises(GroundedOutputError) as caught:
            validate(draft([(f"문장 {n}입니다.", ["EV-001"]) for n in range(3)]), limits=limits)
        assert caught.value.violation is GroundedViolation.TOO_MANY_STATEMENTS

    def test_the_configured_statement_length_is_enforced_after_generation(self):
        limits = OutputLimits(
            max_statements=8, max_statement_characters=20, max_evidence_ids_per_statement=4
        )
        with pytest.raises(GroundedOutputError) as caught:
            validate(draft([(CLAIM_ONE, ["EV-001"])]), limits=limits)
        assert caught.value.violation is GroundedViolation.STATEMENT_TOO_LONG


class TestFillerPolicy:
    @pytest.mark.parametrize(
        "text",
        [
            "Based on the provided evidence,",
            "제공된 증거에 따르면",
            "This answer is not legal advice.",
            "본 답변은 법률 자문이 아닙니다.",
            "I am an AI assistant",
            "N/A",
            "-",
            "...",
        ],
    )
    def test_statements_carrying_no_assertion_are_dropped(self, text: str):
        answer = validate(
            draft([(text, ["EV-001"]), ("통신부는 무선 모듈을 포함한다.", ["EV-002"])])
        )
        assert len(answer.statements) == 1
        assert answer.statements[0].text == "통신부는 무선 모듈을 포함한다."
        assert answer.dropped_filler_count == 1

    def test_a_real_statement_that_merely_begins_with_a_preamble_is_kept(self):
        """The filler pattern is anchored to the whole string for this reason.

        Dropping a genuine statement is a far worse failure than rendering an
        empty-sounding one, so the policy errs towards keeping.
        """
        answer = validate(
            draft([("제공된 증거에 따르면 통신부는 무선 근거리 통신 모듈을 포함한다.", ["EV-001"])])
        )
        assert len(answer.statements) == 1
        assert answer.dropped_filler_count == 0

    def test_dropping_every_statement_of_a_sufficient_answer_is_rejected(self):
        with pytest.raises(GroundedOutputError) as caught:
            validate(draft([("N/A", ["EV-001"]), ("-", ["EV-002"])]))
        assert caught.value.violation is GroundedViolation.NO_SUPPORTED_STATEMENTS

    def test_dropped_filler_does_not_pull_its_evidence_into_the_answer(self):
        answer = validate(draft([("N/A", ["EV-003"]), ("수집부가 있다.", ["EV-001"])]))
        assert [entry.evidence_id for entry in answer.cited] == ["EV-001"]


class TestErrorSafety:
    def test_feedback_never_repeats_the_rejected_content(self):
        """Repair feedback is server-owned text about the rule, not the output.

        Echoing a rejected statement back would put generated text into a prompt
        - and into whatever surrounds that prompt - for no benefit.
        """
        secret = "이 문장은 절대 반복되어서는 안 된다"
        with pytest.raises(GroundedOutputError) as caught:
            validate(draft([(secret, ["EV-999"])]))
        assert secret not in caught.value.feedback
        assert secret not in caught.value.message
        assert "EV-999" not in caught.value.feedback

    def test_every_violation_is_repairable(self):
        with pytest.raises(GroundedOutputError) as caught:
            validate(draft([(STATEMENT, ["EV-999"])]))
        assert caught.value.is_repairable


def test_a_catalog_entry_keeps_its_provenance_through_validation():
    catalog = make_catalog(1)
    answer = validate(draft([("수집부가 있다.", ["EV-001"])]), catalog=catalog)
    entry = answer.cited[0]
    assert entry.candidate.spans == catalog.entries[0].candidate.spans
    assert entry.candidate.text == CLAIM_ONE


def test_validation_reads_provenance_only_from_the_catalog():
    """The model's output contributes nothing but the identifier.

    Built here by pairing a draft that mentions EV-001 with a catalog whose
    EV-001 points at a different document: the answer follows the catalog.
    """
    from claimtrace_api.grounding.evidence import build_catalog

    catalog = build_catalog(
        (make_candidate(document_id=DOCUMENT_B, claim_number=99, pages=((5, 10, 60),)),),
        retrieved_candidate_count=1,
    )
    answer = validate(draft([(STATEMENT, ["EV-001"])]), catalog=catalog)
    entry = answer.cited[0]
    assert entry.candidate.document_id == DOCUMENT_B
    assert entry.candidate.claim_number == 99
    assert entry.candidate.spans[0].page_number == 5
