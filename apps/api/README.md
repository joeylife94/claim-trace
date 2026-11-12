# ClaimTrace API

FastAPI backend for ClaimTrace. It covers document ingestion (including retry of
a failed ingestion), deterministic Korean claim structural parsing, claim-level
hybrid retrieval, a local LLM boundary with evidence-grounded answers, claim
comparison, claim element decomposition with append-only human review,
description-evidence derivation and retrieval, and persistent analyst Cases.
Several of these are API-only: the web app has no UI for Cases or description
search (see [API-only capabilities](#api-only-capabilities)).

## Layout

| Path | Responsibility |
| --- | --- |
| `src/claimtrace_api/core/` | Settings (`pydantic-settings`), error taxonomy, logging setup |
| `src/claimtrace_api/api/` | Routers, dependencies, versioned endpoints under `v1/` |
| `src/claimtrace_api/services/` | Use cases: `ingestion`, `claim_parsing`, `claim_indexing`, `claim_search`, `claim_elements`, `claim_element_reviews`, `claim_comparison`, `description_evidence`, `cases`, `case_grounded_results`, `grounded_generation`, `llm_generation`, `source_resolution` |
| `src/claimtrace_api/parsing/` | `DocumentParser` (PDF text, `pymupdf_parser.py`), `parsing/claims/` (`ClaimParser`), and `elements.py` (deterministic claim element parser) |
| `src/claimtrace_api/indexing/` | Search-text normalisation, `IndexProfile`, and `EmbeddingProvider` implementations |
| `src/claimtrace_api/retrieval/` | Dense (pgvector), lexical (FTS + trigram), and Reciprocal Rank Fusion |
| `src/claimtrace_api/llm/` | The local LLM boundary: provider protocol, `fake`, `ollama` and `openai_compatible` providers, retry, structured-output handling |
| `src/claimtrace_api/grounding/` | Request-local evidence catalog, deterministic prompt/context builder, the model output contract (`draft.py`), and post-generation citation validation for grounded answers |
| `src/claimtrace_api/storage/` | `FileStorage` protocol and the local implementation |
| `src/claimtrace_api/db/` | Engine, session factory, health probe, and ORM models for the `0001`-`0006` tables (`models.py`, `element_models.py`, `review_models.py`) |
| `src/claimtrace_api/schemas/` | Pydantic request/response models, including locators |
| `alembic/` | Migration environment and versions (linear chain `0001` to `0009`) |
| `tests/` | pytest suite; the `integration` tier needs PostgreSQL and skips without it. `tests/d3_acceptance/` and `tests/d4_acceptance/` hold the real-public-corpus acceptance tests, excluded from default collection (see [Tests](#tests)) |
| `evals/` | Offline retrieval evaluation and grounded-generation evaluation over synthetic Korean corpora |

Dependencies point inward: `parsing/`, `storage/`, and `indexing/embeddings/`
know nothing about FastAPI, SQLAlchemy, or each other. `services/` composes them,
`api/` only translates HTTP. `retrieval/` is the one exception and deliberately
so: dense and lexical retrieval *are* SQL, and pretending otherwise would mean
pulling every vector into Python to compare it.

The tables added by migrations `0007` (description evidence), `0008` and `0009`
(analyst Cases and their grounded results) have no ORM model; `services/description_evidence.py`,
`services/cases.py` and `services/case_grounded_results.py` use raw SQL against them.

## Endpoints

33 operations: 2 health probes at the root and 31 under the `/api/v1` prefix
(`API_V1_PREFIX`).

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/health` | Liveness. Never touches PostgreSQL. |
| GET | `/ready` | Readiness. `503` when PostgreSQL is unreachable. |
| GET | `/api/v1/system/info` | Name, version, environment. |
| POST | `/api/v1/documents` | Upload a PDF. `200` on a duplicate digest. |
| POST | `/api/v1/documents/{id}/retry` | Retry one `failed` ingestion from its persisted original. `409` for any non-failed state. |
| GET | `/api/v1/documents` | Documents, newest first. |
| GET | `/api/v1/documents/{id}` | One document's ingestion record. |
| GET | `/api/v1/documents/{id}/pages` | Extracted page text with locators. |
| POST | `/api/v1/documents/{id}/claims/parse` | Parse claim structure. `200` when this parser version already ran, `409` when ingestion is not completed. |
| GET | `/api/v1/documents/{id}/claims` | Parse result with ordered claims, dependencies, and spans. |
| GET | `/api/v1/documents/{id}/claims/{claim_number}` | One claim. |
| POST | `/api/v1/documents/{id}/claims/index` | Embed and index the claims. `200` when this retrieval profile already ran, `409` when parsing is not completed, `503` when the model cannot be loaded. |
| GET | `/api/v1/documents/{id}/claims/index` | The most recent index run and its retrieval profile. |
| POST | `/api/v1/documents/{id}/claims/{claim_number}/elements/decompose` | Deterministic, source-backed element decomposition of one persisted claim. `201` for a new run, `200` when the same request already ran. Machine-produced review material, not a legal conclusion. |
| POST | `/api/v1/element-decomposition-runs/{run_id}/reviews` | Append a human review (accepted or needs-correction) to one exact decomposition run. The machine decomposition is not changed. |
| GET | `/api/v1/element-decomposition-runs/{run_id}/reviews` | Review history for one decomposition run. |
| POST | `/api/v1/documents/{id}/descriptions/derive` | Derive source-verifiable description segments from persisted page text. `201` for a new run, `200` when it already ran, `409` when the document is not completed. |
| POST | `/api/v1/documents/{id}/descriptions/index` | Embed and index the derived description segments (derives first if needed). `201` for a new index, `200` when it already ran, `409` when the document is not completed. |
| POST | `/api/v1/search/descriptions` | Hybrid, dense, or lexical search over description segments. A separate endpoint, not merged into claim search. Results carry canonical locators and a `source_url` that opens the range in the document page. |
| POST | `/api/v1/search/claims` | Hybrid, dense, or lexical claim search. |
| POST | `/api/v1/compare/claims` | Compare one target claim against one reference document. Retrieval only: the target claim text is the query, restricted to that one document; matches are textual correspondences with locators. |
| GET | `/api/v1/llm/status` | Local LLM provider configuration and reachability. Always `200`, including when the provider is unreachable. |
| POST | `/api/v1/llm/diagnostics/generate` | Plain-text generation for development diagnostics. `404` when `LLM_DIAGNOSTICS_ENABLED` resolves to off (on in development, off elsewhere by default). |
| POST | `/api/v1/llm/diagnostics/structured` | Schema-constrained generation against one built-in smoke-test schema; same gating as above. |
| POST | `/api/v1/grounded/answers` | Answer a question from indexed claim text. Stateless: nothing is stored. Only statements whose citations resolve to stored source text are returned; `insufficient_evidence` is a normal `200`. |
| POST | `/api/v1/cases` | Create an analyst Case (`201`). |
| GET | `/api/v1/cases` | List Cases. |
| GET | `/api/v1/cases/{case_id}` | One Case. |
| PUT | `/api/v1/cases/{case_id}/documents/{document_id}` | Associate an existing document with a Case. The response reports whether the association changed. |
| DELETE | `/api/v1/cases/{case_id}/documents/{document_id}` | Remove the association (`204`). |
| POST | `/api/v1/cases/{case_id}/grounded-results` | Run a grounded answer scoped to the Case's documents and persist it with its resolved citations (`201`). An identical request in the same Case returns the stored result. `409` when the requested documents fall outside the Case's scope or the Case has no documents. |
| GET | `/api/v1/cases/{case_id}/grounded-results` | Summaries of the Case's stored grounded results. |
| GET | `/api/v1/cases/{case_id}/grounded-results/{result_id}` | Reopen one stored result. |
| GET | `/docs` | OpenAPI UI (disabled when `ENVIRONMENT=production`). |

`/docs` and `/openapi.json` are framework routes, not counted among the 33.

### API-only capabilities

No page, component, or browser test in `apps/web` calls the Case endpoints or the
description endpoints, so they are reachable only through the API (`/docs`, `curl`,
or the pytest suites). The web app does expose the document, search, grounded,
compare, LLM, and review pages. A description-search result's `source_url` is a
link into the existing document page (`/documents/{id}?page=&start=&end=`); there
is no dedicated description-search or Case UI. Grounded answers, with or without a
Case, are generated from claims only: description evidence is not used as grounded
evidence.

Failed-ingestion retry is intentionally narrow and operator-driven. It reuses the
existing document row, SHA-256 digest, storage key, and persisted original bytes,
then re-enters the same parse/page-persistence path. The endpoint accepts no
replacement file and does not add a worker, queue, retry schedule, OCR fallback,
or automatic resilience policy. A successful retry clears the prior ingestion
error metadata; a new failure remains terminal and traceable on the same document.

Ingestion status moves `uploaded` -> `processing` -> `completed` or `failed`;
retry adds `failed` -> `processing`. Ingestion is the only service that sets
`documents.status`. Claim parsing, claim indexing, element decomposition, and
description derivation each keep their own run records and never modify it, so
the lifecycles stay separate. A document with no detectable claims completes
claim parsing with status `no_claims_found` rather than an error, and is then
refused for claim indexing with `claim_parse_not_completed` - there is nothing to
index, and reporting that as an empty success would make it look indexed.

PDF input is text-layer only. A PDF is rejected with the `no_extractable_text`
error code, and the document is recorded as `failed`, when it yields fewer than
`MIN_EXTRACTED_CHARACTERS` (default 32) characters in total, which is how a
scanned or image-only PDF is caught, or when some pages have extractable text and
others have none (`classify_pdf_text_layer` in `parsing/pymupdf_parser.py`; a blank
or drawings-only page among text pages is enough). There is no OCR. The
classification looks only at extracted text, so a scan that already carries an
embedded text layer is treated as text.

## Local commands

```bash
uv sync --extra dev            # create .venv and install dependencies
uv run uvicorn claimtrace_api.main:app --reload --port 8000
uv run pytest                  # tests (PostgreSQL tier skips itself if absent)
uv run pytest -m "not integration"   # database-free tier only
uv run ruff check .            # lint
uv run ruff format --check .   # format check
uv run alembic upgrade head    # migrations (requires a reachable PostgreSQL)
```

Equivalent in Docker, which is how the PostgreSQL-backed tier is normally run:

```bash
docker compose run --rm api pytest
docker compose run --rm --no-deps api ruff check .
docker compose run --rm --no-deps api ruff format --check .
```

## Tests

No default test downloads or executes a real embedding model. The suite runs
against `FakeEmbeddingProvider`, which satisfies the same protocol
deterministically, so every layer above the boundary is exercised for real. The
real model is used by `python -m evals.run` and by the running service.

`pytest` collects `tests/` only. `tests/d3_acceptance/` and
`tests/d4_acceptance/` are listed under `norecursedirs` in `pyproject.toml`, so
default runs never collect them. They are `integration` tests that run against
two real public Korean patent PDFs which are hash-pinned in
`../../docs/real-public-corpus/manifest.json`, downloaded at run time, and never
committed. They are invoked explicitly by the `Progression D3 Real Public Corpus`
and `Progression D4 Description Evidence` workflows, for example:

```bash
pytest tests/d3_acceptance/test_real_public_corpus.py -m integration
pytest tests/d4_acceptance/test_real_public_description.py -m integration
```

They need the PDFs on disk (the workflows download them and check the hashes with
`scripts/verify-d3-real-corpus-inputs.sh` first) and read their locations from
`CLAIMTRACE_D3_CORPUS_DIR`, `CLAIMTRACE_D3_MANIFEST`, `CLAIMTRACE_D3_EVIDENCE_DIR`
(D4: the `CLAIMTRACE_D4_*` equivalents), so they are not a casual local command.

## Evaluations

Two offline evaluations over synthetic Korean corpora live in `evals/`; see
[`evals/README.md`](evals/README.md) for datasets, metrics, and limits.

```bash
docker compose run --rm api python -m evals.run              # retrieval, configured model
docker compose run --rm api python -m evals.run --provider fake
docker compose run --rm api python -m evals.grounded_run                 # grounded, deterministic tier
docker compose run --rm api python -m evals.grounded_run --tier ollama   # grounded, real local model
```

Both go through the real HTTP API and write under `evals/results/`
(`results.json` and `REPORT.md`; `grounded/results-<tier>.json` and
`grounded/REPORT-<tier>.md`). The committed result files record earlier runs; CI does
not commit refreshed copies. The `Makefile` target `make verify-deterministic-regression`
(run from the repository root) re-runs both evaluations with the fake provider, asserts a
pinned baseline, and **overwrites** the committed result files with fake-provider
output. It is the enforced regression gate; see `evals/README.md` for what it pins
and why its numbers differ from the committed files.

Configuration is read from environment variables, falling back to the repository
root `.env`. See `.env.example` for the supported keys.
