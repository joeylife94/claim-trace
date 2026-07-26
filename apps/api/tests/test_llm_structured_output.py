"""JSON extraction and schema validation.

This is the module where being permissive would be actively harmful, so the
tests are written as a specification of what is *refused*. Every case that a
"find the first {...}" extractor would happily accept appears here as a
rejection.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ConfigDict, Field, RootModel

from claimtrace_api.llm.errors import LLMMalformedJSONError, LLMStructuredValidationError
from claimtrace_api.llm.json_output import (
    expects_array,
    extract_json_value,
    json_schema_for,
    parse_structured_output,
    schema_instruction,
    strict_model,
    strip_code_fence,
    validate_against,
)


class Summary(BaseModel):
    title: str
    keywords: list[str]
    confidence: float = Field(ge=0.0, le=1.0)


class Permissive(BaseModel):
    """A schema that explicitly opts into extra fields."""

    model_config = ConfigDict(extra="allow")

    title: str


class SummaryList(RootModel[list[Summary]]):
    pass


VALID = '{"title": "제목", "keywords": ["센서", "통신"], "confidence": 0.8}'


# --------------------------------------------------------------------------
# Accepted
# --------------------------------------------------------------------------


def test_valid_json_object_is_parsed_and_validated():
    result = parse_structured_output(VALID, Summary)

    assert result.title == "제목"
    assert result.keywords == ["센서", "통신"]
    assert result.confidence == 0.8


def test_surrounding_whitespace_is_accepted():
    assert parse_structured_output(f"\n\n  {VALID}  \n", Summary).title == "제목"


def test_valid_json_array_is_accepted_when_the_schema_expects_one():
    payload = f"[{VALID}]"
    result = parse_structured_output(payload, SummaryList)

    assert len(result.root) == 1
    assert result.root[0].title == "제목"


def test_array_schema_is_detected_from_the_model():
    assert expects_array(SummaryList) is True
    assert expects_array(Summary) is False


def test_an_array_is_rejected_when_the_schema_expects_an_object():
    with pytest.raises(LLMMalformedJSONError, match="JSON object"):
        parse_structured_output(f"[{VALID}]", Summary)


def test_an_object_is_rejected_when_the_schema_expects_an_array():
    with pytest.raises(LLMMalformedJSONError, match="JSON array"):
        parse_structured_output(VALID, SummaryList)


# --------------------------------------------------------------------------
# Markdown fence policy
# --------------------------------------------------------------------------


@pytest.mark.parametrize("opener", ["```json", "```JSON", "```"])
def test_a_single_fence_wrapping_the_whole_value_is_removed(opener: str):
    assert parse_structured_output(f"{opener}\n{VALID}\n```", Summary).title == "제목"


def test_an_unterminated_fence_is_not_repaired():
    """Left alone deliberately, so the JSON parser reports the real fault."""
    with pytest.raises(LLMMalformedJSONError):
        parse_structured_output(f"```json\n{VALID}", Summary)


def test_a_fence_in_the_middle_of_prose_is_not_stripped():
    text = f"Here is the answer:\n```json\n{VALID}\n```\nHope that helps."
    with pytest.raises(LLMMalformedJSONError):
        parse_structured_output(text, Summary)


def test_two_fenced_blocks_are_refused_rather_than_guessed_between():
    text = f"```json\n{VALID}\n```\n```json\n{VALID}\n```"
    with pytest.raises(LLMMalformedJSONError):
        parse_structured_output(text, Summary)


def test_strip_code_fence_returns_unfenced_text_unchanged():
    assert strip_code_fence(VALID) == VALID


# --------------------------------------------------------------------------
# Refused
# --------------------------------------------------------------------------


def test_prose_before_json_is_refused():
    with pytest.raises(LLMMalformedJSONError, match="did not return a JSON object"):
        parse_structured_output(f"Certainly! Here you go: {VALID}", Summary)


def test_prose_after_json_is_refused():
    with pytest.raises(LLMMalformedJSONError, match="followed by additional text"):
        parse_structured_output(f"{VALID}\n\nLet me know if you need more.", Summary)


def test_multiple_json_values_are_refused():
    with pytest.raises(LLMMalformedJSONError, match="more than one JSON value"):
        parse_structured_output(f"{VALID}{VALID}", Summary)


def test_truncated_json_is_reported_as_incomplete():
    """Distinguished from malformed: the usual cause is the output token limit."""
    with pytest.raises(LLMMalformedJSONError, match="incomplete"):
        parse_structured_output('{"title": "제목", "keywords": ["센', Summary)


def test_empty_output_is_refused():
    with pytest.raises(LLMMalformedJSONError, match="empty response"):
        parse_structured_output("   \n  ", Summary)


def test_comments_are_refused():
    payload = '{\n  // the title\n  "title": "제목", "keywords": [], "confidence": 0.5\n}'
    with pytest.raises(LLMMalformedJSONError):
        parse_structured_output(payload, Summary)


def test_trailing_comma_is_refused():
    payload = '{"title": "제목", "keywords": [], "confidence": 0.5,}'
    with pytest.raises(LLMMalformedJSONError):
        parse_structured_output(payload, Summary)


def test_a_brace_inside_prose_is_not_mistaken_for_the_answer():
    """The specific failure a permissive first-{...} extractor would produce."""
    text = 'I would use a JSON object like {"title": "x"} for this. ' + VALID
    with pytest.raises(LLMMalformedJSONError):
        parse_structured_output(text, Summary)


# --------------------------------------------------------------------------
# Schema validation
# --------------------------------------------------------------------------


def test_wrong_type_fails_validation():
    payload = '{"title": "제목", "keywords": "센서", "confidence": 0.5}'
    with pytest.raises(LLMStructuredValidationError):
        parse_structured_output(payload, Summary)


def test_missing_required_field_fails_validation():
    with pytest.raises(LLMStructuredValidationError):
        parse_structured_output('{"title": "제목"}', Summary)


def test_out_of_range_value_fails_validation():
    payload = '{"title": "제목", "keywords": [], "confidence": 1.7}'
    with pytest.raises(LLMStructuredValidationError):
        parse_structured_output(payload, Summary)


def test_unknown_fields_are_refused_by_default():
    """Not silently dropped: an invented field means the schema was misunderstood."""
    payload = '{"title": "제목", "keywords": [], "confidence": 0.5, "verdict": "invalid"}'
    with pytest.raises(LLMStructuredValidationError):
        parse_structured_output(payload, Summary)


def test_unknown_fields_are_kept_when_the_schema_permits_them():
    result = parse_structured_output('{"title": "제목", "extra": 1}', Permissive)

    assert result.title == "제목"
    assert result.model_extra == {"extra": 1}


def test_validation_detail_names_fields_without_quoting_generated_values():
    payload = '{"title": "기밀 제목", "keywords": [], "confidence": 9.9}'

    with pytest.raises(LLMStructuredValidationError) as exc_info:
        parse_structured_output(payload, Summary)

    detail = exc_info.value.validation_detail
    assert "confidence" in detail
    # The offending value never appears - Pydantic's own str() would include it.
    assert "9.9" not in detail
    assert "기밀" not in detail
    assert "기밀" not in exc_info.value.message


def test_validation_detail_is_bounded():
    class Wide(BaseModel):
        a: int
        b: int
        c: int
        d: int
        e: int
        f: int
        g: int

    with pytest.raises(LLMStructuredValidationError) as exc_info:
        validate_against({}, Wide)

    assert "and 2 more" in exc_info.value.validation_detail


# --------------------------------------------------------------------------
# Schema generation
# --------------------------------------------------------------------------


def test_generated_schema_forbids_additional_properties():
    """What lets a server actually enforce the shape rather than merely suggest it."""
    assert json_schema_for(Summary)["additionalProperties"] is False


def test_a_permissive_schema_keeps_its_own_policy():
    assert json_schema_for(Permissive).get("additionalProperties") is not False


def test_strict_model_is_cached():
    assert strict_model(Summary) is strict_model(Summary)


def test_strict_model_returns_an_explicitly_configured_model_unchanged():
    assert strict_model(Permissive) is Permissive


def test_prompt_instruction_embeds_the_schema_and_forbids_prose():
    instruction = schema_instruction(Summary)

    assert "JSON Schema" in instruction
    assert "confidence" in instruction
    assert "no text before or after" in instruction


def test_extract_json_value_returns_plain_python():
    value = extract_json_value(VALID)
    assert value == {"title": "제목", "keywords": ["센서", "통신"], "confidence": 0.8}
