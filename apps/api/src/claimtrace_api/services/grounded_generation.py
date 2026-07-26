"""Evidence-grounded answering: the use case that joins retrieval to generation.

This is the collaborator Phase 4A-1 deliberately left room for. ``ClaimSearchService``
still knows nothing about a model, ``LLMGenerationService`` still knows nothing
about a claim, and the coupling between them lives here, in one object that can
be read top to bottom.

The order of operations is the design:

1. Validate the question and the filter. Nothing expensive runs for a request
   that was never going to be served.
2. Retrieve through the real Phase 3A path. There is no second retrieval
   implementation, no private query, and no score threshold invented for this
   endpoint - a grounded answer is built from exactly what a search would have
   returned.
3. Build the catalog and the prompt together, under one budget, so the evidence
   the model was shown and the evidence a citation can resolve to are the same
   set by construction.
4. Generate against a fixed schema, with at most one bounded corrective attempt.
5. Validate every identifier against the catalog. Nothing else in the model's
   output is trusted, because nothing else in it can be checked.
6. Resolve the surviving citations to canonical spans and read their quotes out
   of stored page text.
7. Compose the answer from validated statements, server-side.

Step 7 is the one that is easy to skip and expensive to skip. The model never
writes the answer text as a whole; it writes sentences that each had to earn a
citation, and the server concatenates the ones that did. There is no path by
which uncited prose reaches a reader.

What this service does *not* do: persist anything, modify a document, a parse
result, or an index run, retrieve outside ``ClaimSearchService``, or reach a
conclusion. It answers what the claim text says, and it says so with a link.
"""

from __future__ import annotations

import hashlib
import logging
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from claimtrace_api.core.config import Settings
from claimtrace_api.core.errors import AppError, ErrorCode
from claimtrace_api.grounding.context import (
    ContextBudget,
    ContextTooLargeError,
    EvidenceContext,
    build_evidence_context,
    repair_instruction,
)
from claimtrace_api.grounding.draft import GroundedAnswerDraft, InsufficientReason
from claimtrace_api.grounding.evidence import EvidenceCandidate, EvidenceEntry
from claimtrace_api.grounding.validation import (
    GroundedOutputError,
    GroundedViolation,
    OutputLimits,
    ValidatedAnswer,
    ValidatedStatement,
    validate_draft,
)
from claimtrace_api.indexing.profile import IndexProfile
from claimtrace_api.llm.models import GenerationResponse
from claimtrace_api.retrieval.base import RetrievalMode
from claimtrace_api.schemas.locators import SourceLocator
from claimtrace_api.services.claim_search import ClaimSearchService, SearchOutcome, SearchResult
from claimtrace_api.services.llm_generation import LLMGenerationService
from claimtrace_api.services.source_resolution import ResolvedSpan, SourceResolver

logger = logging.getLogger(__name__)

#: Server-owned limitation text, one per reason. Deterministic, never generated.
#:
#: These exist because "the evidence does not answer this" still has to be said
#: to a reader in words, and the model is the last thing that should be writing
#: them: prose explaining why a model could not support an answer is itself
#: unsupported prose. Selecting a fixed sentence with a closed enum keeps the
#: explanation inside the grounding guarantee instead of beside it.
INSUFFICIENT_MESSAGES: dict[InsufficientReason, str] = {
    InsufficientReason.NO_RETRIEVED_EVIDENCE: (
        "No indexed claim text was retrieved for this question, so there is nothing to "
        "ground an answer in."
    ),
    InsufficientReason.EVIDENCE_NOT_SPECIFIC_ENOUGH: (
        "The retrieved claims are related to this question but do not state what it asks, "
        "so no supported answer can be given from them."
    ),
    InsufficientReason.CONFLICTING_EVIDENCE: (
        "The retrieved claims do not agree on this point. Choosing between them would be a "
        "judgement rather than a reading of the text."
    ),
    InsufficientReason.QUESTION_OUTSIDE_AVAILABLE_DOCUMENTS: (
        "This question is about something the indexed documents do not cover."
    ),
}

NO_INDEX_WARNING = (
    "No claim index matching the active retrieval profile was found, so nothing was searched."
)
OMITTED_EVIDENCE_WARNING = (
    "Lower-ranked claims were left out of the evidence to stay within the context budget; "
    "they could not be cited."
)
FILLER_DROPPED_WARNING = (
    "One or more statements carrying no assertion about the evidence were removed."
)
REPAIR_WARNING = (
    "The first answer broke a grounding rule and was regenerated once with corrective instructions."
)
CITATION_SEMANTICS_NOTE = (
    "Each citation is verified to point at retrieved source text; that is not a proof that "
    "the cited text entails the statement."
)


