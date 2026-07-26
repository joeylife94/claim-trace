# ClaimTrace

An on-premise RAG service for patent claim decomposition, evidence retrieval, and
document comparison.

> **MVP portfolio project.** ClaimTrace is built to demonstrate retrieval
> engineering practice. It does **not** provide legal advice, does **not**
> determine patent infringement, does **not** determine validity, and does
> **not** determine patentability. Claim classifications such as "dependent" are
> descriptions of document structure, not legal characterisations. Any output is
> a textual correspondence between documents and must be reviewed by a qualified
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

This repository is at **Phase 2B: deterministic claim structural parsing**. A
text-based Korean patent PDF can be uploaded, stored, parsed into page text, then
parsed again into a claim graph - claim numbers, types, dependencies, and exact
page-anchored source spans for every claim.

**Implemented**

- FastAPI backend: `GET /health`, `GET /ready`, `GET /api/v1/system/info`
- Document ingestion: `POST /api/v1/documents`, plus list, detail, and page text
  endpoints under `/api/v1/documents`
- Upload validation (extension, MIME type, `%PDF-` signature, size limit, empty
  file, corrupted PDF, encrypted PDF) with stable error codes
- Content-addressed local file storage behind a `FileStorage` protocol
- SHA-256 identity with a documented duplicate policy
- `DocumentParser` protocol with a PyMuPDF implementation for digital PDFs
- Page-level text persistence and `SourceLocator` provenance
  (`document_id`, `page_number`, `start_char`, `end_char`)
- Deterministic Korean claim structural parsing: `ClaimParser` protocol with a
  rule-based implementation, claim boundaries, numbering, classification, and
  dependency edges
- Claim source stored as ordered page-relative spans, including claims that cross
  a page break
- A claim parsing lifecycle separate from ingestion, with `no_claims_found` as an
  explicit outcome and idempotency per parser version
- Claim endpoints under `/api/v1/documents/{id}/claims`
- PostgreSQL 17 + pgvector, Alembic revisions `0001` (baseline), `0002`
  (ingestion) and `0003` (claim parsing)
- Next.js UI: live system status, PDF upload, document list, per-page text viewer,
  claim structure with source spans that highlight the exact range
- `docker compose` development environment (api, web, postgres) with health checks
- Test suite that needs no network or model provider; the PostgreSQL-backed tier
  skips itself when no database is reachable
- Architecture and roadmap documentation

**Not implemented yet** - deliberately, see [docs/ROADMAP.md](docs/ROADMAP.md):
OCR and scanned-document recovery, bibliographic/abstract/description section
parsing, claim element decomposition, chunking, embeddings, vector search,
keyword and hybrid retrieval, reranking, LLM integration, evidence comparison,
evaluation, authentication, background queues, and any deployment tooling.

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
| Backend | Python 3.12, FastAPI, Pydantic v2 + pydantic-settings, SQLAlchemy 2.x (async), Alembic, psycopg 3, uvicorn, PyMuPDF |
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
| Documents | http://localhost:3000/documents | Upload a PDF, browse extracted text |
| API | http://localhost:8000 | Operational, system, and document endpoints |
| API docs | http://localhost:8000/docs | Disabled when `ENVIRONMENT=production` |
| PostgreSQL | localhost:5432 | Credentials from `.env` |

Quick verification:

