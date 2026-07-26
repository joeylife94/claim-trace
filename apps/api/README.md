# ClaimTrace API

FastAPI backend for ClaimTrace. Current scope: document ingestion, deterministic
Korean claim structural parsing, and claim-level hybrid retrieval.

## Layout

| Path | Responsibility |
| --- | --- |
| `src/claimtrace_api/core/` | Settings (`pydantic-settings`), error taxonomy, logging setup |
| `src/claimtrace_api/api/` | Routers, dependencies, versioned endpoints under `v1/` |
| `src/claimtrace_api/services/` | Use cases: ingestion, claim parsing, claim indexing, claim search |
| `src/claimtrace_api/parsing/` | `DocumentParser` (PDF text) and `parsing/claims/` (`ClaimParser`) |
| `src/claimtrace_api/indexing/` | Search-text normalisation, `IndexProfile`, and `EmbeddingProvider` implementations |
| `src/claimtrace_api/retrieval/` | Dense (pgvector), lexical (FTS + trigram), and Reciprocal Rank Fusion |
| `src/claimtrace_api/storage/` | `FileStorage` protocol and the local implementation |
| `src/claimtrace_api/db/` | Engine, session factory, ORM models, health probe |
| `src/claimtrace_api/schemas/` | Pydantic request/response models, including locators |
| `alembic/` | Migration environment and versions |
| `tests/` | pytest suite; the `integration` tier needs PostgreSQL and skips without it |
| `evals/` | Offline retrieval evaluation over a synthetic Korean corpus |

Dependencies point inward: `parsing/`, `storage/`, and `indexing/embeddings/`
know nothing about FastAPI, SQLAlchemy, or each other. `services/` composes them,
`api/` only translates HTTP. `retrieval/` is the one exception and deliberately
so: dense and lexical retrieval *are* SQL, and pretending otherwise would mean
pulling every vector into Python to compare it.

## Endpoints

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/health` | Liveness. Never touches PostgreSQL. |
| GET | `/ready` | Readiness. `503` when PostgreSQL is unreachable. |
| GET | `/api/v1/system/info` | Name, version, environment. |
| POST | `/api/v1/documents` | Upload a PDF. `200` on a duplicate digest. |
| GET | `/api/v1/documents` | Documents, newest first. |
| GET | `/api/v1/documents/{id}` | One document's ingestion record. |
| GET | `/api/v1/documents/{id}/pages` | Extracted page text with locators. |
| POST | `/api/v1/documents/{id}/claims/parse` | Parse claim structure. `200` when this parser version already ran, `409` when ingestion is not completed. |
| GET | `/api/v1/documents/{id}/claims` | Parse result with ordered claims, dependencies, and spans. |
| GET | `/api/v1/documents/{id}/claims/{claim_number}` | One claim. |
| POST | `/api/v1/documents/{id}/claims/index` | Embed and index the claims. `200` when this retrieval profile already ran, `409` when parsing is not completed, `503` when the model cannot be loaded. |
| GET | `/api/v1/documents/{id}/claims/index` | The most recent index run and its retrieval profile. |
| POST | `/api/v1/search/claims` | Hybrid, dense, or lexical claim search. |
| GET | `/docs` | OpenAPI UI (disabled when `ENVIRONMENT=production`). |

Three lifecycles stay separate: claim parsing never modifies `documents.status`,
and claim indexing modifies neither. A document with no detectable claims
completes with status `no_claims_found` rather than an error, and is then refused
for indexing with `claim_parse_not_completed` - there is nothing to index, and
reporting that as an empty success would make it look indexed.

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

No test downloads or executes a real embedding model. The suite runs against
`FakeEmbeddingProvider`, which satisfies the same protocol deterministically, so
every layer above the boundary is exercised for real. The real model is used by
`python -m evals.run` and by the running service.

## Retrieval evaluation

```bash
docker compose run --rm api python -m evals.run              # configured model
docker compose run --rm api python -m evals.run --provider fake
```

Uploads, parses, indexes, and searches a synthetic Korean corpus through the real
HTTP API, then writes `evals/results/results.json` and `evals/results/REPORT.md`.
There is no separate evaluation-only retrieval path.

Configuration is read from environment variables, falling back to the repository
root `.env`. See `.env.example` for the supported keys.
