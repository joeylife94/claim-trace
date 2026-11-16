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
import hashlib
import json
import re
import sys
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
    "One embedding model and one 1.5B-parameter LLM, on a CPU runner. Nothing here ranks "
    "models or says the system handles Korean patents well.",
    "The oracle tier measures the pipeline, not a language model.",
    "Guardrail refusals are measured only against scripted output.",
    "Citation resolution shows that a quote is the stored text at its locator. It is not "
    "semantic entailment, and no output is a legal determination (infringement, validity, "
    "novelty, equivalence, inventive step, patentability).",
    "Real public documents and description retrieval were not measured.",
)

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
    llm_runs: list[dict[str, Any]],
    base_retrieval: dict[str, Any],
    base_oracle: dict[str, Any],
    base_llm: dict[str, Any],
) -> dict[str, Any]:
    llm_blocks = []
    for index, payload in enumerate(llm_runs, start=1):
        block = _grounded_block(payload)
        block["repeat"] = index
        llm_blocks.append(block)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "git_sha": environment["git_sha"],
        "run_id": environment["run_id"],
        "run_attempt": environment["run_attempt"],
        "environment": environment,
        "warnings": warnings,
        "expected_llm_model": expected_model,
        "expected_repeats": len(llm_runs),
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
        "non_claims": list(NON_CLAIMS),
    }


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
        if key not in ENVIRONMENT_REQUIRED_KEYS:
            env_rows.append([key, value])
    lines += _table(["field", "value"], env_rows) + [""]
    lines += [f"Report generated at {summary['generated_at']}.", ""]

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
        "## M2 Grounded pipeline, oracle tier (real embeddings, oracle in place of a language model)",
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
        columns = [(f"r{run['repeat']}", run["metrics"]) for run in llm_runs]
        columns.append((BASELINE_DATE, base["grounded_llm"]["metrics"]))
        lines += _metric_table(GROUNDED_METRIC_KEYS, columns) + [""]
        for key, title in (("g01", "g01"), ("g16", "g16 (injection document in scope)")):
            lines += [f"### {title} per repeat", ""]
            lines += _case_table(
                [(f"r{run['repeat']}", run[key]) for run in llm_runs]
                + [(BASELINE_DATE, base["grounded_llm"][key])]
            ) + [""]
        lines += ["### Cases that did not return a served answer", ""]
        failures = [
            [f"r{run['repeat']}", f["id"], f["status"], f["error_code"]]
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
        headers = ["case"] + [f"r{run['repeat']}" for run in llm_runs] + [BASELINE_DATE]
        base_by_id = {c["id"]: c for c in base["grounded_llm"]["per_case"]}
        outcome_rows = []
        for position, case in enumerate(llm_runs[0]["per_case"]):
            row: list[Any] = [case["id"]]
            row += [run["per_case"][position]["end_to_end_success"] for run in llm_runs]
            row.append(base_by_id.get(case["id"], {}).get("end_to_end_success"))
            outcome_rows.append(row)
        lines += _table(headers, outcome_rows) + [""]

        stability = summary["stability"]
        lines += ["### Stability across repeats", ""]
        if stability["computed"]:
            lines += [
                f"{stability['identical_end_to_end_outcome']} of {stability['case_count']} cases "
                f"had the same end-to-end outcome in all {stability['repeats']} repeats "
                "(temperature 0, no seed).",
                "",
            ]
            if stability["differing_cases"]:
                lines += _table(
                    ["case", "end_to_end per repeat"],
                    [
                        [d["id"], d["end_to_end_success_per_repeat"]]
                        for d in stability["differing_cases"]
                    ],
                ) + [""]
        else:
            lines += [f"Not computed: {stability['reason']}.", ""]
    return "\n".join(lines).rstrip("\n") + "\n"


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
    llm_runs: list[dict[str, Any]] = []
    for number in wanted:
        label = f"grounded/r{number}/results-ollama.json"
        payload = _read_json(
            run_dir / "grounded" / f"r{number}" / "results-ollama.json", label, violations
        )
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
        llm_runs.append(payload)

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
        llm_runs=llm_runs,
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
