# ClaimTrace

An on-premise RAG service for patent claim decomposition, evidence retrieval, and
document comparison.

> **MVP portfolio project.** ClaimTrace is built to demonstrate retrieval
> engineering practice. It does **not** provide legal advice and does **not**
> determine patent infringement, validity, or patentability. Any output is a
> textual correspondence between documents and must be reviewed by a qualified
> professional before it informs a decision.

---

## Purpose

Patent claim analysis is a citation problem before it is a language problem. A
claim has to be broken into its elements, and each element has to be matched
against passages in other documents - with the passage location preserved, so a
reviewer can verify every statement. ClaimTrace is being built around that
constraint: nothing is asserted that cannot be traced back to a stored source
location, and the whole system runs on-premise, because patent material is
routinely confidential.

## Current implementation scope

This repository is at **Phase 1: foundation**. What exists is the runnable skeleton
of the system - the service boundaries, configuration, database migration pipeline,
container environment, and quality gates.

**Implemented**

- FastAPI backend: `GET /health`, `GET /ready`, `GET /api/v1/system/info`
- Environment-driven configuration with no hardcoded credentials
- PostgreSQL 17 with the pgvector extension enabled by an Alembic baseline
- Next.js landing page that reads live API and database status from the backend
- `docker compose` development environment (api, web, postgres) with health checks
- Backend test suite requiring no database, network, or model provider
- Architecture and roadmap documentation

**Not implemented yet** - deliberately, see [docs/ROADMAP.md](docs/ROADMAP.md):
document upload, PDF/OCR parsing, chunking, embeddings, vector search, hybrid
retrieval, reranking, LLM integration, claim decomposition, evidence comparison,
evaluation, authentication, and any deployment tooling.

## Architecture overview

```
browser ──▶ web (Next.js, :3000) ──HTTP──▶ api (FastAPI, :8000) ──▶ postgres + pgvector (:5432)
```

```
claim-trace/
├── apps/
│   ├── api/            FastAPI service, Alembic migrations, pytest suite
│   └── web/            Next.js App Router frontend
├── packages/           reserved for code shared by two or more apps (empty)
├── infra/              PostgreSQL init SQL and other infrastructure assets
├── docs/               ARCHITECTURE.md, ROADMAP.md
├── tests/              cross-service tests (see tests/README.md)
├── docker-compose.yml  local development environment
├── Makefile            developer commands
└── .env.example        environment template
```

Component responsibilities, request flows, configuration strategy, and the
extension points reserved for parsing, embeddings, retrieval, reranking, LLM
providers, and evaluation are documented in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Technology stack

| Layer | Choice |
| --- | --- |
| Backend | Python 3.12, FastAPI, Pydantic v2 + pydantic-settings, SQLAlchemy 2.x (async), Alembic, psycopg 3, uvicorn |
| Database | PostgreSQL 17 + pgvector |
| Frontend | Next.js (App Router), React, TypeScript, ESLint |
| Tooling | uv (Python dependencies), ruff (lint/format), pytest, npm, Docker Compose, Make |

## Prerequisites

