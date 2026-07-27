"""Metrics for grounded answering.

Several of these are easy to state and easy to misread, so each is defined here
next to the reason it is defined that way.

The one worth reading twice is **citation resolution rate**. It is 1.0 whenever
every returned quote is the stored page text at its own locator - and on a
correctly built system it is *always* 1.0, because a citation that could not be
resolved is refused rather than returned. It is reported not because it is
expected to vary but because it is the phase's central claim, and a claim nobody
measures is a claim nobody notices breaking.

**Evidence selection precision and recall** are the only model-quality numbers
here, and they are meaningful only in the Ollama tier. In the deterministic tier
the oracle cites exactly the labelled claims that reached the prompt, so those
two numbers measure retrieval and the context budget instead - which is worth
measuring, and is not the same thing.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from evals.grounded_dataset import GroundedCase


@dataclass(frozen=True, slots=True)
class CaseOutcome:
    """What one question produced, reduced to what the metrics need."""

    case: GroundedCase
    #: HTTP status. 200 for both an answer and a declared insufficiency.
    status: int
    #: Application error code for a non-200, else ``None``.
    error_code: str | None
    insufficient_evidence: bool
    insufficient_reason: str | None
    statement_count: int
    #: Statements carrying at least one citation.
    cited_statement_count: int
    #: ``(document id, claim number)`` pairs the answer actually cited.
    cited: frozenset[tuple[str, int]]
    #: Whether every returned span's quote equalled the stored page text at its
    #: own locator, checked by reading the pages back through the API.
    citations_resolve: bool
    #: Evidence entries returned with no source span at all. Always zero on a
    #: healthy system; a non-zero value means a citation was returned that a
    #: reader cannot open.
    unresolvable_span_count: int
    retrieved_candidate_count: int
    included_evidence_count: int
    omitted_evidence_count: int
    duration_seconds: float

    # -- derived judgements -------------------------------------------------

    @property
    def produced_structured_output(self) -> bool:
        """Whether the model produced something the schema accepted.

        A 200 always did. A grounded-rule rejection did too - the answer parsed
        and then broke a rule, which is a different failure and is counted
        separately. Only a malformed or schema-invalid payload did not.
        """
        if self.status == 200:
            return True
        return self.error_code not in {
            "llm_malformed_json",
            "llm_structured_output_validation_failed",
            "llm_invalid_provider_response",
        }

    @property
    def evidence_ids_valid(self) -> bool:
        """Whether no citation was fabricated.

        False exactly when the answer was refused for naming an identifier the
        server never issued - including when a repair attempt was spent first.
        """
        return self.error_code not in {
            "grounded_unknown_evidence_id",
            "grounded_repair_failed",
        }

    @property
    def answerability_correct(self) -> bool:
        """Whether the system's answer/decline judgement matched the label.

        An ambiguous case counts as correct either way; see
        ``GroundedCase.is_ambiguous`` for when that applies and why.
        """
        if self.status != 200:
            return False
        if self.case.is_ambiguous:
            return True
        return self.insufficient_evidence != self.case.answerable

    @property
    def reason_acceptable(self) -> bool:
        """Whether a declined answer gave a reason the label allows."""
        if not self.insufficient_evidence:
            return True
        if not self.case.reasons:
            return False
        return self.insufficient_reason in self.case.reasons

    @property
    def cited_forbidden(self) -> frozenset[tuple[str, int]]:
        """Cited claims the label forbids - a leaked document scope."""
        return self.cited & self.case.forbidden

    @property
    def statement_citation_coverage(self) -> float | None:
        """Fraction of returned statements carrying a citation.

        ``None`` when there were no statements, so an empty answer does not
        contribute a 0.0 that reads as "the model cited nothing".
        """
        if self.statement_count == 0:
            return None
        return self.cited_statement_count / self.statement_count

    @property
    def selection_precision(self) -> float | None:
        """Cited claims that were credited, over all cited claims."""
        if not self.cited:
            return None
        return len(self.cited & self.case.all_credited) / len(self.cited)

    @property
    def selection_recall(self) -> float | None:
        """Required claims that were cited, over all required claims."""
        if not self.case.relevant:
            return None
        return len(self.cited & self.case.relevant) / len(self.case.relevant)

    @property
    def end_to_end_success(self) -> bool:
        """The composite: did this question get a defensible, checkable answer?

        Every part has to hold. A case that answers correctly but cites outside
        its document scope fails, and so does one that reaches the right
        conclusion with a citation a reader cannot open.
        """
        if self.status != 200 or not self.citations_resolve or self.cited_forbidden:
            return False
        if not self.answerability_correct or not self.reason_acceptable:
            return False
        if self.insufficient_evidence:
            return True
        if self.case.is_ambiguous:
            return bool(self.cited <= self.case.all_credited)
        return (self.selection_recall or 0.0) > 0.0


@dataclass(frozen=True, slots=True)
class GroundedSummary:
    """Aggregates over one tier's run."""

    case_count: int
    structured_output_rate: float
    answerability_accuracy: float
    insufficient_precision: float
    insufficient_recall: float
    evidence_id_validity_rate: float
    citation_resolution_rate: float
    statement_citation_coverage: float
    selection_precision: float
    selection_recall: float
    end_to_end_success_rate: float
    forbidden_citation_count: int
    mean_duration_seconds: float

    def as_dict(self) -> dict[str, float | int]:
        return {
            "case_count": self.case_count,
            "structured_output_rate": round(self.structured_output_rate, 4),
            "answerability_accuracy": round(self.answerability_accuracy, 4),
            "insufficient_precision": round(self.insufficient_precision, 4),
            "insufficient_recall": round(self.insufficient_recall, 4),
            "evidence_id_validity_rate": round(self.evidence_id_validity_rate, 4),
            "citation_resolution_rate": round(self.citation_resolution_rate, 4),
            "statement_citation_coverage": round(self.statement_citation_coverage, 4),
            "selection_precision": round(self.selection_precision, 4),
            "selection_recall": round(self.selection_recall, 4),
            "end_to_end_success_rate": round(self.end_to_end_success_rate, 4),
            "forbidden_citation_count": self.forbidden_citation_count,
            "mean_duration_seconds": round(self.mean_duration_seconds, 3),
        }


