"""Validate a D8 real-model measurement run and turn it into a summary and a report.

    python -m evals.d8_report --run-dir DIR --expected-llm-model qwen2.5:1.5b \\
        --expected-repeats 2 --emit

This tool decides whether a measurement may be trusted at all, so it is strict
before it is helpful. It reads the files the two evaluation entry points wrote
(``evals.run`` and ``evals.grounded_run``), plus an ``ENVIRONMENT.json`` written by
the workflow, and refuses the whole run - non-zero exit, one reason per violation on
stderr, and **no** summary written - when any of these hold:

* an embedding provider other than ``sentence-transformers`` (a ``fake`` run looks
  exactly like a real one in shape, which is why this is checked on every file);
* an embedding model other than ``intfloat/multilingual-e5-small``;
* an oracle-tier file whose provider is not ``oracle``;
* an LLM file whose provider is not ``ollama`` or whose model differs from the one
  that was asked for, or one reporting the provider or the model as unavailable;
* corpus counts that differ from the committed datasets, a case list that differs
  from the committed cases, or a file that is cut short;
* a missing (or unexpected) repeat, or a missing ``ENVIRONMENT.json`` field.

A request that failed for one case (a timeout, a 502 from the pipeline) is a
*recorded result*, not a reason to refuse the run: the report lists those.

What the numbers mean is fixed by the non-claims below, which are copied verbatim
into the report. In particular the report states differences from the 2026-07-26
record and never attributes one to a cause: code, model revisions, the runtime and
the hardware are not controlled between the two.

Optional, newer run directories (D8-02) add per-segment files: ``grounded/r<k>/segment.json``
(which Ollama image tag served segment k), ``ollama-runtime.json``, and a content-free
``diagnostics`` block per case in ``results-*.json`` (why a case failed, token counts,
prompt and output hashes), plus ``runner.cpu`` in ``ENVIRONMENT.json``. A directory without
them (the D8-01 runs) validates and renders as before. Nothing the model or a server wrote
as free text is ever read here: ``diagnostics-*.json`` and ``ollama-server.log`` are not
opened, and every string that reaches the report is a number, a hash, or matches a closed
set or a strict pattern, else it is shown as ``other``.

``--expected-repeats`` counts segments (tags x repeats per tag) when several Ollama image
tags are measured inside one job.

``--emit`` prints every file of the run directory into the job log so the run can be
cross-checked from the log alone (see ``evals.d8_recover``). The block format is:

    D8-FILE-BEGIN <relative path> <sha256 hex> <byte count>
    <the file's bytes, decoded as UTF-8, exactly as stored>
    <one newline, always>
    D8-FILE-END <relative path>

The newline before the END marker is added unconditionally, so the END marker is on
its own line even when the file does not end with a newline; the reader drops exactly
that one newline. The reader consumes exactly <byte count> bytes, so a content line
that looks like a marker cannot end a block early. After the last block one
``D8-INDEX <relative path> <sha256 hex> <byte count>`` line per file is printed.

Standard library only, so it also runs with plain ``python3`` on a runner host.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO

SCHEMA_VERSION = 1

EVALS_DIR = Path(__file__).resolve().parent
DATA_DIR = EVALS_DIR / "data"
#: The committed 2026-07-26 record. Read-only; resolved from this file so it also
#: works inside the api image, where there is no repository root above ``evals``.
DEFAULT_BASELINE_DIR = EVALS_DIR / "results"

EXPECTED_EMBEDDING_PROVIDER = "sentence-transformers"
EXPECTED_EMBEDDING_MODEL = "intfloat/multilingual-e5-small"
#: The embedding column is fixed at vector(384); another width would need a migration.
EXPECTED_EMBEDDING_DIMENSION = 384
BASELINE_DATE = "2026-07-26"
RETRIEVAL_MODES = ("dense", "lexical", "hybrid")

#: DESIGN section 6, verbatim. Do not reword.
NON_CLAIMS: tuple[str, ...] = (
    "Synthetic corpora only: 26 claims / 19 queries (retrieval), 23 claims / 16 cases "
    "(grounded). These are regression measurements of this pipeline, not benchmarks.",
    # D8-02: names the model the run used ("{model}" is replaced, see ``non_claims``).
    "One embedding model and one local LLM ({model}), on a CPU runner. Nothing here ranks "
    "models or says the system handles Korean patents well.",
    "The oracle tier measures the pipeline, not a language model.",
    "Guardrail refusals are measured only against scripted output.",
    "Citation resolution shows that a quote is the stored text at its locator. It is not "
    "semantic entailment, and no output is a legal determination (infringement, validity, "
    "novelty, equivalence, inventive step, patentability).",
    "Real public documents and description retrieval were not measured.",
)

MODEL_PATTERN = re.compile(r"^[A-Za-z0-9._:/-]{1,128}$")


def non_claims(model: str | None) -> list[str]:
    """``NON_CLAIMS`` with the second sentence naming the (validated) model the run used.

    ``model`` is None when the LLM tier did not run; the sentence then says so.
    """
    if model is None:
        shown = "none: the LLM tier was not run"
    else:
        shown = f"`{model if MODEL_PATTERN.fullmatch(model) else 'other'}`"
    return [sentence.replace("{model}", shown) for sentence in NON_CLAIMS]


#: ``GroundedViolation`` values (claimtrace_api.grounding.validation), copied so this tool
#: stays standard-library only; a unit test asserts the copy equals the enum.
GROUNDED_VIOLATIONS: tuple[str, ...] = (
    "unknown_evidence_id",
    "malformed_evidence_id",
    "uncited_statement",
    "empty_statement",
    "no_supported_statements",
    "contradictory_insufficiency",
    "too_many_statements",
    "statement_too_long",
    "too_many_evidence_ids",
)
DIAGNOSTIC_OUTCOMES = ("accepted", "rejected", "provider_error", "not_validated")
DIAGNOSTICS_SCHEMA_VERSION = 1
SEGMENT_SCHEMA_VERSION = 1
RUNTIME_SCHEMA_VERSION = 1

#: An Ollama image tag, as the workflow validates it.
TAG_PATTERN = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._-]{0,63}$")
#: A lower-case code written by a server (done_reason, an error code).
CODE_PATTERN = re.compile(r"^[a-z_]{1,32}$")
HEX64_PATTERN = re.compile(r"^[0-9a-f]{64}$")
CPU_NAME_PATTERN = re.compile(r"^[A-Za-z0-9 ()@.,_+-]{1,96}$")
#: Short, plain facts (kernel, image version, microcode, cache size, an Ollama version).
SHORT_FACT_PATTERN = re.compile(r"^[A-Za-z0-9 ._:+()-]{1,64}$")
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9._:@/+-]{1,200}$")
TIMESTAMP_PATTERN = re.compile(r"^[0-9TZ:.+-]{10,40}$")
CPU_FLAGS_SELECTED = (
    "sse4_2",
    "avx",
    "avx2",
    "fma",
    "f16c",
    "avx512f",
    "avx512bw",
    "avx512vl",
    "avx512_vnni",
    "avx512_bf16",
    "avx512_fp16",
    "avx_vnni",
    "amx_tile",
    "amx_bf16",
    "amx_int8",
)
#: A version effect is "shown" only if every version pair beats the largest repeat pair by
#: at least this many cases on the raw-output-hash measure. Fixed before any run.
VERSION_EFFECT_MARGIN = 4

ENVIRONMENT_REQUIRED_KEYS = (
    "git_sha",
    "run_id",
    "run_attempt",
    "event_name",
    "runner",
    "api_image_id",
    "ollama_image_digest",
    "ollama_version",
    "ollama_model",
    "ollama_model_id",
    "embedding_model",
    "embedding_model_revision",
)
ENVIRONMENT_RUNNER_KEYS = ("nproc", "mem_total_mb", "os")
#: May be null only when the LLM tier was skipped (``--expected-repeats 0``).
ENVIRONMENT_OLLAMA_KEYS = (
    "ollama_image_digest",
    "ollama_version",
    "ollama_model",
    "ollama_model_id",
)
#: May be null; the report then carries a warning.
ENVIRONMENT_OPTIONAL_KEYS = ("embedding_model_revision",)

RETRIEVAL_METRIC_KEYS = (
    "recall_at_1",
    "recall_at_3",
    "recall_at_5",
    "mrr_at_10",
    "empty_query_hit_rate",
)
GROUNDED_METRIC_KEYS = (
    "case_count",
    "structured_output_rate",
    "answerability_accuracy",
    "insufficient_precision",
    "insufficient_recall",
    "evidence_id_validity_rate",
    "citation_resolution_rate",
    "statement_citation_coverage",
    "selection_precision",
    "selection_recall",
    "end_to_end_success_rate",
    "forbidden_citation_count",
    "mean_duration_seconds",
)
GROUNDED_CASE_KEYS = (
    "id",
    "status",
    "error_code",
    "cited",
    "expected",
    "forbidden_cited",
    "selection_recall",
    "end_to_end_success",
)
G01_PREFIX = "g01-"
G16_PREFIX = "g16-"

_REPEAT_DIR = re.compile(r"^r(\d+)$")


class RunRefused(Exception):
    """The run is not trustworthy; ``reasons`` has one line per violation."""

    def __init__(self, reasons: list[str]) -> None:
        super().__init__("; ".join(reasons))
        self.reasons = reasons


# -- expected shapes, derived from the committed datasets --------------------


def _expected_counts() -> dict[str, Any]:
    """Counts and ids the committed datasets imply.

    Derived from ``evals/data`` rather than hard-coded, so a dataset change cannot
    leave this tool validating against stale numbers.
    """

    def load(name: str) -> dict[str, Any]:
        loaded: dict[str, Any] = json.loads((DATA_DIR / name).read_text(encoding="utf-8"))
        return loaded

    retrieval_docs = load("corpus.json")["documents"]
    queries = load("queries.json")["queries"]
    grounded_docs = load("grounded_corpus.json")["documents"]
    cases = load("grounded_cases.json")["cases"]
    return {
        "retrieval": {
            "documents": len(retrieval_docs),
            "claims": sum(len(doc["claims"]) for doc in retrieval_docs),
            "queries": len(queries),
        },
        "grounded": {
            "documents": len(grounded_docs),
            "claims": sum(len(doc["claims"]) for doc in grounded_docs),
            "cases": len(cases),
            "case_ids": [case["id"] for case in cases],
        },
    }


# -- reading -----------------------------------------------------------------


def _read_json(path: Path, label: str, violations: list[str]) -> dict[str, Any] | None:
    if not path.is_file():
        violations.append(f"{label}: file is missing ({path})")
        return None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        violations.append(f"{label}: unreadable or truncated JSON ({error})")
        return None
    if not isinstance(loaded, dict):
        violations.append(f"{label}: top level is not a JSON object")
        return None
    return loaded


def _get(obj: Any, *keys: str) -> Any:
    """Nested lookup that yields None instead of raising on a wrong shape."""
    current = obj
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


# -- validation --------------------------------------------------------------


def _check_profile(profile: Any, label: str, violations: list[str]) -> None:
    if not isinstance(profile, dict):
        violations.append(f"{label}: embedding profile is missing")
        return
    provider = profile.get("embedding_provider")
    if provider != EXPECTED_EMBEDDING_PROVIDER:
        violations.append(
            f"{label}: embedding_provider is {provider!r}, expected {EXPECTED_EMBEDDING_PROVIDER!r}"
        )
    model = profile.get("embedding_model")
    if model != EXPECTED_EMBEDDING_MODEL:
        violations.append(
            f"{label}: embedding_model is {model!r}, expected {EXPECTED_EMBEDDING_MODEL!r}"
        )
    dimension = profile.get("embedding_dimension")
    if dimension != EXPECTED_EMBEDDING_DIMENSION:
        violations.append(
            f"{label}: embedding_dimension is {dimension!r}, "
            f"expected {EXPECTED_EMBEDDING_DIMENSION}"
        )


def _check_count(actual: Any, expected: int, what: str, label: str, violations: list[str]) -> None:
    if actual != expected:
        violations.append(f"{label}: {what} is {actual!r}, expected {expected}")


def _validate_retrieval(
    payload: dict[str, Any], expected: dict[str, int], violations: list[str]
) -> None:
    label = "retrieval/results.json"
    _check_profile(payload.get("profile"), label, violations)
    for key in ("documents", "claims", "queries"):
        _check_count(
            _get(payload, "corpus", key), expected[key], f"corpus.{key}", label, violations
        )
    metrics = payload.get("metrics")
    if not isinstance(metrics, dict):
        violations.append(f"{label}: metrics are missing")
        return
    for mode in RETRIEVAL_MODES:
        entry = metrics.get(mode)
        if not isinstance(entry, dict):
            violations.append(f"{label}: metrics for mode {mode!r} are missing")
            continue
        _check_count(
            entry.get("query_count"), expected["queries"], f"{mode}.query_count", label, violations
        )
        for key in RETRIEVAL_METRIC_KEYS:
            if not _is_number(entry.get(key)):
                violations.append(f"{label}: {mode}.{key} is missing or not a number")
    per_query = payload.get("per_query")
    wanted = expected["queries"] * len(RETRIEVAL_MODES)
    if not isinstance(per_query, list) or len(per_query) != wanted:
        count = len(per_query) if isinstance(per_query, list) else None
        violations.append(f"{label}: per_query has {count!r} rows, expected {wanted}")


def _validate_grounded(
    payload: dict[str, Any],
    *,
    tier: str,
    label: str,
    expected: dict[str, Any],
    expected_model: str | None,
    violations: list[str],
) -> None:
    if payload.get("tier") != tier:
        violations.append(f"{label}: tier is {payload.get('tier')!r}, expected {tier!r}")
    provider = payload.get("provider")
    if not isinstance(provider, dict):
        violations.append(f"{label}: provider facts are missing")
        provider = {}
    if tier == "deterministic":
        if provider.get("provider") != "oracle":
            violations.append(
                f"{label}: provider is {provider.get('provider')!r}, expected 'oracle'"
            )
    else:
        if provider.get("provider") != "ollama":
            violations.append(
                f"{label}: provider is {provider.get('provider')!r}, expected 'ollama'"
            )
        if provider.get("model") != expected_model:
            violations.append(
                f"{label}: model is {provider.get('model')!r}, expected {expected_model!r}"
            )
    for flag in ("available", "model_available"):
        if provider.get(flag) is not True:
            violations.append(f"{label}: provider {flag} is {provider.get(flag)!r}, expected true")

    _check_profile(_get(payload, "corpus", "retrieval_profile"), label, violations)
    for key in ("documents", "claims", "cases"):
        _check_count(
            _get(payload, "corpus", key), expected[key], f"corpus.{key}", label, violations
        )

    metrics = payload.get("metrics")
    if not isinstance(metrics, dict):
        violations.append(f"{label}: metrics are missing")
    else:
        _check_count(
            metrics.get("case_count"), expected["cases"], "metrics.case_count", label, violations
        )
        for key in GROUNDED_METRIC_KEYS:
            if not _is_number(metrics.get(key)):
                violations.append(f"{label}: metrics.{key} is missing or not a number")

    per_case = payload.get("per_case")
    if not isinstance(per_case, list):
        violations.append(f"{label}: per_case is missing")
    else:
        ids = [entry.get("id") if isinstance(entry, dict) else None for entry in per_case]
        if ids != expected["case_ids"]:
            violations.append(
                f"{label}: per_case ids differ from the committed cases "
                f"({len(ids)} rows, expected {expected['cases']})"
            )
        for entry in per_case:
            if isinstance(entry, dict):
                missing = [key for key in GROUNDED_CASE_KEYS if key not in entry]
                if missing:
                    violations.append(f"{label}: case {entry.get('id')!r} lacks {missing}")
                    break
        for prefix in (G01_PREFIX, G16_PREFIX):
            matching = [i for i in ids if isinstance(i, str) and i.startswith(prefix)]
            if len(matching) != 1:
                violations.append(f"{label}: expected exactly one case starting {prefix!r}")

    guardrails = payload.get("guardrails")
    if not isinstance(guardrails, list):
        violations.append(f"{label}: guardrails are missing")
    elif tier == "deterministic":
        if not guardrails:
            violations.append(f"{label}: the oracle tier recorded no guardrail outcomes")
        for entry in guardrails:
            if not isinstance(entry, dict) or not {"name", "status", "refused"} <= set(entry):
                violations.append(f"{label}: a guardrail entry is malformed")
                break
    elif guardrails:
        violations.append(f"{label}: an LLM file must not carry guardrail outcomes")


def _guardrail_names(payload: dict[str, Any]) -> list[Any]:
    guardrails = payload.get("guardrails")
    if not isinstance(guardrails, list):
        return []
    return [g.get("name") if isinstance(g, dict) else None for g in guardrails]


def _validate_guardrail_names(
    oracle: dict[str, Any], base_oracle: dict[str, Any], label: str, violations: list[str]
) -> None:
    """The oracle tier must report exactly the guardrail payloads of the committed baseline."""
    if not isinstance(oracle.get("guardrails"), list) or not oracle["guardrails"]:
        return  # already reported by _validate_grounded
    got, wanted = _guardrail_names(oracle), _guardrail_names(base_oracle)
    if got != wanted:
        violations.append(f"{label}: guardrail names {got} differ from the baseline's {wanted}")


def _validate_environment(
    env: dict[str, Any], expected_model: str, repeats: int, violations: list[str]
) -> list[str]:
    """Check ENVIRONMENT.json; return the warnings that go into the report."""
    label = "ENVIRONMENT.json"
    warnings: list[str] = []
    for key in ENVIRONMENT_REQUIRED_KEYS:
        if key not in env:
            violations.append(f"{label}: field {key!r} is missing")
            continue
        value = env[key]
        if value is None or value == "":
            if key in ENVIRONMENT_OPTIONAL_KEYS:
                warnings.append(
                    f"{key} was not recorded; the embedding model revision cannot be stated."
                )
            elif key in ENVIRONMENT_OLLAMA_KEYS and repeats == 0:
                continue
            else:
                violations.append(f"{label}: field {key!r} is empty")
    runner = env.get("runner")
    if "runner" in env and not isinstance(runner, dict):
        violations.append(f"{label}: field 'runner' is not an object")
    elif isinstance(runner, dict):
        for key in ENVIRONMENT_RUNNER_KEYS:
            if runner.get(key) in (None, ""):
                violations.append(f"{label}: runner.{key} is missing or empty")
    embedding_model = env.get("embedding_model")
    if embedding_model not in (None, "") and embedding_model != EXPECTED_EMBEDDING_MODEL:
        violations.append(
            f"{label}: embedding_model is {embedding_model!r}, expected "
            f"{EXPECTED_EMBEDDING_MODEL!r}"
        )
    if repeats > 0 and env.get("ollama_model") not in (None, "", expected_model):
        violations.append(
            f"{label}: ollama_model is {env.get('ollama_model')!r}, expected {expected_model!r}"
        )
    return warnings


def _validate_segment_set(
    segments: list[Segment], run_dir: Path, env: dict[str, Any] | None, violations: list[str]
) -> None:
    """Segment files are all-or-nothing and their repeat indexes must count per tag."""
    for segment in segments:
        log_dir = run_dir / "grounded" / f"r{segment.number}"
        if (log_dir / "segment.json").is_file() and segment.meta is None:
            return  # already reported; the checks below would only repeat it
    with_meta = [s for s in segments if s.meta is not None]
    if not with_meta:
        return
    if len(with_meta) != len(segments):
        violations.append("grounded: segment.json is present for only some of the segments")
        return
    seen: dict[str, int] = {}
    for segment in segments:
        tag = str(segment.tag)
        seen[tag] = seen.get(tag, 0) + 1
        if segment.repeat_index != seen[tag]:
            violations.append(
                f"grounded/r{segment.number}/segment.json: repeat_index is "
                f"{segment.repeat_index}, expected {seen[tag]} for tag {tag!r}"
            )
    runtimes = (env or {}).get("ollama_runtimes")
    if isinstance(runtimes, list):
        recorded = [r.get("tag") for r in runtimes if isinstance(r, dict)]
        if recorded != list(seen):
            violations.append(
                f"ENVIRONMENT.json: ollama_runtimes tags {recorded} differ from the "
                f"segments' {list(seen)}"
            )


def _validate_baseline(
    retrieval: dict[str, Any] | None,
    oracle: dict[str, Any] | None,
    llm: dict[str, Any] | None,
    violations: list[str],
) -> None:
    """The baseline is committed and read-only; check only that it can be compared."""
    for label, payload in (
        ("baseline retrieval/results.json", retrieval),
        ("baseline grounded/results-deterministic.json", oracle),
        ("baseline grounded/results-ollama.json", llm),
    ):
        if payload is None:
            continue
        generated = str(payload.get("generated_at", ""))
        if not generated.startswith(BASELINE_DATE):
            violations.append(f"{label}: generated_at {generated!r} is not from {BASELINE_DATE}")
        if not isinstance(payload.get("metrics"), dict):
            violations.append(f"{label}: metrics are missing")
    for label, payload in (
        ("baseline grounded/results-deterministic.json", oracle),
        ("baseline grounded/results-ollama.json", llm),
    ):
        if payload is not None and not isinstance(payload.get("per_case"), list):
            violations.append(f"{label}: per_case is missing")


# -- optional D8-02 facts: segments, diagnostics, machine ----------------------


def _safe(value: Any, pattern: re.Pattern[str]) -> str | None:
    """``value`` if it fully matches ``pattern``; ``None`` for None; otherwise ``other``."""
    if value is None:
        return None
    if isinstance(value, str) and pattern.fullmatch(value):
        return value
    return "other"


def _count(value: Any) -> int | None:
    """A non-negative int, else None (a bool is not a count)."""
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _is_count_or_null(value: Any) -> bool:
    return value is None or _count(value) is not None


def _is_measure_or_null(value: Any) -> bool:
    return value is None or (_is_number(value) and value >= 0)


def _is_hash_or_null(value: Any) -> bool:
    return value is None or (isinstance(value, str) and HEX64_PATTERN.fullmatch(value) is not None)


_ATTEMPT_COUNT_KEYS = (
    "http_calls",
    "prompt_eval_count",
    "eval_count",
    "prompt_characters",
    "response_characters",
    "num_predict",
)
_ATTEMPT_MEASURE_KEYS = (
    "total_ms",
    "load_ms",
    "prompt_eval_ms",
    "eval_ms",
    "wall_seconds",
    "temperature",
)


def _diagnostics_problem(diag: Any) -> str | None:
    """Why a per-case ``diagnostics`` block is malformed, or ``None`` when it is well formed."""
    if not isinstance(diag, dict):
        return "diagnostics is not an object"
    if diag.get("schema_version") != DIAGNOSTICS_SCHEMA_VERSION:
        return f"diagnostics.schema_version is not {DIAGNOSTICS_SCHEMA_VERSION}"
    attempts = diag.get("attempts")
    if not isinstance(attempts, list) or len(attempts) > 2:
        return "diagnostics.attempts is not a list of at most 2 entries"
    if not isinstance(diag.get("repair_used"), bool):
        return "diagnostics.repair_used is not a boolean"
    if not isinstance(diag.get("catalog"), list):
        return "diagnostics.catalog is not a list"
    for position, attempt in enumerate(attempts):
        if not isinstance(attempt, dict):
            return f"diagnostics.attempts[{position}] is not an object"
        if attempt.get("attempt") != position:
            return f"diagnostics.attempts[{position}].attempt is not {position}"
        if attempt.get("outcome") not in DIAGNOSTIC_OUTCOMES:
            return f"diagnostics.attempts[{position}].outcome is outside the closed set"
        violation = attempt.get("violation")
        if violation is not None and violation not in GROUNDED_VIOLATIONS:
            return f"diagnostics.attempts[{position}].violation is outside the closed set"
        for key in _ATTEMPT_COUNT_KEYS:
            if not _is_count_or_null(attempt.get(key)):
                return f"diagnostics.attempts[{position}].{key} is not a non-negative int or null"
        for key in _ATTEMPT_MEASURE_KEYS:
            if not _is_measure_or_null(attempt.get(key)):
                return f"diagnostics.attempts[{position}].{key} is not a non-negative number"
        for key in ("prompt_sha256", "raw_output_sha256"):
            if not _is_hash_or_null(attempt.get(key)):
                return f"diagnostics.attempts[{position}].{key} is not a sha256 or null"
        for key in ("done_reason", "provider_error_code"):
            if attempt.get(key) is not None and not isinstance(attempt.get(key), str):
                return f"diagnostics.attempts[{position}].{key} is not a string or null"
    return None


def _validate_case_diagnostics(payload: dict[str, Any], label: str, violations: list[str]) -> bool:
    """Validate the optional per-case diagnostics of one grounded file.

    Returns whether the file carries diagnostics. They are all-or-nothing: a file in which
    only some cases have them is refused.
    """
    cases = payload.get("per_case")
    if not isinstance(cases, list):
        return False
    with_diag = [c for c in cases if isinstance(c, dict) and "diagnostics" in c]
    if not with_diag:
        return False
    if len(with_diag) != len(cases):
        violations.append(f"{label}: diagnostics are present for only some of the cases")
    for case in with_diag:
        problem = _diagnostics_problem(case["diagnostics"])
        if problem:
            violations.append(f"{label}: case {case.get('id')!r}: {problem}")
            break
    return True


def _validate_segment_meta(meta: Any, number: int, label: str, violations: list[str]) -> None:
    if not isinstance(meta, dict):
        violations.append(f"{label}: top level is not a JSON object")
        return
    if meta.get("schema_version") != SEGMENT_SCHEMA_VERSION:
        violations.append(f"{label}: schema_version is not {SEGMENT_SCHEMA_VERSION}")
    if meta.get("segment") != number:
        violations.append(f"{label}: segment is {meta.get('segment')!r}, expected {number}")
    tag = meta.get("ollama_image_tag")
    if not isinstance(tag, str) or not TAG_PATTERN.fullmatch(tag):
        violations.append(f"{label}: ollama_image_tag is missing or not a valid tag")
    if _count(meta.get("repeat_index")) is None or meta.get("repeat_index") == 0:
        violations.append(f"{label}: repeat_index is not a positive int")
    setting = meta.get("context_length_setting")
    if setting is not None and _count(setting) is None:
        violations.append(f"{label}: context_length_setting is not a non-negative int or null")
    for key in ("ollama_image_digest", "ollama_version", "started_at", "finished_at"):
        if meta.get(key) is not None and not isinstance(meta.get(key), str):
            violations.append(f"{label}: {key} is not a string or null")


def _validate_runtime(runtime: Any, label: str, violations: list[str]) -> None:
    if not isinstance(runtime, dict):
        violations.append(f"{label}: top level is not a JSON object")
        return
    if runtime.get("schema_version") != RUNTIME_SCHEMA_VERSION:
        violations.append(f"{label}: schema_version is not {RUNTIME_SCHEMA_VERSION}")
    ps = runtime.get("ps")
    if ps is not None and (not isinstance(ps, list) or not all(isinstance(e, dict) for e in ps)):
        violations.append(f"{label}: ps is not a list of objects or null")
    show = runtime.get("show")
    if show is not None and not isinstance(show, dict):
        violations.append(f"{label}: show is not an object or null")


@dataclass
class Segment:
    """One run of the 16 LLM cases: ``grounded/r<number>`` (D8-01 calls it a repeat)."""

    number: int
    payload: dict[str, Any]
    meta: dict[str, Any] | None = None
    runtime: dict[str, Any] | None = None
    has_diagnostics: bool = False

    @property
    def tag(self) -> str | None:
        return None if self.meta is None else str(self.meta["ollama_image_tag"])

    @property
    def repeat_index(self) -> int | None:
        return None if self.meta is None else int(self.meta["repeat_index"])

    @property
    def label(self) -> str:
        return f"r{self.number}" if self.tag is None else f"r{self.number} ({self.tag})"

    def attempts(self, case: dict[str, Any]) -> list[dict[str, Any]]:
        diag = case.get("diagnostics")
        return list(diag["attempts"]) if isinstance(diag, dict) else []

    @property
    def context_length(self) -> int | None:
        """The context length the server reported using (``/api/ps``), if it did."""
        for entry in _get(self.runtime, "ps") or []:
            value = _count(entry.get("context_length"))
            if value:
                return value
        return None


def _read_optional_json(
    path: Path, label: str, violations: list[str], validate: Any, *args: Any
) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    loaded = _read_json(path, label, violations)
    if loaded is None:
        return None
    count = len(violations)
    validate(loaded, *args, label, violations)
    return loaded if len(violations) == count else None


def _validate_environment_extras(env: dict[str, Any], violations: list[str]) -> None:
    """Optional D8-02 ENVIRONMENT.json keys; absent keys are fine."""
    label = "ENVIRONMENT.json"
    tag = env.get("ollama_image_tag")
    if tag is not None and (not isinstance(tag, str) or not TAG_PATTERN.fullmatch(tag)):
        violations.append(f"{label}: ollama_image_tag is not a valid tag")
    setting = env.get("ollama_context_length_setting")
    if setting is not None and _count(setting) is None:
        violations.append(f"{label}: ollama_context_length_setting is not an int or null")
    captured = env.get("diagnostics_captured")
    if captured is not None and not isinstance(captured, bool):
        violations.append(f"{label}: diagnostics_captured is not a boolean")
    runtimes = env.get("ollama_runtimes")
    valid_runtimes = isinstance(runtimes, list) and all(
        isinstance(r, dict) and isinstance(r.get("tag"), str) and TAG_PATTERN.fullmatch(r["tag"])
        for r in runtimes
    )
    if runtimes is not None and not valid_runtimes:
        violations.append(f"{label}: ollama_runtimes is not a list of entries with a valid tag")
    runner = env.get("runner")
    cpu = runner.get("cpu") if isinstance(runner, dict) else None
    if cpu is not None and not isinstance(cpu, dict):
        violations.append(f"{label}: runner.cpu is not an object or null")


def _machine_block(env: dict[str, Any]) -> dict[str, Any] | None:
    """The CPU and host facts, reduced to values that are safe to print."""
    runner = env.get("runner")
    if not isinstance(runner, dict):
        return None
    cpu = runner.get("cpu")
    kernel, image_os, image_version = (
        runner.get(key) for key in ("kernel", "image_os", "image_version")
    )
    if not isinstance(cpu, dict) and kernel is None and image_version is None:
        return None
    cpu = cpu if isinstance(cpu, dict) else {}

    def short(key: str) -> Any:
        value = cpu.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        return _safe(value, SHORT_FACT_PATTERN)

    flags = cpu.get("flags_selected")
    selected = (
        [flag for flag in CPU_FLAGS_SELECTED if flag in flags] if isinstance(flags, list) else None
    )
    flags_sha = cpu.get("flags_sha256")
    fingerprint = cpu.get("cpu_fingerprint")
    return {
        "model_name": _safe(cpu.get("model_name"), CPU_NAME_PATTERN),
        "vendor_id": _safe(cpu.get("vendor_id"), SHORT_FACT_PATTERN),
        "cpu_family": short("cpu_family"),
        "model": short("model"),
        "stepping": short("stepping"),
        "microcode": short("microcode"),
        "cpu_cores": short("cpu_cores"),
        "siblings": short("siblings"),
        "cache_size": short("cache_size"),
        "flags_selected": selected,
        "flags_sha256": flags_sha if _is_hash_or_null(flags_sha) else "other",
        "cpu_fingerprint": fingerprint if _is_hash_or_null(fingerprint) else "other",
        "kernel": _safe(kernel, SHORT_FACT_PATTERN),
        "image_os": _safe(image_os, SHORT_FACT_PATTERN),
        "image_version": _safe(image_version, SHORT_FACT_PATTERN),
    }


def _public_environment(env: dict[str, Any]) -> dict[str, Any]:
    """``env`` as it goes into the summary: free-text machine facts replaced by safe values."""
    public = copy.deepcopy(env)
    runner = public.get("runner")
    if isinstance(runner, dict):
        machine = _machine_block(env)
        if machine is not None:
            runner.pop("cpu", None)
            for key in ("kernel", "image_os", "image_version"):
                runner.pop(key, None)
            if any(value is not None for value in machine.values()):
                runner["machine"] = machine
    runtimes = env.get("ollama_runtimes")
    if isinstance(runtimes, list):
        public["ollama_runtimes"] = [
            {
                "tag": item.get("tag"),
                "digest": _safe(item.get("digest"), IDENTIFIER_PATTERN),
                "version": _safe(item.get("version"), SHORT_FACT_PATTERN),
            }
            for item in runtimes
        ]
    return public


# -- diagnostics analysis (counts and closed-set codes only) ---------------------


def _by_id(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(c["id"]): c for c in payload["per_case"]}


def _segment_diagnostics(segment: Segment) -> dict[str, Any]:
    """Why this segment's cases failed, and how close its attempts came to the context."""
    failed: list[dict[str, Any]] = []
    rejections: dict[str, dict[str, int]] = {"attempt_0": {}, "attempt_1": {}}
    repaired_200 = 0
    max_total = max_prompt = length_stops = at_or_over = 0
    context = segment.context_length
    for case in segment.payload["per_case"]:
        attempts = segment.attempts(case)
        if case["status"] == 200 and case["diagnostics"].get("repair_used") is True:
            repaired_200 += 1
        for attempt in attempts:
            key = f"attempt_{attempt['attempt']}"
            if attempt["outcome"] != "accepted":
                name = attempt["violation"] or attempt["outcome"]
                rejections[key][name] = rejections[key].get(name, 0) + 1
            prompt, output = attempt.get("prompt_eval_count"), attempt.get("eval_count")
            if prompt is not None:
                max_prompt = max(max_prompt, prompt)
            if prompt is not None and output is not None:
                max_total = max(max_total, prompt + output)
                if context and prompt + output >= context:
                    at_or_over += 1
            if attempt.get("done_reason") == "length":
                length_stops += 1
        if case["status"] != 200:
            failed.append(
                {
                    "id": case["id"],
                    "status": case["status"],
                    "error_code": case["error_code"],
                    "repair_attempted": len(attempts) > 1,
                    "attempts": [
                        {
                            "attempt": a["attempt"],
                            "outcome": a["outcome"],
                            "violation": a["violation"],
                            "provider_error_code": _safe(
                                a.get("provider_error_code"), CODE_PATTERN
                            ),
                            "done_reason": _safe(a.get("done_reason"), CODE_PATTERN),
                            "prompt_eval_count": a.get("prompt_eval_count"),
                            "eval_count": a.get("eval_count"),
                            "wall_seconds": a.get("wall_seconds"),
                        }
                        for a in attempts
                    ],
                }
            )
    return {
        "segment": segment.number,
        "ollama_image_tag": segment.tag,
        "failed_cases": failed,
        "rejections_by_rule": rejections,
        "repaired_200_cases": repaired_200,
        "tokens": {
            "max_prompt_plus_output": max_total,
            "max_prompt": max_prompt,
            "context_length_in_use": context,
            "attempts_done_reason_length": length_stops,
            "attempts_at_or_over_context": at_or_over,
        },
    }


