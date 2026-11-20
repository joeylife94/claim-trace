"""Replay captured grounded drafts offline, under the current rules and named counterfactuals.

    python -m evals.grounded_replay RUN_DIR [--rules RULE ...] [--json-out PATH]

A D8 run directory written with ``--capture-diagnostics`` holds every draft the model
produced. This tool re-validates each one with the product's own ``validate_draft`` and scores
the outcome with the harness's own ``CaseOutcome`` / ``summarise`` and the committed case
labels. It makes no model call, no network call and no database call.

Two things are reported per segment:

* a **self-check**: under the current rules the replay must reproduce every recorded verdict
  and served outcome, and every recorded hash. If it cannot, the tool refuses that segment
  (exit status 3) and prints no counterfactual table for it, because a replay that does not
  match the record says nothing about a changed rule;
* a **counterfactual table** per selected rule and flow. A rule is a pure function of the
  draft (see ``RULES``); the model is never asked anything again.

What a replay cannot say: how the model would answer *different* feedback wording, a different
prompt or schema, another runtime or another model. ``two_attempt`` therefore reports
``not_replayable`` for a case whose counterfactual repair prompt differs from the recorded one,
and aggregates over replayable cases only. Nothing is imputed. ``citations_resolve`` is
*assumed* true (there is no database here); every output says so.

``diagnostics-*.json`` is untrusted text. It is read as data and nothing from it is printed or
stored: every string in the output is a number, a hash prefix, a catalog label, a closed-set
code or a committed case id (anything else prints as ``other``).

Exit status: 0 ok (also when nothing was captured), 2 unusable input, 3 self-check failed.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path
from typing import Any

from claimtrace_api.db.models import ClaimType
from claimtrace_api.grounding.context import repair_instruction
from claimtrace_api.grounding.draft import (
    MAX_EVIDENCE_IDS_PER_STATEMENT,
    MAX_STATEMENT_CHARACTERS,
    MAX_STATEMENTS,
    GroundedAnswerDraft,
)
from claimtrace_api.grounding.evidence import (
    EvidenceCandidate,
    EvidenceCatalog,
    build_catalog,
    evidence_id_for_position,
)
from claimtrace_api.grounding.validation import (
    GroundedOutputError,
    OutputLimits,
    ValidatedAnswer,
    validate_draft,
)
from claimtrace_api.llm.json_output import parse_structured_output
from claimtrace_api.services.grounded_generation import GroundedGenerationService
from evals.grounded_capture import parse_catalog, prompt_digest, sha256_text
from evals.grounded_dataset import GroundedCase, load_grounded_cases, load_grounded_documents
from evals.grounded_metrics import CaseOutcome, summarise

SCHEMA_VERSION = 1

#: The limits the run used: the config and Compose defaults equal these constants. The
#: self-check is what proves that assumption held for a given run.
LIMITS = OutputLimits(
    max_statements=MAX_STATEMENTS,
    max_statement_characters=MAX_STATEMENT_CHARACTERS,
    max_evidence_ids_per_statement=MAX_EVIDENCE_IDS_PER_STATEMENT,
)

ASSUMPTIONS = (
    "citations_resolve is ASSUMED true for every served answer (no database is consulted); "
    "durations are not replayed (mean_duration_seconds is omitted); limits are the product "
    "constants, which the self-check confirms against the record."
)
NOT_REPLAYABLE_NOTE = (
    "two_attempt covers replayable cases only; a repair whose prompt differs from the recorded "
    "one, or that was never recorded, cannot be replayed and is counted, not imputed. The "
    "model's answer to different feedback, prompt, schema, runtime or model is not replayable."
)

CODE_PATTERN = re.compile(r"^[a-z_]{1,48}$")
TAG_PATTERN = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._-]{0,63}$")
_SEGMENT_DIR = re.compile(r"^r(\d+)$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


# -- rules and flows ---------------------------------------------------------------------


def _is_stray_reason(draft: GroundedAnswerDraft) -> bool:
    return draft.insufficient_evidence is False and draft.insufficient_reason is not None


def _current(draft: GroundedAnswerDraft) -> GroundedAnswerDraft:
    return draft


def _drop_stray_reason(draft: GroundedAnswerDraft) -> GroundedAnswerDraft:
    if _is_stray_reason(draft):
        return draft.model_copy(update={"insufficient_reason": None})
    return draft


def _honour_stray_reason(draft: GroundedAnswerDraft) -> GroundedAnswerDraft:
    if _is_stray_reason(draft):
        return draft.model_copy(update={"insufficient_evidence": True})
    return draft


#: The closed set. Neither counterfactual touches the other contradiction (flag true, reason
#: null). Adding a rule means adding an entry here.
RULES: dict[str, Callable[[GroundedAnswerDraft], GroundedAnswerDraft]] = {
    "current": _current,
    "drop_stray_reason": _drop_stray_reason,
    "honour_stray_reason": _honour_stray_reason,
}
FLOWS = ("first_draft", "two_attempt")


class ReplayRefused(Exception):
    """The directory cannot be replayed at all (exit status 2)."""


# -- what one case needs --------------------------------------------------------------------


@dataclass
class Attempt:
    index: int
    outcome: str
    violation: str | None
    prompt_sha256: str | None
    #: ``None`` when the attempt cannot be replayed (provider error, not validated, or the
    #: raw output did not parse).
    draft: GroundedAnswerDraft | None = None
    unknown_id_count: int = 0


@dataclass
class Prepared:
    case: GroundedCase
    record: dict[str, Any]
    catalog: EvidenceCatalog | None = None
    system: str | None = None
    user_prompt: str = ""
    attempts: list[Attempt] = field(default_factory=list)
    #: Structural self-check failures found while preparing the case.
    failures: list[str] = field(default_factory=list)
    no_model_call: bool = False


@dataclass
class FlowResult:
    verdicts: list[str] = field(default_factory=list)
    outcome: CaseOutcome | None = None
    distinct_statement_count: int = 0
    not_replayable: str | None = None


def _label(entry_document: str, claim_number: int) -> str:
    return f"{entry_document}#{claim_number}"


def _build_catalog(entries: list[dict[str, Any]]) -> EvidenceCatalog:
    candidates = tuple(
        EvidenceCandidate(
            document_id=uuid.uuid5(uuid.NAMESPACE_URL, entry["document"]),
            document_name=entry["document"],
            claim_number=entry["claim_number"],
            # Validation reads neither the type nor the text; any value will do.
            claim_type=ClaimType.INDEPENDENT,
            depends_on=(),
            text="",
            spans=(),
            fused_rank=position,
            fused_score=0.0,
        )
        for position, entry in enumerate(entries, start=1)
    )
    return build_catalog(candidates, retrieved_candidate_count=len(candidates))


def _sha(value: Any) -> str | None:
    return value if isinstance(value, str) and _HEX64.fullmatch(value) else None


def prepare_case(
    record: dict[str, Any],
    raw_case: dict[str, Any] | None,
    system_prompts: Mapping[str, str],
    corpus_ids: Mapping[str, str],
    cases: Mapping[str, GroundedCase],
) -> Prepared:
    """Rebuild one case from the two files and run the structural checks (self-check 1-2)."""
    case = cases.get(record.get("id"))  # type: ignore[arg-type]
    if case is None:
        raise KeyError("unknown_case")
    prepared = Prepared(case=case, record=record)
    block = record["diagnostics"]
    attempts_record = block["attempts"]
    if raw_case is None:
        prepared.failures.append("raw_case_missing")
        return prepared
    calls = raw_case["calls"]
    if len(calls) != len(attempts_record):
        prepared.failures.append("call_count_mismatch")
        return prepared
    if not calls:
        prepared.no_model_call = True
        if block["catalog"]:
            prepared.failures.append("catalog_without_call")
        return prepared

    entries = block["catalog"]
    if any(
        not isinstance(entry.get("document"), str)
        or entry["document"] not in corpus_ids.values()
        or not isinstance(entry.get("claim_number"), int)
        for entry in entries
    ):
        prepared.failures.append("catalog_unknown_document")
        return prepared
    if [entry.get("evidence_id") for entry in entries] != [
        evidence_id_for_position(position) for position in range(1, len(entries) + 1)
    ]:
        prepared.failures.append("catalog_ids_out_of_order")
        return prepared
    first = calls[0]
    if parse_catalog(first["user_prompt"], corpus_ids) != entries:
        prepared.failures.append("catalog_mismatch_prompt")
        return prepared
    prepared.catalog = _build_catalog(entries)

    system_sha = first.get("system_prompt_sha256")
    prepared.system = system_prompts.get(system_sha) if system_sha is not None else None
    if system_sha is not None and (
        prepared.system is None or sha256_text(prepared.system) != system_sha
    ):
        prepared.failures.append("system_prompt_hash_mismatch")
        return prepared
    prepared.user_prompt = first["user_prompt"]

    for index, (call, recorded) in enumerate(zip(calls, attempts_record, strict=True)):
        attempt = Attempt(
            index=index,
            outcome=str(recorded.get("outcome")),
            violation=recorded.get("violation"),
            prompt_sha256=_sha(recorded.get("prompt_sha256")),
        )
        prepared.attempts.append(attempt)
        if call.get("user_prompt_truncated") or call.get("raw_output_truncated"):
            prepared.failures.append(f"truncated_attempt_{index}")
        if attempt.outcome not in {"accepted", "rejected"}:
            continue
        raw = call.get("raw_output")
        if not isinstance(raw, str):
            prepared.failures.append(f"raw_output_missing_attempt_{index}")
            continue
        digest = sha256_text(raw)
        if digest != call.get("raw_output_sha256") or digest != recorded.get("raw_output_sha256"):
            prepared.failures.append(f"raw_hash_mismatch_attempt_{index}")
        try:
            attempt.draft = parse_structured_output(raw, GroundedAnswerDraft)
        except Exception:  # noqa: BLE001 - the parser's message may quote model text; drop it
            prepared.failures.append(f"unparseable_output_attempt_{index}")
            continue
        attempt.unknown_id_count = sum(
            1
            for statement in attempt.draft.supported_statements
            for evidence_id in statement.evidence_ids
            if not prepared.catalog.contains(evidence_id)
        )

    if _attempt_digest(prepared, prepared.user_prompt) != prepared.attempts[0].prompt_sha256:
        prepared.failures.append("prompt_hash_mismatch_attempt_0")
    return prepared


def _attempt_digest(prepared: Prepared, user_prompt: str) -> str:
    messages = [("user", user_prompt)]
    if prepared.system is not None:
        messages.insert(0, ("system", prepared.system))
    return prompt_digest(messages)


def _validate(
    prepared: Prepared, draft: GroundedAnswerDraft, rule: Callable[..., Any]
) -> ValidatedAnswer | GroundedOutputError:
    assert prepared.catalog is not None
    try:
        return validate_draft(rule(draft), catalog=prepared.catalog, limits=LIMITS)
    except GroundedOutputError as error:
        return error


def _served(prepared: Prepared, validated: ValidatedAnswer) -> tuple[CaseOutcome, int]:
    outcome = CaseOutcome(
        case=prepared.case,
        status=200,
        error_code=None,
        insufficient_evidence=validated.insufficient_evidence,
        insufficient_reason=(
            validated.insufficient_reason.value if validated.insufficient_reason else None
        ),
        statement_count=len(validated.statements),
        cited_statement_count=len(validated.statements),
        cited=frozenset(
            (entry.candidate.document_name, entry.candidate.claim_number)
            for entry in validated.cited
        ),
        # Assumed: nothing here can read pages back.
        citations_resolve=True,
        unresolvable_span_count=0,
        retrieved_candidate_count=0,
        included_evidence_count=0,
        omitted_evidence_count=0,
        duration_seconds=0.0,
    )
    return outcome, len({statement.text for statement in validated.statements})


def _refused(prepared: Prepared, error: GroundedOutputError, *, repaired: bool) -> CaseOutcome:
    # The same zero fields grounded_run._score uses for a non-200.
    return CaseOutcome(
        case=prepared.case,
        status=502,
        error_code=GroundedGenerationService._to_app_error(error, repaired=repaired).code.value,
        insufficient_evidence=False,
        insufficient_reason=None,
        statement_count=0,
        cited_statement_count=0,
        cited=frozenset(),
        citations_resolve=True,
        unresolvable_span_count=0,
        retrieved_candidate_count=0,
        included_evidence_count=0,
        omitted_evidence_count=0,
        duration_seconds=0.0,
    )


def _verdict(result: ValidatedAnswer | GroundedOutputError) -> str:
    return result.violation.value if isinstance(result, GroundedOutputError) else "pass"


def run_flow(prepared: Prepared, flow: str, rule_name: str) -> FlowResult:
    """One case under one flow and one rule."""
    rule = RULES[rule_name]
    result = FlowResult()
    if prepared.no_model_call:
        result.not_replayable = "no_model_call"
        return result
    first = prepared.attempts[0]
    if first.draft is None:
        result.not_replayable = (
            first.outcome if first.outcome in {"provider_error", "not_validated"} else "unreadable"
        )
        return result

    verdict = _validate(prepared, first.draft, rule)
    result.verdicts.append(_verdict(verdict))
    if isinstance(verdict, ValidatedAnswer):
        result.outcome, result.distinct_statement_count = _served(prepared, verdict)
        return result
    if flow == "first_draft":
        result.outcome = _refused(prepared, verdict, repaired=False)
        return result

    if len(prepared.attempts) < 2:
        result.not_replayable = "repair_not_recorded"
        return result
    second = prepared.attempts[1]
    assert prepared.catalog is not None
    repair_prompt = (
        prepared.user_prompt + repair_instruction(prepared.catalog, problem=verdict.feedback)
    ).strip()
    if _attempt_digest(prepared, repair_prompt) != second.prompt_sha256:
        result.not_replayable = "repair_prompt_differs"
        return result
    if second.draft is None:
        result.not_replayable = (
            second.outcome
            if second.outcome in {"provider_error", "not_validated"}
            else "unreadable"
        )
        return result
    final = _validate(prepared, second.draft, rule)
    result.verdicts.append(_verdict(final))
    if isinstance(final, ValidatedAnswer):
        result.outcome, result.distinct_statement_count = _served(prepared, final)
    else:
        result.outcome = _refused(prepared, final, repaired=True)
    return result


# -- self-check ----------------------------------------------------------------------------


#: Not a failure: the record itself says there is nothing to compare.
_SKIPPED = frozenset({"provider_error", "not_validated", "no_model_call"})


def self_check_case(prepared: Prepared) -> list[str]:
    """Self-check 3-5 for one case, appended to the structural failures of 1-2."""
    failures = list(prepared.failures)
    if prepared.no_model_call or any(f.startswith(("catalog", "raw_case")) for f in failures):
        return failures
    if prepared.catalog is None or not prepared.attempts:
        return failures
    for attempt in prepared.attempts:
        if attempt.draft is None:
            continue
        verdict = _verdict(_validate(prepared, attempt.draft, _current))
        recorded = attempt.violation if attempt.outcome == "rejected" else "pass"
        if attempt.outcome == "rejected" and not isinstance(recorded, str):
            recorded = None
        if verdict != recorded:
            failures.append(f"verdict_mismatch_attempt_{attempt.index}")

    flow = run_flow(prepared, "two_attempt", "current")
    if flow.not_replayable in _SKIPPED:
        return failures
    if flow.not_replayable is not None:
        failures.append(flow.not_replayable)
        return failures
    outcome = flow.outcome
    assert outcome is not None
    record = prepared.record
    served = (
        record.get("status"),
        record.get("error_code"),
        record.get("insufficient_evidence"),
        record.get("insufficient_reason"),
        record.get("statements"),
        sorted(record.get("cited") or []),
        record.get("end_to_end_success"),
    )
    replayed = (
        outcome.status,
        outcome.error_code,
        outcome.insufficient_evidence,
        outcome.insufficient_reason,
        outcome.statement_count,
        sorted(_label(*pair) for pair in outcome.cited),
        outcome.end_to_end_success,
    )
    if served != replayed:
        failures.append("served_outcome_mismatch")
    return failures


# -- segments ---------------------------------------------------------------------------------


@dataclass
class Segment:
    name: str
    tier: str
    tag: str | None
    repeat_index: int | None
    prepared: list[Prepared]
    failures: dict[str, list[str]]
    attempt_outcomes: Counter[str]
    not_replayable_cases: Counter[str]

    @property
    def ok(self) -> bool:
        return not self.failures


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ReplayRefused("a required file is missing")
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ReplayRefused("a required file is not readable JSON") from error
    if not isinstance(loaded, dict):
        raise ReplayRefused("a required file is not a JSON object")
    return loaded


def _safe_case_id(value: object, cases: Mapping[str, GroundedCase]) -> str:
    return value if isinstance(value, str) and value in cases else "other"


def load_segment(
    name: str,
    tier: str,
    folder: Path,
    *,
    corpus_ids: Mapping[str, str],
    cases: Mapping[str, GroundedCase],
) -> Segment | None:
    """``None`` when the tier carries no diagnostics at all (a pre-D8-02 directory)."""
    results = _read_json(folder / f"results-{tier}.json")
    per_case = results.get("per_case")
    if not isinstance(per_case, list):
        raise ReplayRefused("results file has no per_case list")
    if not any(isinstance(item, dict) and "diagnostics" in item for item in per_case):
        return None
    raw = _read_json(folder / f"diagnostics-{tier}.json")
    system_prompts = raw.get("system_prompts")
    raw_cases = raw.get("cases")
    if not isinstance(system_prompts, dict) or not isinstance(raw_cases, list):
        raise ReplayRefused("diagnostics file has an unexpected shape")
    raw_by_id = {c.get("id"): c for c in raw_cases if isinstance(c, dict)}

    tag: str | None = None
    repeat_index: int | None = None
    segment_file = folder / "segment.json"
    if segment_file.is_file():
        info = _read_json(segment_file)
        raw_tag = info.get("ollama_image_tag")
        tag = raw_tag if isinstance(raw_tag, str) and TAG_PATTERN.fullmatch(raw_tag) else None
        index = info.get("repeat_index")
        repeat_index = index if isinstance(index, int) and not isinstance(index, bool) else None

    segment = Segment(name, tier, tag, repeat_index, [], {}, Counter(), Counter())
    for item in per_case:
        case_label = _safe_case_id(item.get("id") if isinstance(item, dict) else None, cases)
        try:
            prepared = prepare_case(
                item, raw_by_id.get(item.get("id")), system_prompts, corpus_ids, cases
            )
            failures = self_check_case(prepared)
        except (KeyError, TypeError, ValueError, AttributeError, IndexError):
            segment.failures.setdefault(case_label, []).append("malformed_record")
            continue
        segment.prepared.append(prepared)
        if failures:
            segment.failures[case_label] = failures
            continue
        for attempt in prepared.attempts:
            segment.attempt_outcomes[
                attempt.outcome if attempt.outcome in _OUTCOMES else "other"
            ] += 1
        replay = run_flow(prepared, "two_attempt", "current")
        if replay.not_replayable in _SKIPPED:
            segment.not_replayable_cases[replay.not_replayable] += 1
    return segment


_OUTCOMES = frozenset({"accepted", "rejected", "provider_error", "not_validated"})


# -- aggregation and output ------------------------------------------------------------------


def _rows(
    segment: Segment, flow: str, rule: str, cases: Mapping[str, GroundedCase]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    outcomes: list[CaseOutcome] = []
    unreplayable: Counter[str] = Counter()
    for prepared in segment.prepared:
        result = run_flow(prepared, flow, rule)
        row: dict[str, Any] = {"id": _safe_case_id(prepared.case.id, cases)}
        if result.outcome is None:
            code = result.not_replayable or "unreadable"
            row["not_replayable"] = code if CODE_PATTERN.fullmatch(code) else "other"
            unreplayable[row["not_replayable"]] += 1
        else:
            outcome = result.outcome
            outcomes.append(outcome)
            row.update(
                status=outcome.status,
                error_code=outcome.error_code,
                attempt_verdicts=result.verdicts,
                insufficient_evidence=outcome.insufficient_evidence,
                insufficient_reason=outcome.insufficient_reason,
                statement_count=outcome.statement_count,
                distinct_statement_count=result.distinct_statement_count,
                cited=sorted(_label(*pair) for pair in outcome.cited),
                end_to_end_success=outcome.end_to_end_success,
                answerability_correct=outcome.answerability_correct,
                reason_acceptable=outcome.reason_acceptable,
            )
        rows.append(row)
    aggregate = {
        key: value
        for key, value in summarise(outcomes).as_dict().items()
        if key != "mean_duration_seconds"
    }
    return rows, {
        "aggregate": aggregate,
        "replayable_cases": len(outcomes),
        "not_replayable_cases": sum(unreplayable.values()),
        "not_replayable_by_code": dict(sorted(unreplayable.items())),
    }


def observables(segment: Segment) -> dict[str, int]:
    stray = bare = invented = 0
    for prepared in segment.prepared:
        for attempt in prepared.attempts:
            invented += attempt.unknown_id_count
        first = prepared.attempts[0].draft if prepared.attempts else None
        if first is None:
            continue
        if _is_stray_reason(first):
            stray += 1
        elif first.insufficient_evidence and first.insufficient_reason is None:
            bare += 1
    return {
        "stray_reason_first_drafts": stray,
        "bare_decline_first_drafts": bare,
        "evidence_ids_not_in_catalog_all_attempts": invented,
    }


def pair_facts(a: Segment, b: Segment, cases: Mapping[str, GroundedCase]) -> dict[str, Any]:
    """Attempt-0 comparisons from the results files only (no draft is parsed)."""

    def first(segment: Segment) -> dict[str, dict[str, Any]]:
        found: dict[str, dict[str, Any]] = {}
        for prepared in segment.prepared:
            attempts = prepared.record["diagnostics"]["attempts"]
            if attempts:
                found[prepared.case.id] = attempts[0]
        return found

    left, right = first(a), first(b)
    shared = sorted(set(left) & set(right))
    differs = [c for c in shared if left[c].get("prompt_sha256") != right[c].get("prompt_sha256")]
    equal = [c for c in shared if c not in differs]
    return {
        "kind": "repeat_pair" if a.tag is not None and a.tag == b.tag else "version_pair",
        "segments": [a.name, b.name],
        "cases_compared": len(shared),
        "prompt_differs": len(differs),
        "prompt_differs_cases": [_safe_case_id(c, cases) for c in differs],
        "equal_prompt_raw_differences": sum(
            1
            for c in equal
            if left[c].get("raw_output_sha256") != right[c].get("raw_output_sha256")
        ),
        "equal_prompt_token_differences": sum(
            1
            for c in equal
            if left[c].get("prompt_eval_count") != right[c].get("prompt_eval_count")
        ),
    }


def _fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, list):
        return ",".join(value) if value else "-"
    return str(value)


def _row_line(row: dict[str, Any]) -> str:
    if "not_replayable" in row:
        return f"  {row['id']:<32} not_replayable: {row['not_replayable']}"
    return (
        f"  {row['id']:<32} status={row['status']} error={_fmt(row['error_code'])} "
        f"verdicts={_fmt(row['attempt_verdicts'])} flag={row['insufficient_evidence']} "
        f"reason={_fmt(row['insufficient_reason'])} statements={row['statement_count']} "
        f"distinct={row['distinct_statement_count']} cited={_fmt(row['cited'])} "
        f"e2e={row['end_to_end_success']} answerability={row['answerability_correct']} "
        f"reason_ok={row['reason_acceptable']}"
    )


def discover(run_dir: Path) -> list[tuple[str, str, Path]]:
    """``(segment name, tier, folder)`` in a stable order: oracle first, then r1, r2, ..."""
    grounded = run_dir / "grounded"
    found: list[tuple[str, str, Path]] = []
    if (grounded / "results-deterministic.json").is_file():
        found.append(("oracle", "deterministic", grounded))
    numbered = sorted(
        (int(m.group(1)), child)
        for child in grounded.iterdir()
        if child.is_dir() and (m := _SEGMENT_DIR.match(child.name))
    )
    found.extend((child.name, "ollama", child) for _, child in numbered)
    if not numbered and (grounded / "results-ollama.json").is_file():
        found.append(("ollama", "ollama", grounded))
    return found


def replay(run_dir: Path, rules: list[str]) -> tuple[list[str], dict[str, Any], bool, bool]:
    """Returns ``(text lines, json document, self_check_ok, anything_captured)``."""
    if not (run_dir / "grounded").is_dir():
        raise ReplayRefused("RUN_DIR has no grounded/ directory")
    found = discover(run_dir)
    if not found:
        raise ReplayRefused("no grounded results file found")
    corpus_ids = {d.filename: d.id for d in load_grounded_documents()}
    cases = {c.id: c for c in load_grounded_cases()}

    segments: list[Segment] = []
    for name, tier, folder in found:
        loaded = load_segment(name, tier, folder, corpus_ids=corpus_ids, cases=cases)
        if loaded is not None:
            segments.append(loaded)

    name = run_dir.resolve().name
    document: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "run": name if re.fullmatch(r"[A-Za-z0-9._-]{1,96}", name) else "other",
        "assumptions": ASSUMPTIONS,
        "segments": [],
        "pairs": [],
    }
    if not segments:
        return (["no diagnostics captured; nothing to replay"], document, True, False)

    lines = [
        f"GROUNDED REPLAY  run={document['run']}  schema_version={SCHEMA_VERSION}",
        f"ASSUMPTIONS: {ASSUMPTIONS}",
        f"NOT REPLAYABLE: {NOT_REPLAYABLE_NOTE}",
        "All strings below are numbers, catalog labels, closed-set codes or committed case ids;"
        " no model or prompt text is read into this output.",
    ]
    all_ok = True
    for segment in segments:
        all_ok &= segment.ok
        lines += _segment_lines(segment, rules, cases, document)
    llm = [s for s in segments if s.tier == "ollama"]
    if len(llm) >= 2:
        lines += ["", "== segment pairs (from the results files only; observed, not a rule) =="]
        for left, right in combinations(llm, 2):
            facts = pair_facts(left, right, cases)
            document["pairs"].append(facts)
            lines.append(
                f"{facts['kind']} {left.name}-{right.name}: "
                f"cases_compared={facts['cases_compared']} "
                f"prompt_differs={facts['prompt_differs']} ({_fmt(facts['prompt_differs_cases'])}) "
                f"equal_prompt_raw_differences={facts['equal_prompt_raw_differences']} "
                f"equal_prompt_token_differences={facts['equal_prompt_token_differences']}"
            )
    return lines, document, all_ok, True


def _segment_lines(
    segment: Segment,
    rules: list[str],
    cases: Mapping[str, GroundedCase],
    document: dict[str, Any],
) -> list[str]:
    heading = f"== segment {segment.name} (tier {segment.tier}"
    if segment.tag:
        heading += f", ollama tag {segment.tag}"
    if segment.repeat_index is not None:
        heading += f", repeat {segment.repeat_index}"
    lines = ["", heading + ") =="]
    attempts = sum(segment.attempt_outcomes.values())
    skipped = (
        ", ".join(f"{k}={v}" for k, v in sorted(segment.not_replayable_cases.items())) or "none"
    )
    entry: dict[str, Any] = {
        "name": segment.name,
        "tier": segment.tier,
        "tag": segment.tag,
        "repeat_index": segment.repeat_index,
        "self_check": {
            "ok": segment.ok,
            "cases": len(segment.prepared) + sum(1 for k in segment.failures if k == "other"),
            "attempts": attempts,
            "attempt_outcomes": dict(sorted(segment.attempt_outcomes.items())),
            "not_replayable_cases": dict(sorted(segment.not_replayable_cases.items())),
            "failures": {k: sorted(v) for k, v in sorted(segment.failures.items())},
        },
    }
    document["segments"].append(entry)
    if not segment.ok:
        lines.append(f"self-check: FAIL ({len(segment.failures)} case(s)); segment refused")
        lines += [
            f"  {case}: {', '.join(codes)}" for case, codes in sorted(segment.failures.items())
        ]
        return lines
    lines.append(
        f"self-check: PASS ({len(segment.prepared)} cases, {attempts} attempts; every recorded "
        f"hash, verdict and served outcome reproduced; not replayable by record: {skipped})"
    )
    if segment.tier != "ollama":
        lines.append("oracle tier: self-check only (no counterfactual tables)")
        return lines
    entry["observables"] = observables(segment)
    lines.append(
        "observed in the captured first drafts (counts defined after Run A, not a product "
        "metric): " + ", ".join(f"{k}={v}" for k, v in entry["observables"].items())
    )
    entry["tables"] = {}
    for rule in rules:
        for flow in FLOWS:
            rows, summary = _rows(segment, flow, rule, cases)
            entry["tables"][f"{flow}/{rule}"] = {"cases": rows, **summary}
            lines += [
                "",
                f"-- {flow} / {rule}: replayable {summary['replayable_cases']}, "
                f"not replayable {summary['not_replayable_cases']} "
                f"{summary['not_replayable_by_code'] or ''}".rstrip(),
                *[_row_line(row) for row in rows],
                "  aggregate (replayable cases only): "
                + ", ".join(f"{k}={v}" for k, v in summary["aggregate"].items()),
            ]
    return lines


# -- CLI --------------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m evals.grounded_replay",
        description="Replay captured grounded drafts offline (no raw model text is printed).",
    )
    parser.add_argument("run_dir", type=Path)
    parser.add_argument(
        "--rules",
        nargs="+",
        choices=sorted(RULES),
        default=list(RULES),
        help="counterfactual rules to tabulate (default: all)",
    )
    parser.add_argument("--json-out", type=Path, default=None)
    arguments = parser.parse_args(argv)

    try:
        run_dir = arguments.run_dir
        if not run_dir.is_dir():
            raise ReplayRefused("RUN_DIR is not a directory")
        if arguments.json_out is not None:
            target = arguments.json_out.resolve()
            if target.is_relative_to(run_dir.resolve()):
                raise ReplayRefused(
                    "--json-out must not be inside RUN_DIR (it is a committed record)"
                )
        lines, document, ok, captured = replay(run_dir, list(dict.fromkeys(arguments.rules)))
    except ReplayRefused as refusal:
        print(f"GROUNDED REPLAY REFUSED: {refusal}", file=sys.stderr)
        return 2
    print("\n".join(lines))
    if arguments.json_out is not None and captured:
        arguments.json_out.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return 0 if ok else 3


if __name__ == "__main__":
    sys.exit(main())