def summarise(outcomes: Sequence[CaseOutcome]) -> GroundedSummary:
    """Aggregate one tier's outcomes.

    Insufficiency is scored as a retrieval-style precision/recall pair over the
    decision to decline, because the two errors are not equivalent and averaging
    them into one accuracy would hide which one is happening. Declining a
    question the corpus answers withholds a usable answer; answering one it does
    not is the failure this whole phase exists to prevent, and it should be
    visible on its own axis.
    """
    if not outcomes:
        return GroundedSummary(0, *([0.0] * 9), 0, 0.0)  # type: ignore[arg-type]

    total = len(outcomes)
    # Ambiguous cases are excluded from the insufficiency pair: they have no
    # single correct decision, so counting them would move the number without
    # anything having gone right or wrong.
    judged = [outcome for outcome in outcomes if not outcome.case.is_ambiguous]
    should_decline = [outcome for outcome in judged if not outcome.case.answerable]
    declined_judged = [outcome for outcome in judged if outcome.insufficient_evidence]
    correct_declines = [outcome for outcome in declined_judged if not outcome.case.answerable]

    return GroundedSummary(
        case_count=total,
        structured_output_rate=_rate(o.produced_structured_output for o in outcomes),
        answerability_accuracy=_rate(o.answerability_correct for o in outcomes),
        insufficient_precision=(
            len(correct_declines) / len(declined_judged) if declined_judged else 1.0
        ),
        insufficient_recall=(
            len(correct_declines) / len(should_decline) if should_decline else 1.0
        ),
        evidence_id_validity_rate=_rate(o.evidence_ids_valid for o in outcomes),
        citation_resolution_rate=_rate(o.citations_resolve for o in outcomes),
        statement_citation_coverage=_mean(o.statement_citation_coverage for o in outcomes),
        selection_precision=_mean(o.selection_precision for o in outcomes),
        selection_recall=_mean(o.selection_recall for o in outcomes),
        end_to_end_success_rate=_rate(o.end_to_end_success for o in outcomes),
        forbidden_citation_count=sum(len(o.cited_forbidden) for o in outcomes),
        mean_duration_seconds=sum(o.duration_seconds for o in outcomes) / total,
    )


def _rate(values: object) -> float:
    items = list(values)  # type: ignore[call-overload]
    return sum(1 for value in items if value) / len(items) if items else 0.0


def _mean(values: object) -> float:
    """Mean over the cases where the metric is defined at all.

    A ``None`` is "not applicable here", not zero: averaging in a 0.0 for a
    question that legitimately cited nothing would report a precision failure
    that did not happen.
    """
    items = [value for value in values if value is not None]  # type: ignore[union-attr]
    return sum(items) / len(items) if items else 0.0