def _first_attempt(segment_or_payload: dict[str, Any], case_id: str) -> dict[str, Any] | None:
    case = _by_id(segment_or_payload).get(case_id)
    attempts = case.get("diagnostics", {}).get("attempts") if case else None
    return attempts[0] if attempts else None


def _same_evidence(oracle: dict[str, Any], segments: list[Segment]) -> dict[str, Any]:
    """Per segment, the cases whose first-attempt prompt differs from the oracle tier's."""
    out: dict[str, Any] = {}
    for segment in segments:
        differing, missing = [], []
        for case in oracle["per_case"]:
            ours = _first_attempt(oracle, str(case["id"]))
            theirs = _first_attempt(segment.payload, str(case["id"]))
            a = ours.get("prompt_sha256") if ours else None
            b = theirs.get("prompt_sha256") if theirs else None
            if a is None or b is None:
                missing.append(case["id"])
            elif a != b:
                differing.append(case["id"])
        out[f"r{segment.number}"] = {"differing_cases": differing, "not_comparable": missing}
    return out


def _pair_counts(first: Segment, second: Segment) -> dict[str, Any]:
    a, b = _by_id(first.payload), _by_id(second.payload)
    outcome = status = raw = comparable = 0
    for case_id, case in a.items():
        other = b[case_id]
        outcome += case["end_to_end_success"] != other["end_to_end_success"]
        status += case["status"] != other["status"]
        x, y = _first_attempt(first.payload, case_id), _first_attempt(second.payload, case_id)
        hx = x.get("raw_output_sha256") if x else None
        hy = y.get("raw_output_sha256") if y else None
        if hx is not None and hy is not None:
            comparable += 1
            raw += hx != hy
    return {
        "segments": [first.number, second.number],
        "kind": "repeat pair" if first.tag == second.tag else "version pair",
        "tags": [first.tag, second.tag],
        "cases": len(a),
        "different_end_to_end_outcome": int(outcome),
        "different_status": int(status),
        "different_first_attempt_raw_output_hash": int(raw),
        "raw_output_hash_comparable_cases": comparable,
    }