```bash
curl http://localhost:8000/health              # {"status":"ok"}
curl http://localhost:8000/ready               # {"status":"ready","dependencies":{"postgres":"ok"}}
curl http://localhost:8000/api/v1/system/info  # {"name":"ClaimTrace API","version":"0.1.0",...}

# Ingest a PDF and read its text back
curl -F "file=@your-document.pdf;type=application/pdf" \
     http://localhost:8000/api/v1/documents
curl http://localhost:8000/api/v1/documents
curl http://localhost:8000/api/v1/documents/<id>/pages

# Parse its claim structure and read the claim graph
curl -X POST http://localhost:8000/api/v1/documents/<id>/claims/parse
curl http://localhost:8000/api/v1/documents/<id>/claims
curl http://localhost:8000/api/v1/documents/<id>/claims/1
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
| `make test-docker` | Backend test suite inside the api container, including the PostgreSQL tier |
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
| `STORAGE_ROOT` | `/data/uploads` | Where uploaded originals are written. Must be outside the repository |
| `UPLOAD_MAX_BYTES` | `20971520` (20 MB) | Maximum accepted upload, enforced while streaming |
| `UPLOAD_ALLOWED_CONTENT_TYPES` | `application/pdf` | Comma-separated accepted MIME types |
| `UPLOAD_ALLOWED_EXTENSIONS` | `.pdf` | Comma-separated accepted extensions |
| `MIN_EXTRACTED_CHARACTERS` | `32` | Below this document-wide total, a PDF is treated as having no text layer |

Only `NEXT_PUBLIC_*` variables reach the browser bundle. Never put a credential
behind that prefix.

## Document ingestion

### What happens to an upload

The request body is streamed with a hard size ceiling, then validated by extension,
declared content type, and the `%PDF-` signature - the last because the first two
are supplied by the client. The bytes are hashed, checked against existing
documents, written to content-addressed storage, and registered as `uploaded`.
Parsing then extracts text page by page, and the pages plus the `completed` status
are committed in a single transaction, so a half-written page set can never appear
as a finished document.

Full flow, schema, and rationale: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) §7.

### Duplicate policy

A document is identified by the SHA-256 of its bytes, and that column is unique.
Re-uploading the same file returns **200** with the existing record instead of
creating a second document or storing a second copy - including when the existing
record is a failed one. The filename is not part of identity: the same PDF under a
different name is the same document, and the first upload's filename is kept.

### Text-based PDFs only

There is no OCR in this phase. A PDF whose pages are images yields no text, and if
a document produces fewer than `MIN_EXTRACTED_CHARACTERS` characters in total it is
recorded as `failed` with error code `no_extractable_text` and a message asking for
a PDF with a text layer. An empty result is reported as a failure rather than
ingested as a document with nothing to cite.

### Error codes

Clients branch on `error_code`, never on the message text.

| Code | Status | Meaning |
| --- | --- | --- |
| `unsupported_file_type` | 415 | Not a PDF by extension, declared type, or signature |
| `file_too_large` | 413 | Exceeds `UPLOAD_MAX_BYTES` |
| `empty_file` | 400 | Zero bytes |
| `malformed_pdf` | 422 | Unreadable or zero-page PDF |
| `encrypted_pdf` | 422 | Password protected |
| `no_extractable_text` | 422 | Scanned or image-only; no text layer |
| `document_not_found` | 404 | Unknown document id |

The last three arrive after the file has been stored, so the response carries the
persisted, failed document record - the failure is traceable, not just reported.

### Source locators

Every page comes back with a locator: `(document_id, page_number, start_char,
end_char)`, a half-open span over the page text **as stored**. This is the
coordinate system for all future evidence citation, because a page is something a
human can verify against the original PDF and it survives every change to chunking,
embeddings, and retrieval strategy. Offsets index persisted text rather than a
transient parser buffer, so a span recorded today still resolves to the same
characters later.

## Claim structural parsing

Once a document has ingested, `POST /api/v1/documents/{id}/claims/parse` extracts
its claim structure using **deterministic rules only** - no model, no embedding,
no legal reasoning. The same page text always produces the same claim graph.

Full rules, schema, and rationale: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) §8.

### Supported claim patterns

Primary support is Korean. Headings are matched at the start of a line:
`【청구항 1】`, `[청구항 1]`, `〔청구항 1〕`, `청구항 1`, `청구항 1.`, `청구항 제1항`,
and full-width digits (`청구항 １`). A minimal, line-anchored `Claim 1` English
fallback exists and is deliberately isolated.

Dependencies require a claim reference **and** a dependency particle
(`에 있어서`, `에 따른`, `에 따라`, `에 기재된`, `에 기재의`, `에 의한`):

| Expression | Edges |
| --- | --- |
| `제1항에 있어서` / `청구항 1에 있어서` / `제1항에 따른` | → 1 |
| `제1항 또는 제2항에 있어서` | → 1, → 2 |
| `제1항 및 제2항에 있어서` | → 1, → 2 |
| `제1항 내지 제3항 중 어느 한 항에 있어서` | → 1, → 2, → 3 |

Requiring the particle is what keeps arbitrary technical numbers - `온도 100도`,
`도 2에 도시된`, `3개의 부재` - out of the dependency graph.

### Classification

`independent` (no reference), `dependent` (one resolved reference),
`multiple_dependent` (two or more, including an expanded range), or `unknown`
when references were detected but none could be resolved. `unknown` is used
instead of a guess. Classification is syntactic and is **not** a legal
characterisation.

### Claims that cross a page break

A claim is stored as one or more ordered spans, one per page it touches:

```
Claim 3 · seq 0 · page 1 · [100, 125)
          seq 1 · page 2 · [0, 16)
