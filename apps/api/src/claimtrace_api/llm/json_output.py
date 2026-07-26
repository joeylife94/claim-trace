"""Strict extraction and validation of JSON produced by a language model.

The policy here is deliberately unforgiving, and the reason is worth stating
plainly: a model that wraps its answer in an apology, emits two objects, or stops
half way through has not answered the question, and a parser that digs the
"probably intended" object out of that text turns a visible failure into an
invisible one. Everything this module rejects, it rejects loudly.

What is accepted:

* exactly one complete JSON value, with only whitespace around it;
* an object when the schema describes an object, an array when it describes one;
* optionally, that value wrapped in a single Markdown code fence - and only in
  the narrow, fully anchored form described at :func:`strip_code_fence`.

What is rejected, each with its own message:

* prose before or after the JSON;
* a second JSON value following the first;
* truncated JSON - reported distinctly, because it usually means the output
  token limit was hit rather than that the model misbehaved;
* comments, trailing commas, and every other JSON5-ism;
* values that parse but do not satisfy the schema;
* unknown fields, unless the schema itself opts into permitting them.

Notably absent is any search for the first ``{`` in a blob of prose. That
technique appears to work right up until a model writes ``{`` in a sentence.
"""

from __future__ import annotations

import json
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, RootModel, ValidationError

from claimtrace_api.llm.errors import LLMMalformedJSONError, LLMStructuredValidationError

#: Ordered longest-first so ```` ```json ```` is matched before ```` ``` ````.
_FENCE_OPENERS: Final = ("```json", "```JSON", "```")
_FENCE: Final = "```"

#: Rebuilding a strict subclass on every call would recompile a Pydantic core
#: schema per generation. Keyed by the class object itself.
_STRICT_MODELS: dict[type[BaseModel], type[BaseModel]] = {}


def strip_code_fence(text: str) -> str:
    """Remove one Markdown code fence wrapping the entire text.

    Narrow on purpose. The fence is removed only when, after trimming
    surrounding whitespace, the text *begins* with an opening fence and *ends*
    with a closing one - the exact shape a model produces when it has been told
    to answer in JSON and formats the whole answer as a code block.

    A fence in the middle of prose, an unclosed fence, or a second fence later in
    the text is left alone, so the JSON parser then rejects the text as it
    should. Returns the input unchanged when no fence wraps it.
    """
    stripped = text.strip()

    opener = next((o for o in _FENCE_OPENERS if stripped.startswith(o)), None)
    if opener is None:
        return text

    body = stripped[len(opener) :]
    if not body.endswith(_FENCE):
        # An unterminated fence. Left as-is so the failure is reported as
        # malformed or truncated JSON rather than silently repaired.
        return text

    body = body[: -len(_FENCE)]

    # A third fence means this is not one block wrapping one value; refuse to
    # guess which of them was meant.
    if _FENCE in body:
        return text

    return body.strip()


def extract_json_value(text: str, *, expect_array: bool = False) -> Any:
    """Parse exactly one JSON value out of ``text``.

    Uses :meth:`json.JSONDecoder.raw_decode`, which parses one value from the
    start and reports where it stopped. Anything but whitespace after that point
    is an error - which is what makes "one object followed by an explanation"
    fail rather than quietly succeed.

    Args:
        text: the raw model output.
        expect_array: whether the schema describes an array at the top level.

    Raises:
        LLMMalformedJSONError: no complete JSON value, more than one, trailing
            content, or a top-level type the schema cannot accept.
    """
    candidate = strip_code_fence(text).strip()

    if not candidate:
        raise LLMMalformedJSONError("The model returned an empty response.")

    opening = "[" if expect_array else "{"
    if not candidate.startswith(opening):
        # Checked before parsing so the message names the real problem: a reply
        # that opens with prose is a different fault from one that opens with a
        # valid JSON value of the wrong type.
        kind = "array" if expect_array else "object"
        raise LLMMalformedJSONError(
            f"The model did not return a JSON {kind}. Expected the response to "
            f"begin with '{opening}'."
        )

    decoder = json.JSONDecoder()
    try:
        value, end = decoder.raw_decode(candidate)
    except json.JSONDecodeError as exc:
        # Truncation is worth distinguishing from malformedness: it usually means
        # the output token limit was hit, which is fixed by raising the limit
        # rather than by reprompting.
        #
        # Two signals, because one is not enough. A failure at the very end of
        # the input is a value that stopped mid-way. An unterminated string is
        # also truncation, but its reported position is where the string *opened*
        # - which can be far from the end - so the position check alone misses
        # the single most common way a JSON reply gets cut off.
        if exc.msg.startswith("Unterminated") or exc.pos >= len(candidate) - 1:
            raise LLMMalformedJSONError(
                "The model's JSON response is incomplete. It was most likely cut "
                "off by the output token limit."
            ) from exc
        raise LLMMalformedJSONError(
            f"The model's response is not valid JSON (at character {exc.pos})."
        ) from exc

    remainder = candidate[end:].strip()
    if remainder:
        try:
            decoder.raw_decode(remainder)
        except json.JSONDecodeError:
            raise LLMMalformedJSONError(
                "The model returned JSON followed by additional text."
            ) from None
        raise LLMMalformedJSONError(
            "The model returned more than one JSON value; exactly one was expected."
        )

    return value