def _contrasts(segments: list[Segment]) -> dict[str, Any]:
    """Every pair of segments, and the pre-registered version-effect rule applied to them."""
    pairs = [
        _pair_counts(first, second)
        for index, first in enumerate(segments)
        for second in segments[index + 1 :]
    ]
    repeat = [p for p in pairs if p["kind"] == "repeat pair"]
    version = [p for p in pairs if p["kind"] == "version pair"]
    key = "different_first_attempt_raw_output_hash"
    largest_repeat = max((p[key] for p in repeat), default=None)
    smallest_version = min((p[key] for p in version), default=None)
    if not version:
        verdict, reason = None, "this run has only one Ollama image tag"
    elif largest_repeat is None:
        verdict, reason = "not_shown", "no repeat pair to measure run-to-run variation against"
    elif any(p["raw_output_hash_comparable_cases"] != p["cases"] for p in pairs):
        verdict, reason = "not_shown", "first-attempt raw-output hashes are missing for some cases"
    elif all(p[key] >= largest_repeat + VERSION_EFFECT_MARGIN for p in version):
        verdict, reason = "shown", None
    else:
        verdict, reason = "not_shown", None
    return {
        "pairs": pairs,
        "rule": (
            "a version effect on this machine is shown when every version pair exceeds the "
            f"largest repeat-pair count by at least {VERSION_EFFECT_MARGIN} cases on the "
            "raw-output-hash measure; otherwise not shown"
        ),
        "largest_repeat_pair_count": largest_repeat,
        "smallest_version_pair_count": smallest_version,
        "version_effect": verdict,
        "reason": reason,
    }


