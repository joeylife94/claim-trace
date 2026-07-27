"""Run the grounded-generation evaluation end to end.

    docker compose run --rm api python -m evals.grounded_run                 # deterministic
    docker compose run --rm api python -m evals.grounded_run --tier ollama   # real model

There is no shortcut anywhere in this script. It uploads real PDFs through the
real ingestion endpoint, parses them with the real Korean claim parser, indexes
them with the configured embedding provider, and asks every question through
``POST /api/v1/grounded/answers``. Every returned citation is then verified by
reading the page back through ``GET /api/v1/documents/{id}/pages`` and comparing
the quote to the stored text at its own offsets - so the headline
"citation resolution" number is measured against persisted state rather than
asserted.

Two tiers, and the distinction is not cosmetic:

* ``deterministic`` replaces the model with an oracle that reads the evidence
  blocks it was given. It measures the **pipeline** - retrieval, the context
  budget, the catalog, citation resolution, and the guardrails - reliably and in
  seconds. It is **not** a measurement of model quality and must never be quoted
  as one.
* ``ollama`` runs the configured local model. That is the only tier whose
  evidence-selection numbers say anything about a model, and with a 1.5B model on
  CPU it says something about *that* model on a 23-claim synthetic corpus, which
  is a long way from a benchmark.

The evaluation runs against a dedicated ``*_grounded_eval`` database that it
creates and truncates itself, so it never touches development data.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from fastapi.testclient import TestClient

from claimtrace_api.core.config import Settings
from claimtrace_api.main import create_app
from evals.grounded_dataset import (
    GroundedCase,
    GroundedDocument,
    load_grounded_cases,
    load_grounded_documents,
)
from evals.grounded_metrics import CaseOutcome, GroundedSummary, summarise
from evals.grounded_oracle import (
    GUARDRAIL_REPAIR_SCRIPTS,
    GUARDRAIL_SCRIPTS,
    OracleLLMProvider,
)

DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "results" / "grounded"
TOP_K = 6

#: The question the guardrail scripts answer. Ordinary and answerable, so a
#: refusal is unambiguously about the scripted output rather than about the
#: question being hard.
GUARDRAIL_QUESTION = "산출된 해시값은 무엇과 비교되는가?"
GUARDRAIL_SCOPE = "adversarial"


@dataclass(frozen=True, slots=True)
class GuardrailOutcome:
    """One hostile payload, and whether the pipeline refused to serve it."""

    name: str
    status: int
    error_code: str | None
    refused: bool
    repaired: bool


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ClaimTrace grounded-generation evaluation")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--tier",
        choices=("deterministic", "ollama"),
        default="deterministic",
        help="deterministic uses the in-process oracle; ollama uses the configured model",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="run only the first N cases (the real tier is slow on CPU)",
    )
    arguments = parser.parse_args(argv)

    settings = _eval_settings(arguments.tier)
    _prepare_database(settings)

    documents = load_grounded_documents()
    cases = load_grounded_cases()
    if arguments.limit:
        cases = cases[: arguments.limit]

    application = create_app(settings)
    with TestClient(application) as client:
        corpus = _index_corpus(client, documents)
        outcomes = _run_cases(client, cases, corpus, tier=arguments.tier)
        guardrails = _run_guardrails(client, corpus, tier=arguments.tier)
        provider = _provider_facts(client, arguments.tier)

    summary = summarise(outcomes)

    arguments.output_dir.mkdir(parents=True, exist_ok=True)
    payload = _results_payload(arguments.tier, provider, corpus, summary, outcomes, guardrails)
    suffix = arguments.tier
    (arguments.output_dir / f"results-{suffix}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (arguments.output_dir / f"REPORT-{suffix}.md").write_text(
        _markdown_report(payload, summary, outcomes, guardrails), encoding="utf-8"
    )

    _print_summary(arguments.tier, summary, guardrails, arguments.output_dir)
    return 0


# -- setup ------------------------------------------------------------------


def _eval_settings(tier: str) -> Settings:
    """Settings pointed at a dedicated evaluation database."""
    ambient = Settings()
    base = sa.engine.make_url(ambient.sqlalchemy_database_uri)
    eval_url = base.set(database=f"{base.database}_grounded_eval").render_as_string(
        hide_password=False
    )

    overrides: dict[str, Any] = {
        "database_url": eval_url,
        "log_level": "WARNING",
        "storage_root": Path("/tmp/claimtrace-grounded-eval-uploads"),
    }
    if tier == "deterministic":
        # The oracle is installed over app.state below; the configured provider
        # is irrelevant, and "fake" guarantees nothing tries to reach a network.
        overrides["llm_provider"] = "fake"
    else:
        overrides["llm_provider"] = "ollama"
    return Settings(**overrides)


def _prepare_database(settings: Settings) -> None:
    """Create the evaluation database, migrate it, and empty it."""
    base = sa.engine.make_url(settings.sqlalchemy_database_uri)
    admin_url = base.set(database="postgres").render_as_string(hide_password=False)

    admin = sa.create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        exists = connection.scalar(
            sa.text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": base.database}
        )
        if not exists:
            connection.execute(sa.text(f'CREATE DATABASE "{base.database}"'))
    admin.dispose()

    from alembic import command
    from alembic.config import Config

    api_root = Path(__file__).resolve().parents[1]
    config = Config(str(api_root / "alembic.ini"))
    config.set_main_option("script_location", str(api_root / "alembic"))
    config.attributes["sqlalchemy_url"] = settings.sqlalchemy_database_uri
    command.upgrade(config, "head")

    engine = sa.create_engine(settings.sqlalchemy_database_uri)
    with engine.begin() as connection:
        connection.execute(sa.text("TRUNCATE TABLE document_pages, documents CASCADE"))
    engine.dispose()


# -- pipeline ---------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Corpus:
    """The indexed corpus, and the two lookups scoring needs."""

    #: corpus id -> database document id
    document_ids: dict[str, str]
    #: filename -> corpus id, for mapping an answer's evidence back to a label
    corpus_ids: dict[str, str]
    claim_count: int
    profile: dict[str, Any]


def _index_corpus(client: TestClient, documents: tuple[GroundedDocument, ...]) -> Corpus:
    """Upload, parse, and index every synthetic document."""
    from tests.claim_fixtures import build_korean_claims_pdf

    document_ids: dict[str, str] = {}
    corpus_ids: dict[str, str] = {}
    claim_count = 0
    profile: dict[str, Any] = {}

    for document in documents:
        upload = client.post(
            "/api/v1/documents",
            files={
                "file": (
                    document.filename,
                    build_korean_claims_pdf(document.page_texts()),
                    "application/pdf",
                )
            },
        )
        _require(upload.status_code in (200, 201), f"upload failed: {upload.text}")
        document_id = upload.json()["id"]
        document_ids[document.id] = document_id
        corpus_ids[document.filename] = document.id

        parsed = client.post(f"/api/v1/documents/{document_id}/claims/parse")
        _require(parsed.status_code in (200, 201), f"parse failed: {parsed.text}")
        found = parsed.json()["result"]["claim_count"]
        # A silent mismatch here would make every label wrong, so it aborts.
        _require(
            found == len(document.claims),
            f"{document.id}: parser found {found} claims, corpus declares {len(document.claims)}",
        )
        claim_count += found

        indexed = client.post(f"/api/v1/documents/{document_id}/claims/index")
        _require(indexed.status_code in (200, 201), f"index failed: {indexed.text}")
        run = indexed.json()
        profile = {
            key: run[key]
            for key in (
                "embedding_provider",
                "embedding_model",
                "embedding_model_version",
                "embedding_dimension",
                "lexical_strategy",
            )
        }

    return Corpus(
        document_ids=document_ids,
        corpus_ids=corpus_ids,
        claim_count=claim_count,
        profile=profile,
    )


def _install_oracle(client: TestClient, case: GroundedCase, corpus: Corpus) -> None:
    """Point the app at an oracle that knows this case's labels.

    ``app.state.llm_provider`` is the documented seam. The oracle receives the
    labels expressed as ``(filename, claim number)`` because that is what the
    prompt shows it - it never learns a database id, and it never sees the
    catalog.
    """
    filenames = {corpus_id: name for name, corpus_id in corpus.corpus_ids.items()}
    wanted = frozenset(
        (filenames[document_id], number) for document_id, number in case.all_credited
    )
    fallback = next(iter(sorted(case.reasons)), "evidence_not_specific_enough")
    client.app.state.llm_provider = OracleLLMProvider(  # type: ignore[attr-defined]
        wanted=wanted, fallback_reason=fallback
    )


def _run_cases(
    client: TestClient,
    cases: tuple[GroundedCase, ...],
    corpus: Corpus,
    *,
    tier: str,
) -> list[CaseOutcome]:
    outcomes: list[CaseOutcome] = []

    for case in cases:
        if tier == "deterministic":
            _install_oracle(client, case, corpus)

        payload: dict[str, Any] = {"query": case.question, "top_k": TOP_K}
        if case.scope:
            payload["document_ids"] = [corpus.document_ids[case.scope]]

        started = time.perf_counter()
        response = client.post("/api/v1/grounded/answers", json=payload)
        duration = time.perf_counter() - started

        outcomes.append(_score(case, response, corpus, client, duration))
        print(f"  {case.id:<34} {outcomes[-1].status} {duration:6.2f}s", flush=True)

    return outcomes


def _score(
    case: GroundedCase,
    response: Any,
    corpus: Corpus,
    client: TestClient,
    duration: float,
) -> CaseOutcome:
    if response.status_code != 200:
        body = response.json() if response.content else {}
        return CaseOutcome(
            case=case,
            status=response.status_code,
            error_code=body.get("error_code"),
            insufficient_evidence=False,
            insufficient_reason=None,
            statement_count=0,
            cited_statement_count=0,
            cited=frozenset(),
            # Nothing was returned, so nothing failed to resolve. The refusal
            # itself is counted by the other metrics, and marking this False
            # would double-count one failure as two.
            citations_resolve=True,
            unresolvable_span_count=0,
            retrieved_candidate_count=0,
            included_evidence_count=0,
            omitted_evidence_count=0,
            duration_seconds=duration,
        )

    body = response.json()
    evidence_by_id = {entry["evidence_id"]: entry for entry in body["evidence"]}

    cited: set[tuple[str, int]] = set()
    for entry in body["evidence"]:
        corpus_id = corpus.corpus_ids.get(entry["document_name"])
        if corpus_id:
            cited.add((corpus_id, entry["claim_number"]))

    resolves, unresolvable = _verify_citations(client, body)

    return CaseOutcome(
        case=case,
        status=200,
        error_code=None,
        insufficient_evidence=body["insufficient_evidence"],
        insufficient_reason=body["insufficient_reason"],
        statement_count=len(body["statements"]),
        cited_statement_count=sum(
            1
            for statement in body["statements"]
            if statement["evidence_ids"]
            and all(evidence_id in evidence_by_id for evidence_id in statement["evidence_ids"])
        ),
        cited=frozenset(cited),
        citations_resolve=resolves,
        unresolvable_span_count=unresolvable,
        retrieved_candidate_count=body["retrieval"]["retrieved_candidate_count"],
        included_evidence_count=body["retrieval"]["included_evidence_count"],
        omitted_evidence_count=body["retrieval"]["omitted_evidence_count"],
        duration_seconds=duration,
    )


def _verify_citations(client: TestClient, body: Any) -> tuple[bool, int]:
    """Check every quote against the stored page text at its own locator.

    Read back through the public pages endpoint rather than trusted from the
    answer, so this measures persisted state. This is the phase's central claim
    and the one number in the report that is worth more than the others.
    """
    unresolvable = 0
    for entry in body["evidence"]:
        if not entry["source_spans"]:
            unresolvable += 1
            continue
        for span in entry["source_spans"]:
            locator = span["locator"]
            stored = _page_text(client, locator["document_id"], locator["page_number"])
            expected = stored[locator["start_char"] : locator["end_char"]]
            if stored is None or span["quote"] != expected or not span["quote"]:
                unresolvable += 1
    return unresolvable == 0, unresolvable


_PAGE_CACHE: dict[tuple[str, int], str] = {}


def _page_text(client: TestClient, document_id: str, page_number: int) -> str:
    key = (document_id, page_number)
    if key not in _PAGE_CACHE:
        response = client.get(f"/api/v1/documents/{document_id}/pages?limit=200")
        _require(response.status_code == 200, f"pages failed: {response.text}")
        for page in response.json()["items"]:
            _PAGE_CACHE[(document_id, page["page_number"])] = page["text"]
    return _PAGE_CACHE.get(key, "")


def _run_guardrails(client: TestClient, corpus: Corpus, *, tier: str) -> list[GuardrailOutcome]:
    """Send output that must never be served, and check that it is not.

    Only meaningful in the deterministic tier: a real model cannot be instructed
    to produce a specific invalid answer on demand, and waiting for one to
    hallucinate an identifier is not a test. The pipeline being exercised is the
    same one the real tier runs through.
    """
    if tier != "deterministic":
        return []

    outcomes: list[GuardrailOutcome] = []
    payload = {
        "query": GUARDRAIL_QUESTION,
        "top_k": TOP_K,
        "document_ids": [corpus.document_ids[GUARDRAIL_SCOPE]],
    }

    for name, script in GUARDRAIL_SCRIPTS.items():
        repair_script = GUARDRAIL_REPAIR_SCRIPTS.get(name)
        client.app.state.llm_provider = OracleLLMProvider(  # type: ignore[attr-defined]
            script=repair_script or script
        )
        response = client.post("/api/v1/grounded/answers", json=payload)
        body = response.json() if response.content else {}
        error_code = body.get("error_code")

        # Refused means: not served as a successful answer. A 200 here would be
        # the pipeline handing a reader an uncheckable claim.
        outcomes.append(
            GuardrailOutcome(
                name=name,
                status=response.status_code,
                error_code=error_code,
                refused=response.status_code != 200,
                repaired=error_code == "grounded_repair_failed",
            )
        )
        print(f"  guardrail {name:<30} {response.status_code} {error_code}", flush=True)

    return outcomes


def _provider_facts(client: TestClient, tier: str) -> dict[str, Any]:
    """The provider actually used, read from the status endpoint."""
    if tier == "deterministic":
        return {
            "provider": "oracle",
            "model": "oracle-v1 (in-process, not a language model)",
            "available": True,
            "model_available": True,
        }
    response = client.get("/api/v1/llm/status")
    _require(response.status_code == 200, f"llm status failed: {response.text}")
    status = response.json()
    return {
        "provider": status["provider"],
        "model": status["model"],
        "available": status["available"],
        "model_available": status["model_available"],
        "structured_output_mode": status["capabilities"]["structured_output_mode"],
    }


# -- reporting --------------------------------------------------------------


def _results_payload(
    tier: str,
    provider: dict[str, Any],
    corpus: Corpus,
    summary: GroundedSummary,
    outcomes: list[CaseOutcome],
    guardrails: list[GuardrailOutcome],
) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "tier": tier,
        "provider": provider,
        "corpus": {
            "documents": len(load_grounded_documents()),
            "claims": corpus.claim_count,
            "cases": len(outcomes),
            "retrieval_profile": corpus.profile,
        },
        "metrics": summary.as_dict(),
        "guardrails": [
            {
                "name": guardrail.name,
                "status": guardrail.status,
                "error_code": guardrail.error_code,
                "refused": guardrail.refused,
            }
            for guardrail in guardrails
        ],
        "per_case": [
            {
                "id": outcome.case.id,
                "category": outcome.case.category,
                "status": outcome.status,
                "error_code": outcome.error_code,
                "answerable": outcome.case.answerable,
                "insufficient_evidence": outcome.insufficient_evidence,
                "insufficient_reason": outcome.insufficient_reason,
                "statements": outcome.statement_count,
                "cited": sorted(f"{doc}#{num}" for doc, num in outcome.cited),
                "expected": sorted(f"{doc}#{num}" for doc, num in outcome.case.relevant),
                "forbidden_cited": sorted(f"{doc}#{num}" for doc, num in outcome.cited_forbidden),
                "citations_resolve": outcome.citations_resolve,
                "selection_precision": _round(outcome.selection_precision),
                "selection_recall": _round(outcome.selection_recall),
                "end_to_end_success": outcome.end_to_end_success,
                "duration_seconds": round(outcome.duration_seconds, 3),
            }
            for outcome in outcomes
        ],
    }


def _markdown_report(
    payload: dict[str, Any],
    summary: GroundedSummary,
    outcomes: list[CaseOutcome],
    guardrails: list[GuardrailOutcome],
) -> str:
    tier = payload["tier"]
    provider = payload["provider"]
    metrics = payload["metrics"]

    caveat = (
        "> **This tier does not measure model quality.** The model is replaced by an "
        "in-process oracle that reads the evidence blocks it was given and cites the "
        "labelled claims that are present. What is measured is the pipeline: retrieval, "
        "the context budget, the evidence catalog, citation resolution, and the "
        "guardrails. Nothing here says anything about how well a language model answers "
        "patent questions."
        if tier == "deterministic"
        else "> **A small model on a synthetic corpus.** These numbers describe "
        f"`{provider['model']}` answering {payload['corpus']['cases']} newly authored "
        f"questions over {payload['corpus']['claims']} synthetic claims. That is enough "
        "to show the pipeline works with a real model and to catch a gross regression. "
        "It is **not** a benchmark, and it does not establish that this system answers "
        "Korean patent questions well."
    )

    lines = [
        f"# ClaimTrace grounded-generation evaluation ({tier})",
        "",
        f"Generated {payload['generated_at']}.",
        "",
        caveat,
        "",
        "## Configuration",
        "",
        "| Setting | Value |",
        "| --- | --- |",
        f"| Tier | `{tier}` |",
        f"| Provider | `{provider['provider']}` |",
        f"| Model | `{provider['model']}` |",
        f"| Documents | {payload['corpus']['documents']} |",
        f"| Claims | {payload['corpus']['claims']} |",
        f"| Cases | {payload['corpus']['cases']} |",
        f"| Embedding model | `{payload['corpus']['retrieval_profile'].get('embedding_model')}` |",
        f"| top_k | {TOP_K} |",
        "",
        "## Metrics",
        "",
        "| Metric | Value | What it means |",
        "| --- | --- | --- |",
        f"| Structured-output success | {metrics['structured_output_rate']:.3f} | "
        "the answer satisfied the JSON schema |",
        f"| Answerability accuracy | {metrics['answerability_accuracy']:.3f} | "
        "answered when the corpus answers, declined when it does not |",
        f"| Insufficient-evidence precision | {metrics['insufficient_precision']:.3f} | "
        "of the questions declined, how many should have been |",
        f"| Insufficient-evidence recall | {metrics['insufficient_recall']:.3f} | "
        "of the questions that should be declined, how many were |",
        f"| Evidence-ID validity | {metrics['evidence_id_validity_rate']:.3f} | "
        "no answer was refused for naming an id the server never issued |",
        f"| **Citation resolution** | **{metrics['citation_resolution_rate']:.3f}** | "
        "**every returned quote is the stored page text at its own locator** |",
        f"| Statement citation coverage | {metrics['statement_citation_coverage']:.3f} | "
        "returned statements carrying a resolvable citation |",
        f"| Evidence selection precision | {metrics['selection_precision']:.3f} | "
        "cited claims that were credited by the labels |",
        f"| Evidence selection recall | {metrics['selection_recall']:.3f} | "
        "required claims that were cited |",
        f"| End-to-end success | {metrics['end_to_end_success_rate']:.3f} | "
        "all of the above, per case |",
        f"| Forbidden citations | {metrics['forbidden_citation_count']} | "
        "citations outside a scoped question's document |",
        f"| Mean latency | {metrics['mean_duration_seconds']:.2f} s | per question |",
        "",
    ]

    if guardrails:
        refused = sum(1 for guardrail in guardrails if guardrail.refused)
        lines += [
            "## Guardrails",
            "",
            f"{refused} of {len(guardrails)} hostile payloads were refused rather than "
            "served. Each is a complete, schema-shaped answer that breaks exactly one "
            "grounding rule, sent through the whole pipeline against a real question over "
            "the real corpus.",
            "",
            "| Payload | Status | Error code | Refused |",
            "| --- | --- | --- | --- |",
        ]
        for guardrail in guardrails:
            lines.append(
                f"| `{guardrail.name}` | {guardrail.status} | "
                f"`{guardrail.error_code or '-'}` | {'yes' if guardrail.refused else '**NO**'} |"
            )
        lines.append("")

    lines += _weak_case_section(outcomes)
    lines += _by_category_section(outcomes)

    lines += [
        "",
        "## What a passing citation does and does not establish",
        "",
        "A resolved citation establishes that the statement points at retrieved source "
        "text, that the text is stored by this deployment, and that a reader can open the "
        "exact page and character range it came from.",
        "",
        "It does **not** establish that the cited claim entails the statement. No amount "
        "of identifier checking can prove that a sentence is a faithful reading of the "
        "text it cites; that is a semantic judgement, and this pipeline makes none. A "
        "grounded answer is a *checkable* answer, not a verified one.",
        "",
        "ClaimTrace does not provide legal advice and does not determine infringement, "
        "validity, novelty, inventive step, or patentability.",
        "",
        "## Reproducing",
        "",
        "```bash",
        "docker compose up -d postgres",
        "docker compose run --rm api python -m evals.grounded_run",
        "",
        "# with the configured local model (Ollama must be reachable)",
        "docker compose run --rm api python -m evals.grounded_run --tier ollama",
        "```",
        "",
    ]
    return "\n".join(lines)


def _weak_case_section(outcomes: list[CaseOutcome]) -> list[str]:
    weak = [outcome for outcome in outcomes if not outcome.end_to_end_success]
    lines = ["", "## Weak and failed cases", ""]
    if not weak:
        lines.append("Every case succeeded end to end.")
        return lines

    lines += [
        "| Case | Category | Status | Expected | Cited | Why |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for outcome in weak:
        expected = ", ".join(sorted(f"{d}#{n}" for d, n in outcome.case.relevant)) or "(decline)"
        cited = ", ".join(sorted(f"{d}#{n}" for d, n in outcome.cited)) or "(nothing)"
        lines.append(
            f"| `{outcome.case.id}` | {outcome.case.category} | "
            f"{outcome.status}{' ' + (outcome.error_code or '') if outcome.error_code else ''} | "
            f"{expected} | {cited} | {_failure_reason(outcome)} |"
        )
    return lines


def _failure_reason(outcome: CaseOutcome) -> str:
    if outcome.status != 200:
        return f"request failed: {outcome.error_code}"
    if not outcome.citations_resolve:
        return f"{outcome.unresolvable_span_count} span(s) did not resolve"
    if outcome.cited_forbidden:
        return "cited outside the document scope"
    if not outcome.answerability_correct:
        return (
            "declined an answerable question"
            if outcome.insufficient_evidence
            else ("answered a question the corpus does not answer")
        )
    if not outcome.reason_acceptable:
        return f"unexpected reason: {outcome.insufficient_reason}"
    return "cited none of the required claims"


def _by_category_section(outcomes: list[CaseOutcome]) -> list[str]:
    lines = [
        "",
        "## By category",
        "",
        "| Category | Cases | End-to-end success |",
        "| --- | --- | --- |",
    ]
    for category in sorted({outcome.case.category for outcome in outcomes}):
        group = [outcome for outcome in outcomes if outcome.case.category == category]
        succeeded = sum(1 for outcome in group if outcome.end_to_end_success)
        lines.append(f"| {category} | {len(group)} | {succeeded}/{len(group)} |")
    return lines


def _print_summary(
    tier: str,
    summary: GroundedSummary,
    guardrails: list[GuardrailOutcome],
    output_dir: Path,
) -> None:
    print(f"\ntier: {tier}")
    for key, value in summary.as_dict().items():
        print(f"  {key:<32} {value}")
    if guardrails:
        refused = sum(1 for guardrail in guardrails if guardrail.refused)
        print(f"  {'guardrails refused':<32} {refused}/{len(guardrails)}")
    print(f"\nWrote {output_dir / f'results-{tier}.json'} and {output_dir / f'REPORT-{tier}.md'}")


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 4)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"evaluation aborted: {message}")


if __name__ == "__main__":
    sys.exit(main())
