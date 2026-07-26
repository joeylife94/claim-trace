"""Turning a model's draft into something the server is willing to say.

Everything here runs *after* generation and trusts none of it. A draft that
satisfies the JSON schema has proved only that it has the right shape; this
module decides whether it has the right content, which for this phase means
exactly one thing: that every statement is attached to at least one evidence
identifier this server issued for this request.

What a passing result does and does not establish is worth being precise about,
because it is easy to oversell:

*It establishes* that each returned statement points at retrieved source text,
that the text is one this deployment stores, and that the reader can open the
exact page and character range it came from.

*It does not establish* that the cited claim entails the statement. No amount of
identifier checking can prove that a sentence is a faithful reading of the text
it cites; that is a semantic judgement, and this pipeline makes none. A grounded
answer is therefore a *checkable* answer, not a verified one - the citation is
what lets a reader do the checking, not a substitute for it.

The failure vocabulary is a closed enum rather than free text because two very
different consumers read it: the repair attempt, which needs to phrase safe
corrective feedback, and the error mapper, which needs to pick a status code.
Neither can be driven by a message string.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum

from claimtrace_api.grounding.draft import GroundedAnswerDraft, InsufficientReason
from claimtrace_api.grounding.evidence import (
    EvidenceCatalog,
    EvidenceEntry,
    is_well_formed_evidence_id,
)


class GroundedViolation(StrEnum):
    """Why a structurally valid draft is not an acceptable answer."""

    #: An id that is not in this request's catalog. Includes ids from another
    #: request, which are not special: they are simply not here.
    UNKNOWN_EVIDENCE_ID = "unknown_evidence_id"
    #: An id that is not even the right shape - a bare claim number, a lowercased
    #: id, one with surrounding whitespace.
    MALFORMED_EVIDENCE_ID = "malformed_evidence_id"
    #: A statement carrying no citations at all.
    UNCITED_STATEMENT = "uncited_statement"
    #: Text that is blank, or is only punctuation, once stripped.
    EMPTY_STATEMENT = "empty_statement"
    #: ``insufficient_evidence`` is false but nothing survived to answer with.
    NO_SUPPORTED_STATEMENTS = "no_supported_statements"
    #: The insufficiency flag and its reason disagree in one of two directions.
    CONTRADICTORY_INSUFFICIENCY = "contradictory_insufficiency"
    TOO_MANY_STATEMENTS = "too_many_statements"
    STATEMENT_TOO_LONG = "statement_too_long"
    TOO_MANY_EVIDENCE_IDS = "too_many_evidence_ids"


class GroundedOutputError(Exception):
    """A draft that cannot be returned, with feedback safe enough to send back.

    ``message`` is client-facing and says what went wrong in general terms.
    ``feedback`` is model-facing and is the only thing a repair attempt is
    allowed to add to the prompt. Neither ever contains a statement, a claim, an
    evidence body, or the offending value itself - see
    :func:`claimtrace_api.grounding.context.repair_instruction`.
    """

    def __init__(self, violation: GroundedViolation, *, message: str, feedback: str) -> None:
        super().__init__(message)
        self.violation = violation
        self.message = message
        self.feedback = feedback

    @property
    def is_repairable(self) -> bool:
        """Whether one more attempt could plausibly produce a valid answer.

        Every violation in this module is repairable: each one describes a model
        that produced a well-formed answer and broke a stated rule, which is the
        situation a corrective instruction addresses. Provider failures - a
        timeout, an unreachable server, a missing model - never reach here at
        all; they are raised as ``AppError`` before validation runs, and
        retrying those is the transport layer's business, not this one's.

        The property exists rather than being assumed so that adding a
        non-repairable violation later is a visible decision.
        """
        return True


@dataclass(frozen=True, slots=True)
class OutputLimits:
    """Per-deployment ceilings, re-checked after generation.

    These duplicate the bounds declared on the draft schema on purpose.
    Schema-constrained decoding enforces structure, not values: Ollama's grammar
    guarantees an array where an array is declared and does not enforce
    ``maxItems``. The schema asks; this checks.
    """

    max_statements: int
    max_statement_characters: int
    max_evidence_ids_per_statement: int


@dataclass(frozen=True, slots=True)
class ValidatedStatement:
    """One statement the server will repeat, and the evidence behind it."""

    text: str
    #: Deduplicated, in first-mentioned order, every one present in the catalog.
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ValidatedAnswer:
    """A draft that passed. Everything below is server-owned from here on."""

    statements: tuple[ValidatedStatement, ...]
    #: Only the entries actually cited by a surviving statement, in catalog
    #: order. Evidence that was retrieved, shown to the model, and not used is
    #: not part of the answer and is not returned as though it were.
    cited: tuple[EvidenceEntry, ...]
    insufficient_evidence: bool
    insufficient_reason: InsufficientReason | None
    #: Statements removed by the filler policy. Reported as a warning rather
    #: than hidden: the reader should know the model said something that was
    #: dropped, even though what it said carried no information.
    dropped_filler_count: int = 0


def validate_draft(
    draft: GroundedAnswerDraft,
    *,
    catalog: EvidenceCatalog,
    limits: OutputLimits,
) -> ValidatedAnswer:
    """Check a draft against the catalog and the configured ceilings.

    Raises:
        GroundedOutputError: the draft is not an acceptable answer. Never
            partially returned - a draft either passes whole or is rejected
            whole, because returning the statements that happened to validate
            would silently answer a question from a subset the model did not
            choose.
    """
    _check_insufficiency(draft)

    if len(draft.supported_statements) > limits.max_statements:
        raise GroundedOutputError(
            GroundedViolation.TOO_MANY_STATEMENTS,
            message="The model returned more statements than this deployment allows.",
            feedback=f"you returned more than {limits.max_statements} statements",
        )

    statements: list[ValidatedStatement] = []
    dropped = 0

    for statement in draft.supported_statements:
        text = statement.text.strip()
        if not text:
            raise GroundedOutputError(
                GroundedViolation.EMPTY_STATEMENT,
                message="The model returned an empty statement.",
                feedback="one of your statements was empty",
            )
        if len(text) > limits.max_statement_characters:
            raise GroundedOutputError(
                GroundedViolation.STATEMENT_TOO_LONG,
                message="The model returned a statement longer than this deployment allows.",
                feedback=(
                    f"one of your statements was longer than "
                    f"{limits.max_statement_characters} characters"
                ),
            )
        if _is_filler(text):
            dropped += 1
            continue

        statements.append(
            ValidatedStatement(
                text=text,
                evidence_ids=_validate_evidence_ids(statement.evidence_ids, catalog, limits),
            )
        )

    if not draft.insufficient_evidence and not statements:
        raise GroundedOutputError(
            GroundedViolation.NO_SUPPORTED_STATEMENTS,
            message="The model claimed the evidence was sufficient but cited nothing.",
            feedback=(
                "you reported sufficient evidence but returned no usable supported statement"
            ),
        )

    cited_ids = {evidence_id for statement in statements for evidence_id in statement.evidence_ids}
    return ValidatedAnswer(
        statements=tuple(statements),
        # Catalog order, not citation order: the evidence list is a stable
        # reference section, and its ordering should not shuffle because the
        # model happened to mention EV-003 in its first sentence.
        cited=tuple(entry for entry in catalog.entries if entry.evidence_id in cited_ids),
        insufficient_evidence=draft.insufficient_evidence,
        insufficient_reason=draft.insufficient_reason,
        dropped_filler_count=dropped,
    )


# -- internals --------------------------------------------------------------


def _check_insufficiency(draft: GroundedAnswerDraft) -> None:
    """Reject the two ways the insufficiency fields can contradict each other.

    Both directions matter. A reason without the flag would render a limitation
    notice on an answer that claims to be supported; the flag without a reason
    would tell a reader that the system declined without saying why, which is
    the least useful possible refusal.
    """
    if draft.insufficient_evidence and draft.insufficient_reason is None:
        raise GroundedOutputError(
            GroundedViolation.CONTRADICTORY_INSUFFICIENCY,
            message="The model reported insufficient evidence without a reason.",
            feedback="you set insufficient_evidence to true without giving insufficient_reason",
        )
    if not draft.insufficient_evidence and draft.insufficient_reason is not None:
        raise GroundedOutputError(
            GroundedViolation.CONTRADICTORY_INSUFFICIENCY,
            message="The model gave a reason for insufficient evidence it did not report.",
            feedback="you gave an insufficient_reason while insufficient_evidence was false",
        )


def _validate_evidence_ids(
    evidence_ids: list[str], catalog: EvidenceCatalog, limits: OutputLimits
) -> tuple[str, ...]:
    """Check, deduplicate, and order one statement's citations.

    Duplicates are collapsed rather than rejected, keeping first-mentioned
    order. A model citing the same claim twice for one sentence has expressed a
    true thing clumsily, not an invalid thing, and the deduplication is
    deterministic - so the same draft always produces the same citation list.
    Every other defect is fatal.
    """
    if not evidence_ids:
        raise GroundedOutputError(
            GroundedViolation.UNCITED_STATEMENT,
            message="The model returned a statement with no citation.",
            feedback="one of your statements cited no evidence",
        )
    if len(evidence_ids) > limits.max_evidence_ids_per_statement:
        raise GroundedOutputError(
            GroundedViolation.TOO_MANY_EVIDENCE_IDS,
            message="The model cited more evidence for one statement than is allowed.",
            feedback=(
                f"one statement cited more than {limits.max_evidence_ids_per_statement} "
                "pieces of evidence"
            ),
        )

    accepted: list[str] = []
    for evidence_id in evidence_ids:
        # Compared exactly as received. No strip(), no casefold(), no accepting
        # a bare number: each of those would let output the server never issued
        # become a citation, which is the one thing this phase exists to stop.
        if not is_well_formed_evidence_id(evidence_id):
            raise GroundedOutputError(
                GroundedViolation.MALFORMED_EVIDENCE_ID,
                message="The model returned a citation that is not an evidence id.",
                feedback="one of your citations was not an evidence id of the form EV-001",
            )
        if not catalog.contains(evidence_id):
            raise GroundedOutputError(
                GroundedViolation.UNKNOWN_EVIDENCE_ID,
                message="The model cited evidence that was not supplied to it.",
                feedback="you cited an evidence id that was not in the supplied evidence",
            )
        if evidence_id not in accepted:
            accepted.append(evidence_id)

    return tuple(accepted)


#: Statements that are entirely boilerplate. Anchored to the whole string, so a
#: real statement that merely *begins* with "Based on the evidence," is kept -
#: only a sentence that is nothing but the preamble is dropped.
#:
#: The list is short and stays short on purpose. Every entry is a phrase
#: observed to carry no information about the claim text; guessing at more would
#: risk deleting a genuine statement, which is a far worse failure than
#: rendering an empty-sounding one.
_FILLER_PHRASES = re.compile(
    r"\A(?:"
    r"(?:this|the)\s+(?:answer|response)\s+is\s+not\s+legal\s+advice"
    r"|i\s+am\s+an?\s+(?:ai|language\s+model)[^.]*"
    r"|based\s+on\s+the\s+(?:provided\s+|supplied\s+)?evidence"
    r"|(?:본|이)\s*(?:답변|응답)은\s*법률\s*자문이\s*아닙니다"
    r"|제공된\s*증거에\s*따르면"
    r"|위\s*증거에\s*따르면"
    r")\s*[.,:;!?]*\s*\Z",
    re.IGNORECASE,
)

#: Below this many letter-or-digit characters, a statement cannot be saying
#: anything about a claim. Catches "N/A", "-", "없음.", and the punctuation-only
#: fragments a small model emits when it has nothing to add.
_MIN_CONTENT_CHARACTERS = 4


def _is_filler(text: str) -> bool:
    """Whether a statement carries no assertion about the evidence.

    Filler is *dropped*, not rejected. A model that appends a disclaimer to an
    otherwise good answer has not produced an invalid answer, and failing the
    whole generation - or worse, spending the one repair attempt - over a
    sentence that says nothing would trade a good answer for no answer. Dropping
    is counted and surfaced as a warning so the removal is visible.
    """
    if _content_length(text) < _MIN_CONTENT_CHARACTERS:
        return True
    return _FILLER_PHRASES.match(text) is not None


def _content_length(text: str) -> int:
    """How many letters or digits a statement contains.

    Uses Unicode categories rather than ``str.isalnum`` per character for the
    same reason the rest of this codebase normalises with NFKC: the text is
    Korean as often as it is English, and "is this punctuation?" has to be
    answered the same way for both.
    """
    return sum(1 for character in text if unicodedata.category(character)[0] in {"L", "N"})