def _diagnostics_summary(
    environment: dict[str, Any],
    oracle: dict[str, Any],
    oracle_has_diagnostics: bool,
    segments: list[Segment],
) -> dict[str, Any] | None:
    """Everything the new report sections show, or None for a run without any of it."""
    with_diag = [s for s in segments if s.has_diagnostics]
    has_meta = any(s.meta is not None or s.runtime is not None for s in segments)
    machine = _machine_block(environment)
    if not (with_diag or has_meta or machine):
        return None
    block: dict[str, Any] = {"schema_version": DIAGNOSTICS_SCHEMA_VERSION, "machine": machine}
    block["segments"] = [
        {
            "segment": s.number,
            "ollama_image_tag": s.tag,
            "repeat_index": s.repeat_index,
            "ollama_image_digest": _safe(
                (s.meta or {}).get("ollama_image_digest"), IDENTIFIER_PATTERN
            ),
            "ollama_version": _safe((s.meta or {}).get("ollama_version"), SHORT_FACT_PATTERN),
            "context_length_setting": _count((s.meta or {}).get("context_length_setting")),
            "started_at": _safe((s.meta or {}).get("started_at"), TIMESTAMP_PATTERN),
            "finished_at": _safe((s.meta or {}).get("finished_at"), TIMESTAMP_PATTERN),
            "runtime": _runtime_block(s),
        }
        for s in segments
        if s.meta is not None or s.runtime is not None
    ]
    block["m3"] = [_segment_diagnostics(s) for s in with_diag]
    if oracle_has_diagnostics and with_diag:
        block["same_evidence"] = _same_evidence(oracle, with_diag)
    block["contrasts"] = _contrasts(with_diag) if len(with_diag) > 1 else None
    return block


