"""The output contract the model must satisfy.

This schema is the single place a model's answer enters the system, and its
shape is the point. There is no free-form ``answer`` field, no ``summary``, no
``conclusion``, and no ``note``: every sentence the server is willing to repeat
has to arrive attached to at least one evidence identifier. A model that wants
to say something it cannot cite has exactly one way to express that, which is
``insufficient_evidence``.

Removing the uncited free-text field is not a stylistic choice. If one existed,
it would be the field that got rendered - it reads best, it always has content,
and it is never blocked by a citation check - and the grounding guarantee would
quietly become decorative. The final answer text is assembled by the server from
validated statements instead; see
:mod:`claimtrace_api.grounding.validation`.

Two warnings about what a schema does and does not buy:

*Constrained decoding enforces structure, not values.* Ollama's grammar
guarantees a string where a string is declared; it does not enforce
``maxLength``, ``maxItems``, or ``pattern``. Phase 4A-1 observed exactly this
with a numeric range. Every bound declared here is therefore re-checked after
arrival by the validator, which is the real enforcement point. The declarations
remain because they cost nothing and do help a server that honours them.

*Field descriptions are prompt text.* Pydantic puts them in the JSON Schema, and
the schema is sent to the model. They are written for the model - short,
imperative, and free of internal reasoning. Anything a maintainer needs to know
belongs in a comment like this one, where it is not spending a small model's
context window.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

#: Absolute ceilings, independent of configuration. Declared as literals because
#: a Pydantic field constraint has to resolve at class-definition time. The
#: matching settings may lower them further; nothing may raise them.
MAX_STATEMENTS = 8
MAX_STATEMENT_CHARACTERS = 600
MAX_EVIDENCE_IDS_PER_STATEMENT = 4

#: An evidence id, as the model may write it.
#:
#: There is deliberately no ``pattern=`` constraint here, and the omission is a
#: policy decision rather than an oversight. The format *is* enforced strictly,
#: by :func:`~claimtrace_api.grounding.evidence.is_well_formed_evidence_id`
#: after the answer arrives - and enforcing it in the schema as well would make
#: a malformed id fail *inside* the provider, as a schema-validation error
#: indistinguishable from malformed JSON. That is a dead end: the generation is
#: over and nothing can be corrected. Letting a malformed id through the schema
#: and rejecting it in the validator turns it into what it actually is - a
#: well-formed answer that broke a rule - which one bounded repair attempt can
#: fix. Strictness is not reduced anywhere; it is moved to the layer that can
#: act on it.
#:
#: The ``examples`` entry is load-bearing rather than decorative. It shows the
#: model a concrete instance of the format, and it is what lets the fake
#: provider synthesise a schema-valid grounded draft: a declared example is by
#: construction a legal value, which a bare description is not enough to derive.
#: ``EV-001`` exists whenever a catalog is non-empty, and an empty catalog never
#: reaches a provider at all.
EvidenceIdField = Annotated[str, Field(json_schema_extra={"examples": ["EV-001"]})]


class InsufficientReason(StrEnum):
    """Why a question could not be answered from the supplied evidence.

    A closed set, because this value is rendered to a reader as the system's own
    explanation. A free-text reason would be uncited model prose reaching the UI
    through the one field that was not required to carry a citation.
    """

    #: Retrieval returned nothing, so there was nothing to ground an answer in.
    #: Normally set by the server without consulting the model at all.
    NO_RETRIEVED_EVIDENCE = "no_retrieved_evidence"
    #: Evidence was retrieved and is related, but does not state what was asked.
    EVIDENCE_NOT_SPECIFIC_ENOUGH = "evidence_not_specific_enough"
    #: The retrieved claims disagree, and picking a winner would be an
    #: unsupported judgement rather than a reading of the text.
    CONFLICTING_EVIDENCE = "conflicting_evidence"
    #: The question is about something the available documents do not cover.
    QUESTION_OUTSIDE_AVAILABLE_DOCUMENTS = "question_outside_available_documents"


class GroundedStatementDraft(BaseModel):
    """One factual statement and the evidence it came from."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(
        min_length=1,
        max_length=MAX_STATEMENT_CHARACTERS,
        description="One sentence stating only what the cited evidence says.",
    )
    evidence_ids: list[EvidenceIdField] = Field(
        min_length=1,
        max_length=MAX_EVIDENCE_IDS_PER_STATEMENT,
        description="Evidence IDs supporting this sentence, such as EV-001. Never invent one.",
    )

    @field_validator("text")
    @classmethod
    def _reject_blank(cls, value: str) -> str:
        """A whitespace-only statement satisfies ``min_length`` and says nothing."""
        if not value.strip():
            raise ValueError("statement text must not be blank")
        return value


class GroundedAnswerDraft(BaseModel):
    """The complete answer, as the model is allowed to express it."""

    model_config = ConfigDict(extra="forbid")

    # All three fields are required, and none carries a Python default. That is
    # a deliberate choice about how models behave rather than a modelling
    # preference.
    #
    # A field with a default is *optional* in the emitted JSON Schema, and an
    # optional field is one a constrained decoder is free to omit - so the
    # answer arrives missing the very flag that says whether it is grounded,
    # and "absent" has to be disambiguated from "null" downstream. Requiring all
    # three means the grammar always produces them, an explicit
    # ``"insufficient_reason": null`` is what a sufficient answer looks like,
    # and there is one representation of each state instead of two.
    #
    # It also has a concrete offline consequence: the fake provider synthesises
    # exactly the required fields, so this is what lets ``LLM_PROVIDER=fake``
    # answer a grounded request at all.
    supported_statements: list[GroundedStatementDraft] = Field(
        max_length=MAX_STATEMENTS,
        description="Statements answering the question, each citing evidence. May be empty.",
    )
    insufficient_evidence: bool = Field(
        description="True when the evidence does not answer the question.",
    )
    insufficient_reason: InsufficientReason | None = Field(
        description="Required when insufficient_evidence is true; otherwise null.",
    )

    # Note what is deliberately *not* enforced here: the coherence of
    # ``insufficient_evidence`` with ``insufficient_reason``, and with the
    # presence of statements. Those are checked in
    # :mod:`claimtrace_api.grounding.validation` instead.
    #
    # The reason is the repair policy. A model validator failing here surfaces
    # as a schema-validation error from inside the provider, which is a dead end
    # - the generation is already over and the failure looks identical to
    # malformed JSON. A contradiction between two flags, by contrast, is a
    # well-formed answer that broke a rule, which is precisely the case one
    # bounded corrective attempt can fix. Enforcing it at this layer would
    # convert a repairable violation into an unrepairable one.