@dataclass(frozen=True, slots=True)
class GroundedEvidence:
    """One cited catalog entry, with its spans resolved against stored text."""

    entry: EvidenceEntry
    spans: tuple[ResolvedSpan, ...]


@dataclass(frozen=True, slots=True)
class RetrievalContext:
    """What was searched, and how much of it survived into the prompt."""

    mode: RetrievalMode
    profile: IndexProfile
    searched_index_run_count: int
    retrieved_candidate_count: int
    included_evidence_count: int
    omitted_evidence_count: int


@dataclass(frozen=True, slots=True)
class GroundedAnswer:
    """The complete, server-owned result of one grounded question."""

    #: Composed by the server from validated statements. Never model prose that
    #: bypassed citation checking.
    answer: str
    statements: tuple[ValidatedStatement, ...]
    evidence: tuple[GroundedEvidence, ...]
    insufficient_evidence: bool
    insufficient_reason: InsufficientReason | None
    retrieval: RetrievalContext
    #: ``None`` when no provider was contacted, which happens when retrieval
    #: returned nothing. A zero-filled metadata block would report a generation
    #: that never took place.
    generation: GenerationResponse | None
    warnings: tuple[str, ...] = field(default_factory=tuple)


class GroundedGenerationService:
    """Answers one question from retrieved claims, or explains why it cannot."""

    def __init__(
        self,
        *,
        search: ClaimSearchService,
        llm: LLMGenerationService,
        session: AsyncSession,
        settings: Settings,
    ) -> None:
        self._search = search
        self._llm = llm
        self._resolver = SourceResolver(session=session)
        self._settings = settings

    async def answer(
        self,
        *,
        query: str,
        mode: RetrievalMode = RetrievalMode.HYBRID,
        document_ids: Sequence[uuid.UUID] | None = None,
        top_k: int,
    ) -> GroundedAnswer:
        """Answer ``query`` from indexed claim text.

        Raises:
            AppError: the request cannot be served, the provider failed, or the
                model produced output that cannot be grounded. Insufficient
                evidence is not among these - it is a successful answer.
        """
        started = time.perf_counter()
        settings = self._settings

        if not settings.grounded_generation_enabled:
            raise AppError(
                ErrorCode.GROUNDED_GENERATION_UNAVAILABLE,
                "Evidence-grounded answering is disabled for this deployment.",
            )

        question = query.strip()
        if not question:
            raise AppError(ErrorCode.LLM_INVALID_REQUEST, "The question may not be empty.")

        scope = _unique_document_ids(document_ids)

        outcome = await self._search.search(
            query=question,
            mode=mode,
            document_ids=scope or None,
            top_k=top_k,
            # Server-controlled. The caller chooses how many claims it wants to
            # see, never how wide the internal candidate sweep is: inflating
            # those is a cost decision, not a relevance one.
            dense_candidate_count=settings.dense_candidate_count,
            lexical_candidate_count=settings.lexical_candidate_count,
        )

        warnings: list[str] = []
        if outcome.searched_index_run_count == 0:
            warnings.append(NO_INDEX_WARNING)

        if not outcome.results:
            # No provider is contacted. Asking a model to answer from an empty
            # evidence list is asking it to answer from memory, which is the one
            # thing this endpoint must never do - and it would cost a CPU
            # inference to arrive at a conclusion the server already knows.
            answer = self._empty_answer(outcome, warnings=warnings)
            self._log(question, scope, answer, started, repair_attempts=0)
            return answer

        context = self._build_context(question, outcome.results)
        if context.catalog.omitted_candidate_count:
            warnings.append(OMITTED_EVIDENCE_WARNING)

        validated, generation, repair_attempts = await self._generate(context)

        if repair_attempts:
            warnings.append(REPAIR_WARNING)
        if validated.dropped_filler_count:
            warnings.append(FILLER_DROPPED_WARNING)
        warnings.extend(generation.warnings)
        warnings.append(CITATION_SEMANTICS_NOTE)

        evidence = await self._resolve_citations(validated)

        answer = GroundedAnswer(
            answer=_compose_answer(validated),
            statements=validated.statements,
            evidence=evidence,
            insufficient_evidence=validated.insufficient_evidence,
            insufficient_reason=validated.insufficient_reason,
            retrieval=_retrieval_context(outcome, context),
            generation=generation,
            warnings=tuple(warnings),
        )
        self._log(question, scope, answer, started, repair_attempts=repair_attempts)
        return answer

    # -- pipeline stages ----------------------------------------------------

    def _build_context(self, question: str, results: Sequence[SearchResult]) -> EvidenceContext:
        """Assemble the catalog and the prompt, mapping a budget failure to HTTP."""
        try:
            return build_evidence_context(
                question=question,
                candidates=[_to_candidate(result) for result in results],
                budget=ContextBudget(
                    max_evidence_candidates=self._settings.grounded_max_evidence_candidates,
                    max_evidence_characters=self._settings.grounded_max_evidence_characters,
                    max_question_characters=self._settings.grounded_max_question_characters,
                ),
            )
        except ContextTooLargeError as error:
            raise AppError(ErrorCode.GROUNDED_CONTEXT_TOO_LARGE, error.message) from error

    async def _generate(
        self, context: EvidenceContext
    ) -> tuple[ValidatedAnswer, GenerationResponse, int]:
        """Generate and validate, with at most the configured repair attempts.

        The evidence never changes between attempts. A repair reuses the same
        catalog and the same rendered blocks and adds only server-owned
        corrective text, so a second attempt cannot cite anything the first one
        could not, and retrieval is not run again.
        """
        limits = OutputLimits(
            max_statements=self._settings.grounded_max_statements,
            max_statement_characters=self._settings.grounded_max_statement_characters,
            max_evidence_ids_per_statement=(self._settings.grounded_max_evidence_ids_per_statement),
        )
        allowed_repairs = max(0, self._settings.grounded_repair_max_attempts)
        prompt = context.user_prompt

        for repair_attempt in range(allowed_repairs + 1):
            generation = await self._llm.generate_structured(
                prompt=prompt,
                output_model=GroundedAnswerDraft,
                system=context.system_prompt,
                temperature=self._settings.grounded_temperature,
                max_output_tokens=self._settings.grounded_max_output_tokens,
                timeout_seconds=self._settings.grounded_timeout_seconds,
            )
            try:
                validated = validate_draft(generation.value, catalog=context.catalog, limits=limits)
            except GroundedOutputError as error:
                # Logged with the violation only. The rejected statements, the
                # offending id, and the evidence never reach a log line: an
                # invalid answer is still an answer about confidential text.
                logger.info(
                    "grounded output rejected",
                    extra={
                        "violation": error.violation.value,
                        "repair_attempt": repair_attempt,
                        "evidence_count": len(context.catalog),
                    },
                )
                if repair_attempt >= allowed_repairs or not error.is_repairable:
                    raise self._to_app_error(error, repaired=repair_attempt > 0) from error
                prompt = context.user_prompt + repair_instruction(
                    context.catalog, problem=error.feedback
                )
                continue

            return validated, generation.response, repair_attempt

        # Unreachable: the loop either returns or raises on its final pass.
        raise AppError(  # pragma: no cover
            ErrorCode.GROUNDED_OUTPUT_INVALID, "The model did not produce a usable answer."
        )

    async def _resolve_citations(self, validated: ValidatedAnswer) -> tuple[GroundedEvidence, ...]:
        """Resolve each cited entry's spans against stored page text.

        Every locator for the whole answer is resolved in one pass, then handed
        back out, so a multi-page claim and a five-claim answer cost the same
        one query.
        """
        locators: list[SourceLocator] = [
            span for entry in validated.cited for span in entry.candidate.spans
        ]
        resolved = await self._resolver.resolve(locators)

        by_locator = {
            (span.locator.document_id, span.locator.page_number, span.locator.start_char): span
            for span in resolved
        }
        return tuple(
            GroundedEvidence(
                entry=entry,
                spans=tuple(
                    by_locator[(span.document_id, span.page_number, span.start_char)]
                    for span in entry.candidate.spans
                ),
            )
            for entry in validated.cited
        )

    # -- outcomes -----------------------------------------------------------

    def _empty_answer(self, outcome: SearchOutcome, *, warnings: list[str]) -> GroundedAnswer:
        """The deterministic result for a question that retrieved nothing."""
        reason = InsufficientReason.NO_RETRIEVED_EVIDENCE
        return GroundedAnswer(
            answer=INSUFFICIENT_MESSAGES[reason],
            statements=(),
            evidence=(),
            insufficient_evidence=True,
            insufficient_reason=reason,
            retrieval=RetrievalContext(
                mode=outcome.mode,
                profile=outcome.profile,
                searched_index_run_count=outcome.searched_index_run_count,
                retrieved_candidate_count=0,
                included_evidence_count=0,
                omitted_evidence_count=0,
            ),
            generation=None,
            warnings=tuple(warnings),
        )

    @staticmethod
    def _to_app_error(error: GroundedOutputError, *, repaired: bool) -> AppError:
        """Choose the code that tells an operator what actually happened.

        Three outcomes are worth distinguishing, and one code could not: an
        answer that was corrected and still failed, a fabricated identifier, and
        every other broken rule.
        """
        if repaired:
            return AppError(ErrorCode.GROUNDED_REPAIR_FAILED, error.message)
        if error.violation is GroundedViolation.UNKNOWN_EVIDENCE_ID:
            return AppError(ErrorCode.GROUNDED_UNKNOWN_EVIDENCE_ID, error.message)
        return AppError(ErrorCode.GROUNDED_OUTPUT_INVALID, error.message)

    def _log(
        self,
        question: str,
        scope: list[uuid.UUID],
        answer: GroundedAnswer,
        started: float,
        *,
        repair_attempts: int,
    ) -> None:
        """One structured event per grounded answer.

        Counts, codes, and identifiers this server issued - and nothing else.
        The question is reduced to a length and a digest prefix for the same
        reason a search query is: it states what someone is working on, which in
        this domain is confidential before anything is filed. The statements,
        the evidence, the prompt, and the quotes are absent entirely, because a
        log line that carries them has copied the document into a system with a
        different retention policy than the document has.
        """
        generation = answer.generation
        logger.info(
            "grounded answer finished",
            extra={
                "question_length": len(question),
                "question_hash_prefix": hashlib.sha256(question.encode("utf-8")).hexdigest()[:12],
                "document_filter_count": len(scope),
                "retrieval_mode": answer.retrieval.mode.value,
                "index_run_count": answer.retrieval.searched_index_run_count,
                "retrieved_candidate_count": answer.retrieval.retrieved_candidate_count,
                "included_evidence_count": answer.retrieval.included_evidence_count,
                "omitted_evidence_count": answer.retrieval.omitted_evidence_count,
                "provider": generation.provider if generation else None,
                "model": generation.model if generation else None,
                "generation_duration_seconds": (
                    round(generation.duration_seconds, 4) if generation else None
                ),
                "repair_attempts": repair_attempts,
                "statement_count": len(answer.statements),
                "cited_evidence_count": len(answer.evidence),
                "insufficient_evidence": answer.insufficient_evidence,
                "insufficient_reason": (
                    answer.insufficient_reason.value if answer.insufficient_reason else None
                ),
                "warning_count": len(answer.warnings),
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            },
        )