def _runtime_block(segment: Segment) -> dict[str, Any] | None:
    runtime = segment.runtime
    if runtime is None:
        return None
    ps = [e for e in runtime.get("ps") or [] if isinstance(e, dict)]
    first = ps[0] if ps else {}
    return {
        "api_version": _safe(runtime.get("api_version"), SHORT_FACT_PATTERN),
        "model_digest": _safe(first.get("digest"), IDENTIFIER_PATTERN),
        "context_length_in_use": segment.context_length,
        "model_context_length": _count(_get(runtime, "show", "context_length")),
    }


# -- summary -----------------------------------------------------------------


def _case(payload: dict[str, Any], prefix: str) -> dict[str, Any]:
    for entry in payload["per_case"]:
        if str(entry["id"]).startswith(prefix):
            return {key: entry.get(key) for key in GROUNDED_CASE_KEYS}
    return {}


def _failed_cases(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"id": c["id"], "status": c["status"], "error_code": c["error_code"]}
        for c in payload["per_case"]
        if c["status"] != 200 or c["error_code"] is not None
    ]


def _grounded_block(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "generated_at": payload.get("generated_at"),
        "provider": payload.get("provider"),
        "metrics": payload["metrics"],
        "per_case": [
            {
                "id": c["id"],
                "status": c["status"],
                "error_code": c["error_code"],
                "end_to_end_success": c["end_to_end_success"],
            }
            for c in payload["per_case"]
        ],
        "failed_cases": _failed_cases(payload),
        "g01": _case(payload, G01_PREFIX),
        "g16": _case(payload, G16_PREFIX),
    }


def _guardrail_block(payload: dict[str, Any]) -> dict[str, Any]:
    entries = payload.get("guardrails") or []
    return {
        "refused": sum(1 for entry in entries if entry.get("refused") is True),
        "total": len(entries),
        "entries": entries,
    }


def _retrieval_block(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "generated_at": payload.get("generated_at"),
        "corpus": payload.get("corpus"),
        "profile": payload.get("profile"),
        "modes": {mode: payload["metrics"][mode] for mode in RETRIEVAL_MODES},
    }


def _stability(repeats: list[dict[str, Any]]) -> dict[str, Any]:
    """How far the repeats agree, case by case. Measured, not assumed."""
    if len(repeats) < 2:
        return {"repeats": len(repeats), "computed": False, "reason": "fewer than two repeats"}
    by_repeat = [{c["id"]: c for c in block["per_case"]} for block in repeats]
    ids = [c["id"] for c in repeats[0]["per_case"]]
    differing = []
    for case_id in ids:
        outcomes = [r[case_id]["end_to_end_success"] for r in by_repeat]
        if len(set(outcomes)) > 1:
            differing.append({"id": case_id, "end_to_end_success_per_repeat": outcomes})
    return {
        "repeats": len(repeats),
        "computed": True,
        "case_count": len(ids),
        "identical_end_to_end_outcome": len(ids) - len(differing),
        "differing_cases": differing,
    }