```

Claim text is *defined* as those spans resolved against `document_pages.text` and
joined with a single `"\n"`. There is no flattened document offset anywhere; the
page locator from Phase 2A remains the only citation coordinate.

### Lifecycle, parser versioning, and idempotency

Claim parsing has its own lifecycle - `processing → completed | no_claims_found |
failed` - and **never changes `documents.status`**. A document that ingested
cleanly stays `completed` even if it turns out to contain no claims.

`no_claims_found` is an explicit status, not an empty success: "this document has
no claims" and "we could not parse it" call for different responses.

Results are unique per `(document, parser_name, parser_version)`. Re-running the
same version returns the existing result with **200** instead of **201**; a failed
or stranded attempt is retried in place; a future parser version creates a new
result beside the current one, so existing citations are never overwritten.

### Uploaded files are never committed

`STORAGE_ROOT` points outside the repository (a Docker volume by default), and
`.gitignore` refuses `*.pdf` and the usual data directories. No real patent document
is committed as a fixture; test PDFs are generated at runtime.

## Current limitations

- Structure stops at the claim graph. No bibliographic/abstract/description
  parsing, no claim element decomposition, no chunking, embeddings, retrieval, or
  analysis - see [docs/ROADMAP.md](docs/ROADMAP.md).
- Claim parsing supports Korean conventions plus a minimal English heading
  fallback. Other languages are not attempted.
- Claim parsing is deterministic and conservative: a document whose formatting it
  does not recognise reports `no_claims_found` rather than guessing.
- Text-based PDFs only. No OCR, and no recovery of scanned documents.
- No authentication or authorisation; do not expose this service beyond a trusted
  network. Anyone who can reach the API can upload and read every document.
- Uploads are not virus-scanned.
- Parsing is synchronous, and the whole file is held in memory while hashing and
  parsing. Both are bounded by `UPLOAD_MAX_BYTES` (20 MB by default).
- No re-parse or delete endpoint. Deleting a document row cascades to its pages,
  but the stored original is not garbage-collected by the application.
- Documents are immutable and unversioned: a revised PDF is simply a different
  document, with no link to the one it supersedes.
- The web container runs `next dev`. There is no production image, and no CI
  pipeline.
- Migrations are applied explicitly (`make migrate`) rather than on container
  start, so a fresh environment has an empty schema until you run them.
- `/ready` checks PostgreSQL connectivity only; it does not verify that migrations
  have been applied.
- No request tracing, rate limiting, or background job processing.

## Planned next phases

Summarised from [docs/ROADMAP.md](docs/ROADMAP.md):

| Phase | Focus |
| --- | --- |
| 1 | Foundation - **complete** |
| 2A | Document ingestion boundary and page-level provenance - **complete** |
| 2B | Deterministic claim structural parsing and dependency graph - **complete** |
| 2C | Claim element decomposition schema and deterministic review boundary |
| 3 | Chunking, embeddings, pgvector indexing, hybrid retrieval, optional reranking |
| 4 | Local LLM provider abstraction with a deterministic fake for tests |
| 5 | Claim decomposition and element-level evidence comparison, with grounding enforced |
| 6 | Offline evaluation harness, regression gates, reproducible demonstration |

## License

MIT - see [LICENSE](LICENSE).