# -- helpers ----------------------------------------------------------------


def _unique_document_ids(document_ids: Sequence[uuid.UUID] | None) -> list[uuid.UUID]:
    """Deduplicate the filter, keeping first-seen order.

    Deterministic rather than set-ordered, so the same request always produces
    the same query and the same log line. A repeated id is a client mistake with
    an obvious intent, not something to reject.
    """
    if not document_ids:
        return []
    seen: dict[uuid.UUID, None] = {}
    for document_id in document_ids:
        seen.setdefault(document_id, None)
    return list(seen)


def _to_candidate(result: SearchResult) -> EvidenceCandidate:
    """Map a retrieval result onto the evidence vocabulary.

    The one place the two layers meet. Retrieval speaks of ranks and spans;
    grounding speaks of what a model may see and what a citation resolves to.
    Doing the conversion explicitly is what keeps ``grounding`` free of the
    service layer, and therefore testable with no database at all.
    """
    return EvidenceCandidate(
        document_id=result.document_id,
        document_name=result.document_filename,
        claim_number=result.claim_number,
        claim_type=result.claim_type,
        depends_on=tuple(result.depends_on),
        text=result.text,
        spans=tuple(
            SourceLocator(
                document_id=result.document_id,
                page_number=span.page_number,
                start_char=span.start_char,
                end_char=span.end_char,
            )
            for span in result.spans
        ),
        fused_rank=result.fused_rank,
        fused_score=result.fused_score,
        dense_rank=result.dense_rank,
        dense_score=result.dense_score,
        lexical_rank=result.lexical_rank,
        lexical_score=result.lexical_score,
    )


def _retrieval_context(outcome: SearchOutcome, context: EvidenceContext) -> RetrievalContext:
    return RetrievalContext(
        mode=outcome.mode,
        profile=outcome.profile,
        searched_index_run_count=outcome.searched_index_run_count,
        retrieved_candidate_count=context.catalog.retrieved_candidate_count,
        included_evidence_count=len(context.catalog),
        omitted_evidence_count=context.catalog.omitted_candidate_count,
    )


def _compose_answer(validated: ValidatedAnswer) -> str:
    """Assemble the answer text from validated statements only.

    When evidence was insufficient, the server's own limitation sentence leads.
    Any statements the model did manage to support are kept after it rather than
    discarded: they passed the same citation check as any other statement, and
    "here is what the evidence does say, and here is what it does not answer" is
    more useful than either half alone.
    """
    body = "\n".join(statement.text for statement in validated.statements)
    if not validated.insufficient_evidence:
        return body

    reason = validated.insufficient_reason or InsufficientReason.NO_RETRIEVED_EVIDENCE
    limitation = INSUFFICIENT_MESSAGES[reason]
    return f"{limitation}\n{body}" if body else limitation