def _build_summary(
    *,
    environment: dict[str, Any],
    warnings: list[str],
    expected_model: str,
    retrieval: dict[str, Any],
    oracle: dict[str, Any],
    oracle_has_diagnostics: bool,
    segments: list[Segment],
    base_retrieval: dict[str, Any],
    base_oracle: dict[str, Any],
    base_llm: dict[str, Any],
) -> dict[str, Any]:
    llm_blocks = []
    for segment in segments:
        block = _grounded_block(segment.payload)
        block["repeat"] = segment.number
        if segment.meta is not None:
            block["ollama_image_tag"] = segment.tag
            block["repeat_index"] = segment.repeat_index
        llm_blocks.append(block)
    summary: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "git_sha": environment["git_sha"],
        "run_id": environment["run_id"],
        "run_attempt": environment["run_attempt"],
        "environment": _public_environment(environment),
        "warnings": warnings,
        "expected_llm_model": expected_model,
        "expected_repeats": len(segments),
        "retrieval": _retrieval_block(retrieval),
        "grounded_oracle": {
            **_grounded_block(oracle),
            "guardrails": _guardrail_block(oracle),
        },
        "grounded_llm": llm_blocks,
        "stability": _stability(llm_blocks),
        "baseline_2026_07_26": {
            "retrieval": _retrieval_block(base_retrieval),
            "grounded_oracle": {
                **_grounded_block(base_oracle),
                "guardrails": _guardrail_block(base_oracle),
            },
            "grounded_llm": _grounded_block(base_llm),
        },
        "non_claims": non_claims(expected_model if segments else None),
    }
    tags = list(dict.fromkeys(s.tag for s in segments if s.tag is not None))
    if len(tags) > 1:
        summary["stability_by_tag"] = {
            tag: _stability([b for b in llm_blocks if b.get("ollama_image_tag") == tag])
            for tag in tags
        }
    diagnostics = _diagnostics_summary(environment, oracle, oracle_has_diagnostics, segments)
    if diagnostics is not None:
        summary["diagnostics"] = diagnostics
    return summary


# -- report ------------------------------------------------------------------


def _fmt(value: Any) -> str:
    """A value exactly as the input wrote it (no re-rounding)."""
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) if value else "-"
    return str(value)


def _table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(_fmt(cell) for cell in row) + " |" for row in rows]
    return lines


def _metric_table(keys: tuple[str, ...], columns: list[tuple[str, dict[str, Any]]]) -> list[str]:
    headers = ["metric"] + [name for name, _ in columns]
    rows = [[key] + [metrics.get(key) for _, metrics in columns] for key in keys]
    return _table(headers, rows)


def _case_table(case_blocks: list[tuple[str, dict[str, Any]]]) -> list[str]:
    headers = ["case", "status", "error_code", "cited", "expected", "forbidden_cited", "end_to_end"]
    rows = []
    for name, case in case_blocks:
        rows.append(
            [
                name,
                case.get("status"),
                case.get("error_code"),
                case.get("cited"),
                case.get("expected"),
                case.get("forbidden_cited"),
                case.get("end_to_end_success"),
            ]
        )
    return _table(["entry"] + headers[1:], rows)


def _run_label(run: dict[str, Any]) -> str:
    tag = run.get("ollama_image_tag")
    return f"r{run['repeat']}" if tag is None else f"r{run['repeat']} ({tag})"


def _render_report(summary: dict[str, Any]) -> str:
    base = summary["baseline_2026_07_26"]
    lines: list[str] = ["# D8 real-model measurement report", ""]
    lines += ["## Non-claims", ""]
    lines += [f"- {sentence}" for sentence in summary["non_claims"]]
    lines += [
        "",
        "## How to read this report",
        "",
        f"- Each table shows this run beside the committed {BASELINE_DATE} record. Values are "
        "copied as the input files wrote them.",
        "- Differences between the columns are stated only. No cause is attributed to any "
        "of them; the columns were produced by different runs and their conditions are not "
        "controlled against each other.",
        "- Every case is one question over a small synthetic corpus, so one case moves a "
        "rate by several points.",
        "",
    ]
    if summary["warnings"]:
        lines += ["## Warnings", ""] + [f"- {warning}" for warning in summary["warnings"]] + [""]

    env = summary["environment"]
    runner = env["runner"]
    lines += ["## Environment", ""]
    env_rows: list[list[Any]] = [
        ["git_sha", env["git_sha"]],
        [
            "run_id / attempt / event",
            f"{env['run_id']} / {env['run_attempt']} / {env['event_name']}",
        ],
        ["runner nproc", runner["nproc"]],
        ["runner mem_total_mb", runner["mem_total_mb"]],
        ["runner os", runner["os"]],
        ["api_image_id", env["api_image_id"]],
        ["embedding_model", env["embedding_model"]],
        ["embedding_model_revision", env["embedding_model_revision"]],
        ["ollama_image_digest", env["ollama_image_digest"]],
        ["ollama_version", env["ollama_version"]],
        ["ollama_model", env["ollama_model"]],
        ["ollama_model_id", env["ollama_model_id"]],
    ]
    for key, value in env.items():
        if key not in ENVIRONMENT_REQUIRED_KEYS and key != "ollama_runtimes":
            env_rows.append([key, value])
    lines += _table(["field", "value"], env_rows) + [""]
    lines += [f"Report generated at {summary['generated_at']}.", ""]
    diagnostics = summary.get("diagnostics")
    if diagnostics and diagnostics.get("machine"):
        lines += _render_machine(diagnostics["machine"])

    # M1
    retrieval = summary["retrieval"]
    counts = retrieval["corpus"]
    lines += [
        "## M1 Retrieval (real embeddings)",
        "",
        f"This run: {counts['documents']} documents, {counts['claims']} claims, "
        f"{counts['queries']} queries; baseline file generated "
        f"{base['retrieval']['generated_at']}.",
        "",
    ]
    rows: list[list[Any]] = []
    for mode in RETRIEVAL_MODES:
        for name, block in (("this run", retrieval), (BASELINE_DATE, base["retrieval"])):
            metrics = block["modes"][mode]
            rows.append([mode, name] + [metrics.get(key) for key in RETRIEVAL_METRIC_KEYS])
    lines += _table(["mode", "run", *RETRIEVAL_METRIC_KEYS], rows) + [""]

    # M2
    oracle = summary["grounded_oracle"]
    lines += [
        "## M2 Grounded pipeline, oracle tier "
        "(real embeddings, oracle in place of a language model)",
        "",
        "The oracle tier measures the pipeline, not a language model.",
        "",
    ]
    lines += _metric_table(
        GROUNDED_METRIC_KEYS,
        [("this run", oracle["metrics"]), (BASELINE_DATE, base["grounded_oracle"]["metrics"])],
    ) + [""]
    guard, base_guard = oracle["guardrails"], base["grounded_oracle"]["guardrails"]
    lines += [
        f"Guardrail payloads refused: {guard['refused']} of {guard['total']} "
        f"(baseline {base_guard['refused']} of {base_guard['total']}). "
        "Measured only against scripted output.",
        "",
    ]
    lines += _table(
        ["guardrail", "status", "error_code", "refused"],
        [
            [g.get("name"), g.get("status"), g.get("error_code"), g.get("refused")]
            for g in guard["entries"]
        ],
    ) + [""]
    lines += ["### g01 in the oracle tier", ""]
    lines += _case_table(
        [("this run", oracle["g01"]), (BASELINE_DATE, base["grounded_oracle"]["g01"])]
    ) + [""]

    # M3
    lines += ["## M3 Grounded generation, real local LLM", ""]
    llm_runs = summary["grounded_llm"]
    if not llm_runs:
        lines += ["The LLM tier was not run (expected repeats: 0).", ""]
    else:
        lines += [
            f"Expected model: `{summary['expected_llm_model']}`; repeats: {len(llm_runs)}. "
            f"Baseline model: `{base['grounded_llm']['provider'].get('model')}`.",
            "",
        ]
        columns = [(_run_label(run), run["metrics"]) for run in llm_runs]
        columns.append((BASELINE_DATE, base["grounded_llm"]["metrics"]))
        lines += _metric_table(GROUNDED_METRIC_KEYS, columns) + [""]
        for key, title in (("g01", "g01"), ("g16", "g16 (injection document in scope)")):
            lines += [f"### {title} per repeat", ""]
            lines += _case_table(
                [(_run_label(run), run[key]) for run in llm_runs]
                + [(BASELINE_DATE, base["grounded_llm"][key])]
            ) + [""]
        lines += ["### Cases that did not return a served answer", ""]
        failures = [
            [_run_label(run), f["id"], f["status"], f["error_code"]]
            for run in llm_runs
            for f in run["failed_cases"]
        ] + [
            [BASELINE_DATE, f["id"], f["status"], f["error_code"]]
            for f in base["grounded_llm"]["failed_cases"]
        ]
        if failures:
            lines += _table(["run", "case", "status", "error_code"], failures) + [""]
        else:
            lines += ["None.", ""]
        lines += ["### End-to-end outcome per case", ""]
        headers = ["case"] + [_run_label(run) for run in llm_runs] + [BASELINE_DATE]
        base_by_id = {c["id"]: c for c in base["grounded_llm"]["per_case"]}
        outcome_rows = []
        for position, case in enumerate(llm_runs[0]["per_case"]):
            row: list[Any] = [case["id"]]
            row += [run["per_case"][position]["end_to_end_success"] for run in llm_runs]
            row.append(base_by_id.get(case["id"], {}).get("end_to_end_success"))
            outcome_rows.append(row)
        lines += _table(headers, outcome_rows) + [""]

        lines += ["### Stability across repeats", ""]
        by_tag = summary.get("stability_by_tag")
        if by_tag:
            lines += [
                "Several Ollama image tags were measured in this run, so stability is stated "
                "within each tag; see the within-machine contrasts for differences between tags.",
                "",
            ]
            for tag, stability in by_tag.items():
                lines += _render_stability(stability, f"Tag `{tag}`: ")
        else:
            lines += _render_stability(summary["stability"], "")
    if diagnostics:
        lines += _render_diagnostics(diagnostics, summary)
    return "\n".join(lines).rstrip("\n") + "\n"


