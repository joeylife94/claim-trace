"""The output contract the model is held to.

Most of these assert refusals. The schema's job is to make an ungrounded answer
inexpressible, so the interesting cases are the payloads it will not accept.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from claimtrace_api.grounding.draft import (
    MAX_EVIDENCE_IDS_PER_STATEMENT,
    MAX_STATEMENT_CHARACTERS,
    MAX_STATEMENTS,
    GroundedAnswerDraft,
    InsufficientReason,
)
from claimtrace_api.llm.json_output import json_schema_for, parse_structured_output
from tests.grounded_fixtures import draft_json


def parse(payload: str) -> GroundedAnswerDraft:
    """Parse through the same pipeline a provider uses."""
    return parse_structured_output(payload, GroundedAnswerDraft)


class TestAcceptedShapes:
    def test_a_supported_statement_is_accepted(self):
        draft = parse(draft_json([("통신부는 무선 근거리 통신 모듈을 포함한다.", ("EV-001",))]))
        assert draft.insufficient_evidence is False
        assert draft.insufficient_reason is None
        assert len(draft.supported_statements) == 1
        assert draft.supported_statements[0].evidence_ids == ["EV-001"]

    def test_several_statements_citing_several_pieces_are_accepted(self):
        draft = parse(
            draft_json(
                [
                    ("수집부는 복수의 센서로부터 측정값을 수집한다.", ("EV-001",)),
                    ("통신부는 무선 근거리 통신 모듈을 포함한다.", ("EV-001", "EV-002")),
                ]
            )
        )
        assert len(draft.supported_statements) == 2
        assert draft.supported_statements[1].evidence_ids == ["EV-001", "EV-002"]

    def test_insufficient_evidence_with_no_statements_is_a_valid_shape(self):
        draft = parse(
            draft_json(
                [], insufficient_evidence=True, insufficient_reason="evidence_not_specific_enough"
            )
        )
        assert draft.insufficient_evidence is True
        assert draft.insufficient_reason is InsufficientReason.EVIDENCE_NOT_SPECIFIC_ENOUGH
        assert draft.supported_statements == []

    def test_every_documented_reason_is_accepted(self):
        for reason in InsufficientReason:
            draft = parse(
                draft_json([], insufficient_evidence=True, insufficient_reason=reason.value)
            )
            assert draft.insufficient_reason is reason


class TestRejectedShapes:
    def test_an_empty_statement_is_rejected(self):
        with pytest.raises(ValidationError):
            GroundedAnswerDraft.model_validate(
                {
                    "supported_statements": [{"text": "", "evidence_ids": ["EV-001"]}],
                    "insufficient_evidence": False,
                    "insufficient_reason": None,
                }
            )

    def test_a_whitespace_only_statement_is_rejected(self):
        """``min_length`` alone would pass this; a statement of spaces says nothing."""
        with pytest.raises(ValidationError):
            GroundedAnswerDraft.model_validate(
                {
                    "supported_statements": [{"text": "   \n\t ", "evidence_ids": ["EV-001"]}],
                    "insufficient_evidence": False,
                    "insufficient_reason": None,
                }
            )

    def test_a_statement_with_no_evidence_ids_is_rejected(self):
        """The rule the whole phase rests on, enforced by the type itself."""
        with pytest.raises(ValidationError):
            GroundedAnswerDraft.model_validate(
                {
                    "supported_statements": [{"text": "온도 센서를 포함한다.", "evidence_ids": []}],
                    "insufficient_evidence": False,
                    "insufficient_reason": None,
                }
            )

    def test_too_many_statements_are_rejected(self):
        with pytest.raises(ValidationError):
            GroundedAnswerDraft.model_validate(
                {
                    "supported_statements": [
                        {"text": f"문장 {n}", "evidence_ids": ["EV-001"]}
                        for n in range(MAX_STATEMENTS + 1)
                    ],
                    "insufficient_evidence": False,
                    "insufficient_reason": None,
                }
            )

    def test_too_many_evidence_ids_for_one_statement_are_rejected(self):
        with pytest.raises(ValidationError):
            GroundedAnswerDraft.model_validate(
                {
                    "supported_statements": [
                        {
                            "text": "모든 청구항에 해당한다.",
                            "evidence_ids": [
                                f"EV-{n:03d}" for n in range(MAX_EVIDENCE_IDS_PER_STATEMENT + 1)
                            ],
                        }
                    ],
                    "insufficient_evidence": False,
                    "insufficient_reason": None,
                }
            )

    def test_an_over_long_statement_is_rejected(self):
        with pytest.raises(ValidationError):
            GroundedAnswerDraft.model_validate(
                {
                    "supported_statements": [
                        {"text": "가" * (MAX_STATEMENT_CHARACTERS + 1), "evidence_ids": ["EV-001"]}
                    ],
                    "insufficient_evidence": False,
                    "insufficient_reason": None,
                }
            )

    def test_an_unknown_insufficient_reason_is_rejected(self):
        with pytest.raises(ValidationError):
            GroundedAnswerDraft.model_validate(
                {
                    "supported_statements": [],
                    "insufficient_evidence": True,
                    "insufficient_reason": "the model felt unsure",
                }
            )

    @pytest.mark.parametrize(
        "field",
        [
            "answer",
            "summary",
            "conclusion",
            "page_number",
            "start_char",
            "document_id",
            "claim_id",
            "quote",
            "source",
        ],
    )
    def test_unknown_fields_are_rejected(self, field: str):
        """Including every field a model might use to smuggle in a locator.

        ``extra="forbid"`` is what makes "the model cannot produce a page
        number" true by construction rather than by convention: there is no key
        it can put one under.
        """
        with pytest.raises(ValidationError):
            GroundedAnswerDraft.model_validate(
                {
                    "supported_statements": [
                        {"text": "온도 센서를 포함한다.", "evidence_ids": ["EV-001"]}
                    ],
                    "insufficient_evidence": False,
                    "insufficient_reason": None,
                    field: "4",
                }
            )

    def test_an_unknown_field_on_a_statement_is_rejected(self):
        with pytest.raises(ValidationError):
            GroundedAnswerDraft.model_validate(
                {
                    "supported_statements": [
                        {
                            "text": "온도 센서를 포함한다.",
                            "evidence_ids": ["EV-001"],
                            "page_number": 4,
                        }
                    ],
                    "insufficient_evidence": False,
                    "insufficient_reason": None,
                }
            )


class TestGeneratedSchema:
    def test_the_schema_forbids_additional_properties_at_both_levels(self):
        schema = json_schema_for(GroundedAnswerDraft)
        assert schema["additionalProperties"] is False
        statement = schema["$defs"]["GroundedStatementDraft"]
        assert statement["additionalProperties"] is False

    def test_the_schema_has_no_field_that_could_carry_a_locator(self):
        """A structural check on the contract, not on any one payload."""
        rendered = json.dumps(json_schema_for(GroundedAnswerDraft))
        for forbidden in ("page_number", "start_char", "end_char", "document_id", "claim_id"):
            assert forbidden not in rendered

    def test_the_evidence_id_field_declares_an_example(self):
        """Which is what lets the fake provider synthesise a valid draft.

        Without it, the offline default (``LLM_PROVIDER=fake``) could not answer
        a grounded request at all, and the whole endpoint would need a model
        server to be exercised even once.
        """
        schema = json_schema_for(GroundedAnswerDraft)
        item = schema["$defs"]["GroundedStatementDraft"]["properties"]["evidence_ids"]["items"]
        assert item["examples"] == ["EV-001"]

    def test_all_three_fields_are_required(self):
        """No optional fields, so a constrained decoder cannot omit one.

        An absent ``insufficient_evidence`` would be an answer that does not say
        whether it is grounded; an absent ``insufficient_reason`` would make
        "not applicable" and "forgot to say" the same payload.
        """
        schema = json_schema_for(GroundedAnswerDraft)
        assert set(schema["required"]) == {
            "supported_statements",
            "insufficient_evidence",
            "insufficient_reason",
        }

    @pytest.mark.parametrize(
        "missing", ["supported_statements", "insufficient_evidence", "insufficient_reason"]
    )
    def test_omitting_a_required_field_is_rejected(self, missing: str):
        payload: dict[str, object] = {
            "supported_statements": [{"text": "온도 센서를 포함한다.", "evidence_ids": ["EV-001"]}],
            "insufficient_evidence": False,
            "insufficient_reason": None,
        }
        del payload[missing]
        with pytest.raises(ValidationError):
            GroundedAnswerDraft.model_validate(payload)

    def test_the_insufficient_reason_enum_is_closed(self):
        schema = json_schema_for(GroundedAnswerDraft)
        assert set(schema["$defs"]["InsufficientReason"]["enum"]) == {
            reason.value for reason in InsufficientReason
        }