def strict_model[SchemaT: BaseModel](output_model: type[SchemaT]) -> type[SchemaT]:
    """Return ``output_model`` with unknown fields forbidden.

    Pydantic ignores unknown fields by default, which for a *generated* payload
    is the wrong default: a model that invents a field has misunderstood the
    schema, and dropping the evidence hides that. A schema that genuinely wants
    to accept extras says so with ``model_config = ConfigDict(extra="allow")``,
    and that declaration is respected here - which is what "unless the schema
    explicitly permits them" means in practice.

    Only the top level is tightened. A nested model keeps whatever policy it
    declares, so a schema needing depth-wise strictness sets ``extra="forbid"``
    on its own nested models.

    A :class:`~pydantic.RootModel` is returned untouched. It has no fields of its
    own for an extra key to appear alongside - Pydantic rejects ``extra`` on one
    outright - and the models nested inside it are tightened when they are
    validated in their own right.
    """
    if issubclass(output_model, RootModel) or output_model.model_config.get("extra") is not None:
        return output_model

    cached = _STRICT_MODELS.get(output_model)
    if cached is None:
        # A real subclass rather than a post-hoc attribute assignment: Pydantic
        # bakes ``extra`` into the compiled core schema when the class is
        # created, so a config set afterwards would generate the right JSON
        # Schema while still ignoring unknown fields at validation time.
        cached = type(
            output_model.__name__,
            (output_model,),
            {
                "__module__": output_model.__module__,
                "__doc__": output_model.__doc__,
                "model_config": ConfigDict(**{**output_model.model_config, "extra": "forbid"}),
            },
        )
        _STRICT_MODELS[output_model] = cached
    return cached  # type: ignore[return-value]


def json_schema_for(output_model: type[BaseModel]) -> dict[str, Any]:
    """The JSON Schema sent to a provider that can enforce one.

    Generated from the strict variant, so the schema carries
    ``additionalProperties: false``. That is what the schema-constrained modes of
    both target servers need in order to enforce the shape rather than merely
    suggest it.
    """
    return strict_model(output_model).model_json_schema()


def expects_array(output_model: type[BaseModel]) -> bool:
    """Whether this schema describes an array at the top level.

    True for a ``RootModel[list[...]]``; false for an ordinary model, which is
    always a JSON object.
    """
    return output_model.model_json_schema().get("type") == "array"


def validate_against[SchemaT: BaseModel](value: Any, output_model: type[SchemaT]) -> SchemaT:
    """Validate a parsed JSON value against ``output_model``.

    Raises:
        LLMStructuredValidationError: with a detail naming the offending fields
            and the expected types - derived from the schema, never from the
            generated values, so it is safe to show to an operator while the
            output that produced it is not.
    """
    model = strict_model(output_model)
    try:
        return model.model_validate(value)  # type: ignore[return-value]
    except ValidationError as exc:
        raise LLMStructuredValidationError(
            "The model's JSON response did not match the requested schema.",
            validation_detail=summarize_validation_error(exc),
        ) from exc


def summarize_validation_error(exc: ValidationError, *, limit: int = 5) -> str:
    """Describe a validation failure without quoting any generated value.

    Pydantic's own ``str(exc)`` embeds the offending input, which for a model
    response is exactly the content this project does not put into logs or error
    bodies. Only the field path and the rule that failed are kept.
    """
    parts: list[str] = []
    for error in exc.errors()[:limit]:
        location = ".".join(str(item) for item in error["loc"]) or "<root>"
        parts.append(f"{location}: {error['type']}")

    remaining = len(exc.errors()) - limit
    if remaining > 0:
        parts.append(f"and {remaining} more")
    return "; ".join(parts)


def parse_structured_output[SchemaT: BaseModel](text: str, output_model: type[SchemaT]) -> SchemaT:
    """Extract and validate one JSON value in a single step.

    The pipeline every provider funnels structured output through: strip an
    optional fence, take exactly one JSON value, then validate it strictly.
    """
    value = extract_json_value(text, expect_array=expects_array(output_model))
    return validate_against(value, output_model)


def schema_instruction(output_model: type[BaseModel]) -> str:
    """The prompt text used when a provider cannot enforce a schema itself.

    This is the weakest of the structured-output strategies and reads like it:
    it *asks*. Its value is that the reply is still validated on arrival with the
    same strictness as a natively constrained one, so a model that ignores the
    instruction produces a clean error instead of a plausible-looking wrong
    answer.
    """
    schema = json.dumps(json_schema_for(output_model), ensure_ascii=False, sort_keys=True)
    return (
        "Respond with a single JSON value that validates against this JSON Schema. "
        "Output only the JSON value: no explanation, no Markdown code fence, and "
        "no text before or after it.\n"
        f"JSON Schema: {schema}"
    )