def _render_stability(stability: dict[str, Any], prefix: str) -> list[str]:
    if not stability["computed"]:
        return [f"{prefix}Not computed: {stability['reason']}.", ""]
    lines = [
        f"{prefix}{stability['identical_end_to_end_outcome']} of {stability['case_count']} cases "
        f"had the same end-to-end outcome in all {stability['repeats']} repeats "
        "(temperature 0, no seed).",
        "",
    ]
    if stability["differing_cases"]:
        lines += _table(
            ["case", "end_to_end per repeat"],
            [[d["id"], d["end_to_end_success_per_repeat"]] for d in stability["differing_cases"]],
        ) + [""]
    return lines


def _render_machine(machine: dict[str, Any]) -> list[str]:
    fingerprint = machine.get("cpu_fingerprint")
    rows: list[list[Any]] = [
        ["cpu model name", machine.get("model_name")],
        ["cpu fingerprint (first 12 hex)", fingerprint[:12] if fingerprint else None],
        ["cpu flags (selected)", machine.get("flags_selected")],
        ["kernel", machine.get("kernel")],
        ["runner image version", machine.get("image_version")],
    ]
    return ["## Machine", "", *_table(["field", "value"], rows), ""]


def _segment_name(entry: dict[str, Any]) -> str:
    tag = entry.get("ollama_image_tag")
    return f"r{entry['segment']}" if tag is None else f"r{entry['segment']} ({tag})"


