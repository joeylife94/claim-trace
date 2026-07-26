# ClaimTrace API

FastAPI backend for ClaimTrace. Phase 1 scope is the service skeleton only:
operational probes, system metadata, configuration, and the migration pipeline.

## Layout

| Path | Responsibility |
| --- | --- |
| `src/claimtrace_api/core/` | Settings (`pydantic-settings`), error taxonomy, logging setup |
| `src/claimtrace_api/api/` | Routers, dependencies, versioned endpoints under `v1/` |
| `src/claimtrace_api/services/` | Use cases: ingestion, claim parsing |
| `src/claimtrace_api/parsing/` | `DocumentParser` (PDF text) and `parsing/claims/` (`ClaimParser`) |
| `src/claimtrace_api/storage/` | `FileStorage` protocol and the local implementation |
| `src/claimtrace_api/db/` | Engine, session factory, ORM models, health probe |
| `src/claimtrace_api/schemas/` | Pydantic request/response models, including locators |
| `alembic/` | Migration environment and versions |
| `tests/` | pytest suite; the `integration` tier needs PostgreSQL and skips without it |

Dependencies point inward: `parsing/` and `storage/` know nothing about FastAPI,
SQLAlchemy, or each other. `services/` composes them, `api/` only translates HTTP.

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
| GET | `/docs` | OpenAPI UI (disabled when `ENVIRONMENT=production`). |

Claim parsing never modifies `documents.status`, and a document with no
detectable claims completes with status `no_claims_found` rather than an error.

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

Configuration is read from environment variables, falling back to the repository
root `.env`. See `.env.example` for the supported keys.