- Docker Desktop or Docker Engine with the Compose v2 plugin
- Optional, for running the apps directly on the host:
  - [uv](https://docs.astral.sh/uv/) and Python 3.12
  - Node.js 22+ and npm
  - GNU Make (the Makefile is a convenience; every target maps to a plain command)

## Local execution

### With Docker (recommended)

```bash
cp .env.example .env        # or: make init
docker compose up --build   # or: make up
```

Then apply the database migrations once:

```bash
docker compose run --rm api alembic upgrade head   # or: make migrate
```

| Service | URL | Notes |
| --- | --- | --- |
| Web | http://localhost:3000 | Landing page with live status panel |
| API | http://localhost:8000 | `/health`, `/ready`, `/api/v1/system/info` |
| API docs | http://localhost:8000/docs | Disabled when `ENVIRONMENT=production` |
| PostgreSQL | localhost:5432 | Credentials from `.env` |

Quick verification:

```bash
curl http://localhost:8000/health              # {"status":"ok"}
curl http://localhost:8000/ready               # {"status":"ready","dependencies":{"postgres":"ok"}}
curl http://localhost:8000/api/v1/system/info  # {"name":"ClaimTrace API","version":"0.1.0",...}
```

Ports are configurable through `API_PORT`, `WEB_PORT`, and `POSTGRES_PORT` in
`.env`.

### Without Docker

The API needs a reachable PostgreSQL instance with pgvector for `/ready` to report
`ready`; `/health` works regardless.

```bash
# backend
cd apps/api
uv sync --extra dev
uv run alembic upgrade head
uv run uvicorn claimtrace_api.main:app --reload --port 8000

# frontend (separate shell)
cd apps/web
npm install
npm run dev
```

## Developer commands

`make help` lists every target. The most used ones:

| Command | Action |
| --- | --- |
| `make init` | Create `.env` from `.env.example` (never overwrites) |
| `make up` / `make up-detached` | Build and start all services |
| `make down` | Stop containers, keep the database volume |
| `make logs` / `make ps` | Follow logs / show service health |
| `make migrate` | `alembic upgrade head` in the api container |
| `make migration m="..."` | Autogenerate a migration |
| `make psql` | psql shell on the postgres container |
| `make test` | Backend test suite (`uv run pytest`) |
| `make lint` / `make format` / `make fmt-check` | ruff check / format / format check |
| `make web-lint` / `make web-typecheck` | ESLint / `tsc --noEmit` |
| `make check` | All quality gates |
| `make clean` | Remove containers, volumes, and local build artifacts |

Equivalent plain commands, if Make is unavailable:

```bash
cd apps/api && uv run pytest
cd apps/api && uv run ruff check .
cd apps/api && uv run ruff format --check .
cd apps/web && npm run lint
cd apps/web && npm run typecheck
docker compose run --rm api alembic upgrade head
```

## Environment variables

Copy `.env.example` to `.env` and adjust as needed. `.env` is git-ignored; the
example file contains local placeholders only.

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_NAME` | `ClaimTrace API` | Reported by `/api/v1/system/info` |
| `APP_VERSION` | `0.1.0` | Reported by `/api/v1/system/info` |
| `ENVIRONMENT` | `development` | `development`/`test`/`staging`/`production`; `production` disables `/docs` |
| `LOG_LEVEL` | `INFO` | Root log level |
| `LOG_FORMAT` | `text` | `text` or `json` (one JSON object per line) |
| `API_V1_PREFIX` | `/api/v1` | Versioned API mount point |
| `CORS_ALLOW_ORIGINS` | `http://localhost:3000` | Comma-separated allowed browser origins |
| `CORS_ALLOW_CREDENTIALS` | `false` | Whether credentialed cross-origin requests are allowed |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | `claimtrace` / placeholder / `claimtrace` | Database credentials, shared by the api and postgres services |
| `POSTGRES_HOST` / `POSTGRES_PORT` | `localhost` / `5432` | Database location (Compose overrides the host with `postgres`) |
| `DATABASE_URL` | unset | Full DSN override; wins over the discrete `POSTGRES_*` values |
| `API_PORT` / `WEB_PORT` | `8000` / `3000` | Published host ports |
| `API_INTERNAL_BASE_URL` | `http://api:8000` | API address used by the Next.js server runtime |
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000` | Fallback, and the base URL any browser-side call would use |

Only `NEXT_PUBLIC_*` variables reach the browser bundle. Never put a credential
behind that prefix.

## Current limitations

- No patent-domain functionality yet: no upload, parsing, embedding, retrieval, or
  analysis. Endpoints are operational and informational only.
- No authentication or authorisation; do not expose this service beyond a trusted
  network.
- The web container runs `next dev`. There is no production image, and no CI
  pipeline.
- Migrations are applied explicitly (`make migrate`) rather than on container
  start, so a fresh environment has an empty schema until you run them.
- `/ready` checks PostgreSQL connectivity only; it does not verify that migrations
  have been applied.
- The Alembic baseline creates a single infrastructure table (`app_metadata`).
  Domain schema is intentionally absent.
- No request tracing, rate limiting, or background job processing.

## Planned next phases

Summarised from [docs/ROADMAP.md](docs/ROADMAP.md):

| Phase | Focus |
| --- | --- |
| 1 | Foundation - **complete** |
| 2 | Patent document ingestion and structural parsing (sections, claim sets, source locators) |
| 3 | Chunking, embeddings, pgvector indexing, hybrid retrieval, optional reranking |
| 4 | Local LLM provider abstraction with a deterministic fake for tests |
| 5 | Claim decomposition and element-level evidence comparison, with grounding enforced |
| 6 | Offline evaluation harness, regression gates, reproducible demonstration |

## License

MIT - see [LICENSE](LICENSE).