def _render_diagnostics(diagnostics: dict[str, Any], summary: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    segments = diagnostics.get("segments", [])
    if segments:
        lines += ["## Ollama runtime", ""]
        rows = []
        for entry in segments:
            runtime = entry.get("runtime") or {}
            rows.append(
                [
                    f"r{entry['segment']}",
                    entry.get("ollama_image_tag"),
                    entry.get("ollama_image_digest"),
                    entry.get("ollama_version"),
                    runtime.get("api_version"),
                    runtime.get("model_digest"),
                    entry.get("context_length_setting"),
                    runtime.get("context_length_in_use"),
                    runtime.get("model_context_length"),
                ]
            )
        lines += _table(
            [
                "segment",
                "image tag",
                "image digest",
                "version",
                "api_version",
                "model digest",
                "context setting",
                "context in use",
                "model max context",
            ],
            rows,
        ) + [""]

    m3 = diagnostics.get("m3", [])
    if m3:
        names = {e["segment"]: _segment_name(e) for e in m3}
        lines += ["## Why M3 cases failed", ""]
        rows = []
        for entry in m3:
            for case in entry["failed_cases"]:
                attempts = case["attempts"]

                def per_attempt(key: str, attempts: list[dict[str, Any]] = attempts) -> str:
                    return " / ".join(_fmt(a.get(key)) for a in attempts) or "-"

                rows.append(
                    [
                        names[entry["segment"]],
                        case["id"],
                        case["status"],
                        case["error_code"],
                        per_attempt("violation") if attempts else "-",
                        "yes" if case["repair_attempted"] else "no",
                        per_attempt("done_reason"),
                        per_attempt("prompt_eval_count"),
                        per_attempt("eval_count"),
                        per_attempt("wall_seconds"),
                    ]
                )
        if rows:
            lines += _table(
                [
                    "segment",
                    "case",
                    "status",
                    "error_code",
                    "violation (attempt 0 / 1)",
                    "repair attempted",
                    "done_reason (0 / 1)",
                    "prompt tokens (0 / 1)",
                    "output tokens (0 / 1)",
                    "wall seconds (0 / 1)",
                ],
                rows,
            ) + [""]
        else:
            lines += ["No M3 case failed.", ""]

        lines += ["## Rejections by rule", ""]
        rules = sorted(
            {
                name
                for entry in m3
                for attempts in entry["rejections_by_rule"].values()
                for name in attempts
            }
        )
        if rules:
            headers = ["rule"] + [f"{names[e['segment']]} attempt {n}" for e in m3 for n in (0, 1)]
            rows = [
                [rule]
                + [e["rejections_by_rule"][f"attempt_{n}"].get(rule, 0) for e in m3 for n in (0, 1)]
                for rule in rules
            ]
            lines += _table(headers, rows) + [""]
        else:
            lines += ["No attempt was rejected.", ""]
        lines += [
            f"- {names[e['segment']]}: {e['repaired_200_cases']} served (200) cases used a repair."
            for e in m3
        ] + [""]

        lines += ["## Tokens and context", ""]
        rows = []
        for entry in m3:
            tokens = entry["tokens"]
            context = tokens["context_length_in_use"]
            rows.append(
                [
                    names[entry["segment"]],
                    tokens["max_prompt_plus_output"],
                    tokens["max_prompt"],
                    context if context else "not recorded",
                    tokens["attempts_done_reason_length"],
                    tokens["attempts_at_or_over_context"] if context else "-",
                ]
            )
        lines += _table(
            [
                "segment",
                "max prompt + output tokens",
                "max prompt tokens",
                "context length in use",
                "attempts with done_reason length",
                "attempts at or over the context",
            ],
            rows,
        ) + [""]

    same = diagnostics.get("same_evidence")
    if same:
        lines += ["## Same evidence in both tiers", ""]
        lines += [
            "Whether the first-attempt prompt hash of each case equals the oracle tier's (M2).",
            "",
        ]
        for name, result in same.items():
            differing = result["differing_cases"]
            lines += [
                f"- {name}: "
                + (
                    f"differs in {len(differing)} case(s): {', '.join(differing)}"
                    if differing
                    else "identical in every compared case"
                )
                + (
                    f"; not comparable for {len(result['not_comparable'])} case(s)"
                    if result["not_comparable"]
                    else ""
                )
            ]
        lines += [""]

    contrasts = diagnostics.get("contrasts")
    if contrasts:
        lines += _render_contrasts(contrasts)
    if m3 or same or contrasts:
        lines += [
            "Raw prompts and model output are in diagnostics-<tier>.json; they are untrusted "
            "text and are not reproduced in this report.",
            "",
        ]
    return lines


def _render_contrasts(contrasts: dict[str, Any]) -> list[str]:
    lines = ["## Within-machine contrasts", ""]
    lines += [
        "Every pair of segments run on this one machine. A repeat pair shares an Ollama image "
        "tag; a version pair does not. Counts are of cases.",
        "",
    ]
    rows = []
    for pair in contrasts["pairs"]:
        first, second = pair["segments"]
        rows.append(
            [
                f"r{first} - r{second}",
                pair["kind"],
                pair["different_end_to_end_outcome"],
                pair["different_status"],
                pair["different_first_attempt_raw_output_hash"],
                f"{pair['raw_output_hash_comparable_cases']} of {pair['cases']}",
            ]
        )
    lines += _table(
        [
            "pair",
            "kind",
            "different end-to-end outcome",
            "different status",
            "different first-attempt raw-output hash",
            "hashes comparable",
        ],
        rows,
    ) + [""]
    verdict = contrasts["version_effect"]
    largest, smallest = (
        contrasts["largest_repeat_pair_count"],
        contrasts["smallest_version_pair_count"],
    )
    if verdict is None:
        lines += [f"Version effect: not assessed ({contrasts['reason']}).", ""]
    else:
        lines += [
            f"Version effect on this machine: **{'shown' if verdict == 'shown' else 'not shown'}**"
            f" (largest repeat-pair count {_fmt(largest)}, smallest version-pair count "
            f"{_fmt(smallest)}, raw-output-hash measure; required margin "
            f"{VERSION_EFFECT_MARGIN})."
            + (f" Reason: {contrasts['reason']}." if contrasts["reason"] else ""),
            "",
            f"Rule, fixed before any run: {contrasts['rule']}.",
            "",
        ]
    return lines


# -- building a run ----------------------------------------------------------


def validate_and_build(
    run_dir: Path, expected_model: str, expected_repeats: int, baseline_dir: Path
) -> tuple[dict[str, Any], str]:
    """Validate every input, then return ``(summary, report markdown)``.

    Raises ``RunRefused`` listing every violation found; nothing is written here.
    """
    violations: list[str] = []
    if expected_repeats < 0:
        raise RunRefused(["--expected-repeats must be 0 or more"])
    if not run_dir.is_dir():
        raise RunRefused([f"run directory {run_dir} does not exist"])
    try:
        expected = _expected_counts()
    except (OSError, KeyError, ValueError) as error:
        raise RunRefused([f"committed datasets are unreadable: {error}"]) from error

    retrieval = _read_json(
        run_dir / "retrieval" / "results.json", "retrieval/results.json", violations
    )
    oracle_label = "grounded/results-deterministic.json"
    oracle = _read_json(
        run_dir / "grounded" / "results-deterministic.json", oracle_label, violations
    )
    env = _read_json(run_dir / "ENVIRONMENT.json", "ENVIRONMENT.json", violations)

    if retrieval is not None:
        _validate_retrieval(retrieval, expected["retrieval"], violations)
    if oracle is not None:
        _validate_grounded(
            oracle,
            tier="deterministic",
            label=oracle_label,
            expected=expected["grounded"],
            expected_model=None,
            violations=violations,
        )
    warnings: list[str] = []
    if env is not None:
        warnings = _validate_environment(env, expected_model, expected_repeats, violations)

    # Repeats: exactly r1..rN, no gaps and no strays.
    grounded_dir = run_dir / "grounded"
    present = sorted(
        int(match.group(1))
        for child in (grounded_dir.iterdir() if grounded_dir.is_dir() else [])
        if child.is_dir() and (match := _REPEAT_DIR.match(child.name))
    )
    wanted = list(range(1, expected_repeats + 1))
    for number in wanted:
        if number not in present:
            violations.append(f"grounded/r{number}: repeat is missing")
    for number in present:
        if number not in wanted:
            violations.append(f"grounded/r{number}: repeat was not expected ({expected_repeats})")
    segments: list[Segment] = []
    for number in wanted:
        directory = run_dir / "grounded" / f"r{number}"
        label = f"grounded/r{number}/results-ollama.json"
        payload = _read_json(directory / "results-ollama.json", label, violations)
        if payload is None:
            continue
        _validate_grounded(
            payload,
            tier="ollama",
            label=label,
            expected=expected["grounded"],
            expected_model=expected_model,
            violations=violations,
        )
        segment = Segment(number=number, payload=payload)
        segment.has_diagnostics = _validate_case_diagnostics(payload, label, violations)
        segment.meta = _read_optional_json(
            directory / "segment.json",
            f"grounded/r{number}/segment.json",
            violations,
            _validate_segment_meta,
            number,
        )
        segment.runtime = _read_optional_json(
            directory / "ollama-runtime.json",
            f"grounded/r{number}/ollama-runtime.json",
            violations,
            _validate_runtime,
        )
        segments.append(segment)
    _validate_segment_set(segments, run_dir, env, violations)
    oracle_has_diagnostics = (
        _validate_case_diagnostics(oracle, oracle_label, violations) if oracle else False
    )
    if env is not None:
        _validate_environment_extras(env, violations)
        if env.get("diagnostics_captured") is True:
            for name, has in [("oracle tier", oracle_has_diagnostics)] + [
                (f"grounded/r{s.number}", s.has_diagnostics) for s in segments
            ]:
                if oracle is not None and not has:
                    violations.append(
                        f"ENVIRONMENT.json says diagnostics were captured, but {name} has none"
                    )

    base_retrieval = _read_json(baseline_dir / "results.json", "baseline results.json", violations)
    base_oracle = _read_json(
        baseline_dir / "grounded" / "results-deterministic.json",
        "baseline grounded/results-deterministic.json",
        violations,
    )
    base_llm = _read_json(
        baseline_dir / "grounded" / "results-ollama.json",
        "baseline grounded/results-ollama.json",
        violations,
    )
    _validate_baseline(base_retrieval, base_oracle, base_llm, violations)
    if oracle is not None and base_oracle is not None:
        _validate_guardrail_names(oracle, base_oracle, oracle_label, violations)

    if violations:
        raise RunRefused(violations)
    assert retrieval and oracle and env and base_retrieval and base_oracle and base_llm
    summary = _build_summary(
        environment=env,
        warnings=warnings,
        expected_model=expected_model,
        retrieval=retrieval,
        oracle=oracle,
        oracle_has_diagnostics=oracle_has_diagnostics,
        segments=segments,
        base_retrieval=base_retrieval,
        base_oracle=base_oracle,
        base_llm=base_llm,
    )
    return summary, _render_report(summary)


# -- emit --------------------------------------------------------------------


class EmitRefused(Exception):
    """A file cannot be carried through a text log faithfully."""


def emit(run_dir: Path, out: BinaryIO) -> list[tuple[str, str, int]]:
    """Write every file under ``run_dir`` to ``out`` as BEGIN/END blocks, then the index.

    Returns ``(relative path, sha256, bytes)`` per file in the order printed.
    """
    entries: list[tuple[str, bytes]] = []
    for path in sorted(run_dir.rglob("*"), key=lambda p: p.relative_to(run_dir).as_posix()):
        relative = path.relative_to(run_dir).as_posix()
        if path.is_symlink():
            raise EmitRefused(f"{relative}: symbolic links are not emitted")
        if not path.is_file():
            continue
        if any(ord(char) < 0x20 or char == "\x7f" for char in relative):
            raise EmitRefused(f"{relative}: control characters in the path")
        data = path.read_bytes()
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as error:
            raise EmitRefused(f"{relative}: not UTF-8 text ({error})") from error
        if "\r" in text:
            raise EmitRefused(f"{relative}: contains a carriage return, which a log cannot carry")
        entries.append((relative, data))

    index: list[tuple[str, str, int]] = []
    for relative, data in entries:
        digest = hashlib.sha256(data).hexdigest()
        index.append((relative, digest, len(data)))
        out.write(f"D8-FILE-BEGIN {relative} {digest} {len(data)}\n".encode())
        out.write(data)
        out.write(b"\n")
        out.write(f"D8-FILE-END {relative}\n".encode())
    for relative, digest, size in index:
        out.write(f"D8-INDEX {relative} {digest} {size}\n".encode())
    return index


# -- command line ------------------------------------------------------------


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m evals.d8_report",
        description=(
            "Validate a D8 run directory fail-closed, then write D8-SUMMARY.json and "
            "D8-REPORT.md into it. Refuses (non-zero exit, no summary) on a fake or "
            "wrong provider or model, wrong counts, a missing repeat, or a missing "
            "ENVIRONMENT field."
        ),
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        required=True,
        help=(
            "run directory: retrieval/results.json, grounded/results-deterministic.json, "
            "grounded/r1/results-ollama.json [, r2 ...], ENVIRONMENT.json"
        ),
    )
    parser.add_argument(
        "--expected-llm-model", required=True, help="the model the LLM tier must have used"
    )
    parser.add_argument(
        "--expected-repeats",
        type=int,
        required=True,
        help="number of LLM repeats that must be present; 0 when the LLM tier was skipped",
    )
    parser.add_argument(
        "--baseline-dir",
        type=Path,
        default=DEFAULT_BASELINE_DIR,
        help="committed 2026-07-26 record, read-only (default: evals/results)",
    )
    parser.add_argument(
        "--emit",
        action="store_true",
        help="after writing, print every file under --run-dir with BEGIN/END markers and an index",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        summary, report = validate_and_build(
            arguments.run_dir,
            arguments.expected_llm_model,
            arguments.expected_repeats,
            arguments.baseline_dir,
        )
    except RunRefused as refusal:
        for reason in refusal.reasons:
            print(f"D8 REFUSED: {reason}", file=sys.stderr)
        print(
            f"D8 REFUSED: {len(refusal.reasons)} violation(s); no summary was written.",
            file=sys.stderr,
        )
        return 1

    (arguments.run_dir / "D8-SUMMARY.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (arguments.run_dir / "D8-REPORT.md").write_text(report, encoding="utf-8")
    print(f"D8 run validated; wrote D8-SUMMARY.json and D8-REPORT.md to {arguments.run_dir}")

    if arguments.emit:
        sys.stdout.flush()
        try:
            emit(arguments.run_dir, sys.stdout.buffer)
        except EmitRefused as refusal:
            print(f"D8 EMIT REFUSED: {refusal}", file=sys.stderr)
            return 1
        sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
