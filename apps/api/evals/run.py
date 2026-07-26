"""Run the retrieval evaluation end to end.

    docker compose run --rm api python -m evals.run

There is no shortcut anywhere in this script. It uploads real PDFs through the
real ingestion endpoint, parses them with the real claim parser, indexes them
with the configured embedding provider through the real indexing service, and
queries them through ``POST /api/v1/search/claims``. If retrieval regresses, this
regresses; if it were wired to a private code path, the numbers would mean
nothing.

The evaluation runs against a dedicated ``*_eval`` database that it creates and
truncates itself, so it never touches development data.

Reported numbers are only as good as the corpus: 26 synthetic claims and 19
queries measure whether the pipeline is wired correctly and let two
configurations be compared against each other. They do not establish that this
system retrieves Korean patent claims well, and nothing here should be quoted as
if they did.
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
from evals.dataset import EvalQuery, SyntheticDocument, load_documents, load_queries
from evals.metrics import MetricSummary, summarise

MODES = ("dense", "lexical", "hybrid")
TOP_K = 10
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "results"


@dataclass(frozen=True, slots=True)
class QueryOutcome:
    """One query under one mode, kept so weak cases can be reported individually."""

    query: EvalQuery
    mode: str
    #: ``(document id, claim number)`` in rank order.
    retrieved: list[tuple[str, int]]
    reciprocal_rank: float


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ClaimTrace retrieval evaluation")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Where to write results.json and REPORT.md",
    )
    parser.add_argument(
        "--provider",
        choices=("sentence-transformers", "fake"),
        default=None,
        help="Override EMBEDDING_PROVIDER for this run",
    )
    arguments = parser.parse_args(argv)

    settings = _eval_settings(arguments.provider)
    _prepare_database(settings)

    documents = load_documents()
    queries = load_queries()

    application = create_app(settings)
    with TestClient(application) as client:
        indexing = _index_corpus(client, documents)
        outcomes, timings = _run_queries(client, queries)

    summaries = {
        mode: summarise(
            mode,
            judged=[
                (outcome.retrieved, outcome.query.relevant)
                for outcome in outcomes
                if outcome.mode == mode
            ],
        )
        for mode in MODES
    }

    arguments.output_dir.mkdir(parents=True, exist_ok=True)
    payload = _results_payload(settings, indexing, summaries, outcomes, timings)
    (arguments.output_dir / "results.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (arguments.output_dir / "REPORT.md").write_text(
        _markdown_report(payload, summaries, outcomes), encoding="utf-8"
    )

    _print_summary(summaries, arguments.output_dir)
    return 0


# -- setup ------------------------------------------------------------------


def _eval_settings(provider_override: str | None) -> Settings:
    """Settings pointed at a dedicated evaluation database."""
    ambient = Settings()
    base = sa.engine.make_url(ambient.sqlalchemy_database_uri)
    eval_url = base.set(database=f"{base.database}_eval").render_as_string(hide_password=False)

    overrides: dict[str, Any] = {"database_url": eval_url, "log_level": "WARNING"}
    if provider_override:
        overrides["embedding_provider"] = provider_override
    # Storage has to be writable and is throwaway: the PDFs are regenerated on
    # every run from the committed corpus.
    overrides["storage_root"] = Path("/tmp/claimtrace-eval-uploads")
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


def _index_corpus(client: TestClient, documents: tuple[SyntheticDocument, ...]) -> dict[str, Any]:
    """Upload, parse, and index every synthetic document."""
    from tests.claim_fixtures import build_korean_claims_pdf

    document_ids: dict[str, str] = {}
    profile: dict[str, Any] = {}
    indexed_claims = 0
    index_seconds = 0.0

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

        parsed = client.post(f"/api/v1/documents/{document_id}/claims/parse")
        _require(parsed.status_code in (200, 201), f"parse failed: {parsed.text}")
        found = parsed.json()["result"]["claim_count"]
        _require(
            found == len(document.claims),
            f"{document.id}: parser found {found} claims, corpus declares {len(document.claims)}",
        )

        started = time.perf_counter()
        indexed = client.post(f"/api/v1/documents/{document_id}/claims/index")
        index_seconds += time.perf_counter() - started
        _require(indexed.status_code in (200, 201), f"index failed: {indexed.text}")

        run = indexed.json()
        indexed_claims += run["indexed_claim_count"]
        profile = {
            "embedding_provider": run["embedding_provider"],
            "embedding_model": run["embedding_model"],
            "embedding_model_version": run["embedding_model_version"],
            "embedding_dimension": run["embedding_dimension"],
            "vectors_normalized": run["vectors_normalized"],
            "normalization_version": run["normalization_version"],
            "lexical_strategy": run["lexical_strategy"],
            "lexical_strategy_version": run["lexical_strategy_version"],
        }

    return {
        "document_ids": document_ids,
        "indexed_claim_count": indexed_claims,
        "index_seconds": round(index_seconds, 3),
        "profile": profile,
    }


def _run_queries(
    client: TestClient, queries: tuple[EvalQuery, ...]
) -> tuple[list[QueryOutcome], dict[str, float]]:
    """Execute every query in every mode against the search endpoint."""
    from evals.metrics import MRR_AT, reciprocal_rank

    outcomes: list[QueryOutcome] = []
    timings: dict[str, float] = {}

    # Filename -> corpus id, so results can be scored against the labels without
    # the labels having to know a database identifier.
    corpus_ids = {document.filename: document.id for document in load_documents()}

    for mode in MODES:
        started = time.perf_counter()
        for query in queries:
            response = client.post(
                "/api/v1/search/claims",
                json={"query": query.query, "mode": mode, "top_k": TOP_K},
            )
            _require(response.status_code == 200, f"search failed: {response.text}")
            body = response.json()

            retrieved = [
                (corpus_ids[result["document_filename"]], result["claim_number"])
                for result in body["results"]
            ]
            outcomes.append(
                QueryOutcome(
                    query=query,
                    mode=mode,
                    retrieved=retrieved,
                    reciprocal_rank=reciprocal_rank(retrieved, query.relevant, MRR_AT),
                )
            )
        timings[mode] = round((time.perf_counter() - started) / len(queries) * 1000, 2)

    return outcomes, timings


# -- reporting --------------------------------------------------------------


def _results_payload(
    settings: Settings,
    indexing: dict[str, Any],
    summaries: dict[str, MetricSummary],
    outcomes: list[QueryOutcome],
    timings: dict[str, float],
) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "corpus": {
            "documents": len(load_documents()),
            "claims": indexing["indexed_claim_count"],
            "queries": len(load_queries()),
        },
        "profile": indexing["profile"],
        "settings": {
            "rrf_k": settings.rrf_k,
            "dense_candidate_count": settings.dense_candidate_count,
            "lexical_candidate_count": settings.lexical_candidate_count,
            "top_k": TOP_K,
        },
        "timing": {
            "total_index_seconds": indexing["index_seconds"],
            "mean_query_ms": timings,
        },
        "metrics": {mode: summary.as_dict() for mode, summary in summaries.items()},
        "per_query": [
            {
                "id": outcome.query.id,
                "category": outcome.query.category,
                "mode": outcome.mode,
                "relevant": sorted(f"{doc}#{num}" for doc, num in outcome.query.relevant),
                "retrieved": [f"{doc}#{num}" for doc, num in outcome.retrieved[:5]],
                "reciprocal_rank": round(outcome.reciprocal_rank, 4),
            }
            for outcome in outcomes
        ],
    }


def _markdown_report(
    payload: dict[str, Any],
    summaries: dict[str, MetricSummary],
    outcomes: list[QueryOutcome],
) -> str:
    profile = payload["profile"]
    lines = [
        "# ClaimTrace retrieval evaluation",
        "",
        f"Generated {payload['generated_at']}.",
        "",
        "> Synthetic corpus of "
        f"{payload['corpus']['claims']} newly authored Korean patent-like claims across "
        f"{payload['corpus']['documents']} documents, with {payload['corpus']['queries']} "
        "queries. This is large enough to catch a broken retrieval channel and to "
        "compare two configurations. It is **far too small to establish retrieval "
        "quality**, and none of these numbers should be read as a benchmark result.",
        "",
        "## Configuration",
        "",
        "| Setting | Value |",
        "| --- | --- |",
        f"| Embedding provider | `{profile['embedding_provider']}` |",
        f"| Embedding model | `{profile['embedding_model']}` |",
        f"| Model version | `{profile['embedding_model_version']}` |",
        f"| Dimension | {profile['embedding_dimension']} |",
        f"| Vectors normalised | {profile['vectors_normalized']} |",
        f"| Normalisation | `{profile['normalization_version']}` |",
        f"| Lexical strategy | `{profile['lexical_strategy']}` "
        f"`{profile['lexical_strategy_version']}` |",
        f"| RRF k | {payload['settings']['rrf_k']} |",
        f"| top_k | {payload['settings']['top_k']} |",
        "",
        "## Results",
        "",
        "Recall is *set* recall: for a query with three relevant claims, Recall@1 "
        "cannot exceed 0.33. The two queries with no relevant claim are excluded "
        "from recall and MRR and reported separately in the last column.",
        "",
        "| Mode | Recall@1 | Recall@3 | Recall@5 | MRR@10 | Returned something for a "
        "no-answer query |",
        "| --- | --- | --- | --- | --- | --- |",
    ]

    for mode in MODES:
        summary = summaries[mode]
        lines.append(
            f"| {mode} | {summary.recall_at_1:.3f} | {summary.recall_at_3:.3f} | "
            f"{summary.recall_at_5:.3f} | {summary.mrr_at_10:.3f} | "
            f"{summary.empty_query_hit_rate:.0%} |"
        )

    lines += [
        "",
        "Mean query latency: "
        + ", ".join(f"{mode} {ms} ms" for mode, ms in payload["timing"]["mean_query_ms"].items())
        + ".",
        f" Indexing the whole corpus took {payload['timing']['total_index_seconds']} s.",
        "",
        "## By query category",
        "",
        "| Category | dense MRR@10 | lexical MRR@10 | hybrid MRR@10 |",
        "| --- | --- | --- | --- |",
    ]

    categories = sorted({outcome.query.category for outcome in outcomes if outcome.query.relevant})
    for category in categories:
        cells = []
        for mode in MODES:
            scores = [
                outcome.reciprocal_rank
                for outcome in outcomes
                if outcome.mode == mode
                and outcome.query.category == category
                and outcome.query.relevant
            ]
            cells.append(f"{sum(scores) / len(scores):.3f}" if scores else "-")
        lines.append(f"| {category} | " + " | ".join(cells) + " |")

    lines += _weak_case_section(outcomes)
    lines += _regression_section(summaries, outcomes)

    lines += [
        "",
        "## Reproducing",
        "",
        "```bash",
        "docker compose up -d postgres",
        "docker compose run --rm api python -m evals.run",
        "```",
        "",
        "Add `--provider fake` to run without downloading a model. The fake provider "
        "is deterministic but not semantic, so its dense numbers measure plumbing "
        "rather than retrieval quality.",
        "",
    ]
    return "\n".join(lines)


def _weak_case_section(outcomes: list[QueryOutcome]) -> list[str]:
    """Queries where hybrid failed to put anything relevant near the top."""
    weak = [
        outcome
        for outcome in outcomes
        if outcome.mode == "hybrid" and outcome.query.relevant and outcome.reciprocal_rank < 0.5
    ]
    lines = ["", "## Weak and failed cases (hybrid)", ""]
    if not weak:
        lines.append("Every labelled query placed a relevant claim at rank 1 or 2.")
        return lines

    lines.append("| Query | Category | Relevant | Top 5 retrieved | RR |")
    lines.append("| --- | --- | --- | --- | --- |")
    for outcome in sorted(weak, key=lambda item: item.reciprocal_rank):
        relevant = ", ".join(sorted(f"{d}#{n}" for d, n in outcome.query.relevant))
        top = ", ".join(f"{d}#{n}" for d, n in outcome.retrieved[:5]) or "(nothing)"
        lines.append(
            f"| `{outcome.query.id}` | {outcome.query.category} | {relevant} | {top} | "
            f"{outcome.reciprocal_rank:.2f} |"
        )
    return lines


def _regression_section(
    summaries: dict[str, MetricSummary], outcomes: list[QueryOutcome]
) -> list[str]:
    """Where fusing did worse than the better single channel.

    This section exists because the headline table can hide a real cost of
    fusion. RRF interleaves two lists, so a claim that one channel ranked fourth
    can be pushed past the cutoff by the other channel's confident-but-wrong
    candidates. Reporting only MRR - which looks at the *first* relevant hit -
    would never show it, and the honest thing is to look for it deliberately
    rather than to let the aggregate flatter the design being proposed.
    """
    from evals.metrics import recall_at_k

    lines = ["", "## Where hybrid loses to a single channel", ""]

    deficits = [
        (mode, metric, getattr(summaries[mode], metric) - getattr(summaries["hybrid"], metric))
        for mode in ("dense", "lexical")
        for metric in ("recall_at_1", "recall_at_3", "recall_at_5", "mrr_at_10")
        if getattr(summaries[mode], metric) > getattr(summaries["hybrid"], metric) + 1e-9
    ]

    if not deficits:
        lines.append("Hybrid matched or beat both single channels on every reported metric.")
    else:
        lines.append("| Metric | Better channel | That channel | Hybrid | Difference |")
        lines.append("| --- | --- | --- | --- | --- |")
        for mode, metric, delta in sorted(deficits, key=lambda item: -item[2]):
            lines.append(
                f"| {metric} | {mode} | {getattr(summaries[mode], metric):.3f} | "
                f"{getattr(summaries['hybrid'], metric):.3f} | -{delta:.3f} |"
            )

    by_query: dict[tuple[str, str], QueryOutcome] = {
        (outcome.query.id, outcome.mode): outcome for outcome in outcomes
    }
    losers: list[str] = []
    for outcome in outcomes:
        if outcome.mode != "hybrid" or not outcome.query.relevant:
            continue
        hybrid_recall = recall_at_k(outcome.retrieved, outcome.query.relevant, 5)
        for mode in ("dense", "lexical"):
            other = by_query.get((outcome.query.id, mode))
            if other is None:
                continue
            if recall_at_k(other.retrieved, other.query.relevant, 5) > hybrid_recall + 1e-9:
                losers.append(
                    f"- `{outcome.query.id}` ({outcome.query.category}): {mode} Recall@5 "
                    f"{recall_at_k(other.retrieved, other.query.relevant, 5):.2f} vs hybrid "
                    f"{hybrid_recall:.2f}"
                )

    if losers:
        lines += ["", "Individual queries where a single channel had better Recall@5:", ""]
        lines += sorted(set(losers))

    return lines


def _print_summary(summaries: dict[str, MetricSummary], output_dir: Path) -> None:
    print(f"{'mode':<9} {'R@1':>7} {'R@3':>7} {'R@5':>7} {'MRR@10':>7}")
    for mode in MODES:
        s = summaries[mode]
        print(
            f"{mode:<9} {s.recall_at_1:>7.3f} {s.recall_at_3:>7.3f} "
            f"{s.recall_at_5:>7.3f} {s.mrr_at_10:>7.3f}"
        )
    print(f"\nWrote {output_dir / 'results.json'} and {output_dir / 'REPORT.md'}")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"evaluation aborted: {message}")


if __name__ == "__main__":
    sys.exit(main())
