# ClaimTrace

An on-premise RAG service for patent claim decomposition, evidence retrieval, and
document comparison.

> **MVP portfolio project.** ClaimTrace is built to demonstrate retrieval
> engineering practice. It does **not** provide legal advice, does **not**
> determine patent infringement, does **not** determine validity, and does
> **not** determine patentability, and does **not** determine novelty. Claim
> classifications such as "dependent" are descriptions of document structure, not
> legal characterisations. Any output is a textual correspondence between
> documents and must be reviewed by a qualified professional before it informs a
> decision. Text produced by a language model is model output, not a legal
> opinion, and the small model this project has been validated with is not fit
> for patent analysis.

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

This repository is at **Phase 4A-1: local LLM provider boundary**. A text-based
Korean patent PDF can be uploaded, stored, parsed into page text, parsed again
into a claim graph, indexed with a local multilingual embedding model, and then
searched - by meaning, by wording, or both - with every result resolving back to
the exact page and character range it came from.

Phase 4A-1 adds the ability to *generate* with a local model, and deliberately
nothing that uses it. There is no evidence-grounded answering, no claim analysis,
and no citation yet - that is Phase 4A-2. What exists is a provider boundary, an
Ollama adapter, an OpenAI-compatible (vLLM) adapter, a deterministic fake, and a
narrow diagnostics surface to prove it works.

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
- `EmbeddingProvider` protocol with two implementations: a real local
  sentence-transformers model and a deterministic hash provider that downloads
  nothing and is what the whole test suite runs against
- Claim-level indexing into pgvector, with its own lifecycle, a retrieval
  profile recorded per run, and idempotency per profile
- Dense retrieval (pgvector cosine, HNSW), Korean-aware lexical retrieval
  (PostgreSQL `simple` full-text plus `pg_trgm`), and Reciprocal Rank Fusion
- `POST /api/v1/search/claims` with `hybrid`, `dense`, and `lexical` modes,
  document scoping, and per-channel ranking metadata on every result
- PostgreSQL 17 + pgvector + pg_trgm, Alembic revisions `0001` (baseline),
  `0002` (ingestion), `0003` (claim parsing), `0004` (retrieval)
- Next.js UI: live system status, PDF upload, document list, per-page text viewer,
  claim structure with source spans that highlight the exact range, a retrieval
  index panel, and a `/search` page whose results link back into that viewer
- A reproducible retrieval evaluation over a synthetic Korean corpus, reporting
  Recall@1/3/5 and MRR@10 separately for dense, lexical, and hybrid
- `LLMProvider` protocol with three implementations - Ollama, an
  OpenAI-compatible local server (vLLM), and a deterministic fake that is the
  default and needs no model - plus a provider-neutral error taxonomy, retry
  policy, timeout control, and schema-constrained JSON output
- LLM diagnostics: `GET /api/v1/llm/status`, two development-only generation
  endpoints, and a `/llm` page showing provider, capabilities, and limits
- `docker compose` development environment (api, web, postgres) with health checks,
  plus an optional `llm` profile for a bundled Ollama
- Test suite that needs no network or model provider; the PostgreSQL-backed tier
  skips itself when no database is reachable
- Architecture and roadmap documentation

**Not implemented yet** - deliberately, see [docs/ROADMAP.md](docs/ROADMAP.md):
OCR and scanned-document recovery, bibliographic/abstract/description section
parsing, claim element decomposition, description-level chunking, reranking,
evidence-grounded generation and citation, evidence comparison, chat and
conversation history, streaming, tool calling, authentication, background queues,
and any deployment tooling.

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
| Search | http://localhost:3000/search | Hybrid claim search with source links |
| LLM | http://localhost:3000/llm | Provider status, capabilities, and diagnostics |
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

# Index its claims for retrieval, then search them
curl -X POST http://localhost:8000/api/v1/documents/<id>/claims/index
curl http://localhost:8000/api/v1/documents/<id>/claims/index
curl -X POST http://localhost:8000/api/v1/search/claims \
     -H 'Content-Type: application/json' \
     -d '{"query":"센서 데이터를 수집하는 통신 장치","mode":"hybrid","top_k":5}'

# Local LLM provider status (works with the default fake provider)
curl http://localhost:8000/api/v1/llm/status
```

The **first** index request downloads the embedding model (about 940 MB into the
`model_cache` volume) and takes roughly ten seconds longer than the rest. Later
requests reuse the resident model. To run entirely offline, set
`EMBEDDING_PROVIDER=fake` - deterministic, no download, and not semantic.

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
| `make eval` / `make eval-fake` | Retrieval evaluation, with the real model / the deterministic one |
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
| `EMBEDDING_PROVIDER` | `sentence-transformers` | `sentence-transformers` (real local model) or `fake` (deterministic, no download) |
| `EMBEDDING_MODEL` | `intfloat/multilingual-e5-small` | Must produce `EMBEDDING_DIMENSION`-wide vectors |
| `EMBEDDING_CACHE_DIR` | `/models` | Model weights. A Docker volume; never inside the repository |
| `EMBEDDING_DEVICE` | `cpu` | Only `cpu` is validated |
| `EMBEDDING_BATCH_SIZE` | `16` | Claims per encode call |
| `EMBEDDING_DIMENSION` | `384` | Must match the migrated `vector(n)` column |
| `DENSE_CANDIDATE_COUNT` / `LEXICAL_CANDIDATE_COUNT` | `30` / `30` | Candidates each channel contributes before fusion |
| `RRF_K` | `60` | Reciprocal Rank Fusion constant |
| `SEARCH_TOP_K_MAX` | `50` | Ceiling on `top_k` |
| `SEARCH_QUERY_MAX_LENGTH` | `512` | Ceiling on query length |
| `LLM_PROVIDER` | `fake` | `fake` (deterministic, no model), `ollama`, or `openai_compatible` |
| `LLM_OLLAMA_BASE_URL` | `http://host.docker.internal:11434` | Host Ollama by default; use `http://ollama:11434` with the `llm` profile |
| `LLM_OLLAMA_MODEL` | `qwen2.5:1.5b` | Small multilingual instruct model; a smoke test, not an analyst |
| `LLM_OPENAI_COMPATIBLE_BASE_URL` | `http://localhost:8000/v1` | Local or private server only; include the `/v1` prefix |
| `LLM_OPENAI_COMPATIBLE_MODEL` | `local-model` | Model id the server serves |
| `LLM_OPENAI_COMPATIBLE_API_KEY` | unset | Optional. Held as a secret: never logged, serialised, or returned |
| `LLM_STRUCTURED_OUTPUT_MODE` | `native_json_schema` | `native_json_schema`, `native_json_object`, `prompt_constrained_json`, or `unsupported`. Declared, not probed |
| `LLM_CONNECT_TIMEOUT_SECONDS` | `5` | Short, so a wrong port fails fast |
| `LLM_READ_TIMEOUT_SECONDS` | `120` | Generous: a small model on CPU is genuinely slow |
| `LLM_MAX_TIMEOUT_SECONDS` | `180` | Bounds one whole call including retries. A request may lower it, never raise it |
| `LLM_RETRY_MAX_ATTEMPTS` | `2` | Only failures that never reached the server are replayed |
| `LLM_MAX_PROMPT_CHARACTERS` | `8000` | Oversized prompts are rejected, not truncated |
| `LLM_MAX_OUTPUT_TOKENS` | `1024` | Ceiling on requested output; a larger request is clamped |
| `LLM_DIAGNOSTICS_ENABLED` | unset | Unset follows `ENVIRONMENT` (on in development, off elsewhere); `true`/`false` override |
| `OLLAMA_PORT` | `11434` | Host port published by the optional `llm` Compose profile |

Only `NEXT_PUBLIC_*` variables reach the browser bundle. Never put a credential
behind that prefix. `LLM_OPENAI_COMPATIBLE_API_KEY` is a `SecretStr`: it is
excluded from repr, from `model_dump()`, and from every log line, and no endpoint
returns it.

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

## Claim indexing and hybrid retrieval

Once a document's claims are parsed,
`POST /api/v1/documents/{id}/claims/index` embeds them and writes their search
records. `POST /api/v1/search/claims` then retrieves from two independent
channels and fuses the rankings.

Full design and rationale: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) §9.

### The two channels, and why they are fused by rank

**Dense** retrieval embeds the query with the same model that embedded the
claims and asks pgvector for the nearest vectors by cosine distance, using an
HNSW index. It finds paraphrases - a query about "배터리가 뜨거워지면 식혀 주는
장치" reaches a claim reciting a cooling circuit that shares almost no words with
it.

**Lexical** retrieval uses PostgreSQL's `simple` full-text configuration plus
`pg_trgm`. It finds exact wording - part numbers, units, `제1항` references - that
an embedding will happily blur.

They are combined with **Reciprocal Rank Fusion**, not by adding their scores:

```
fused_score(claim) = Σ over channels  1 / (60 + rank_in_that_channel)
```

A cosine similarity of 0.82 and a lexical score of 0.74 are numbers from
unrelated procedures on unrelated scales. Adding them invents a relationship that
does not exist. Ranks keep only the ordering each channel is actually entitled to
assert. A claim found by both channels gets both contributions; a claim found by
one is still returned, with the other channel's rank reported as `null` - which
is information, not missing data.

### Korean lexical search is limited, and the limit is real

PostgreSQL has no Korean morphological analyser. `simple` splits on whitespace
and punctuation, so the corpus's `데이터를` and a user's `데이터` are unrelated
tokens to it. Trigram matching is what recovers those, and it is a heuristic:
it cannot resolve a synonym and will occasionally match a coincidence. Proper
Korean lexical search wants an analyser such as mecab-ko behind a custom
text-search configuration - a database provisioning decision, not an application
change.

### The embedding model

`intfloat/multilingual-e5-small`: 384 dimensions, unit-normalised, CPU, about
940 MB cached, ~9.5 s to load and ~5 ms per claim to embed thereafter. It was
chosen so this phase could validate the *architecture* on a CPU-only host, not
because it is the best Korean embedding model - no Korean benchmark was run to
choose it, and the evaluation corpus here is far too small to rank models.

Swapping to another **384-dimensional** model is a settings change plus a
re-index; the two indexes coexist and only the configured one is searched.
Swapping to a model of a **different width** needs a migration, because the
column is `vector(384)`. That is a deliberate MVP limitation, not an oversight.

### Every result stays citable

A search result carries the same `(document_id, page_number, start_char,
end_char)` spans the claim endpoints return. Normalised search text is folded and
space-collapsed, so its offsets address nothing in the source; it is never used
as a coordinate. In the UI, clicking a result's span link opens that document's
page viewer with the exact range highlighted.

### Query privacy

Search queries are never logged. A patent search query says what someone is
working on, which is confidential before filing, and logs outlive requests. Logs
carry the query's length and a 12-character digest prefix - enough to correlate a
bug report with a log line, not enough to reconstruct the query.

### Retrieval evaluation

```bash
make eval          # with the configured model
make eval-fake     # deterministic provider, no download
```

Runs the real pipeline - upload, parse, index, search - over 26 newly authored
synthetic Korean claims and 19 queries, and writes
[apps/api/evals/results/REPORT.md](apps/api/evals/results/REPORT.md). Measured
with `multilingual-e5-small`:

| Mode | Recall@1 | Recall@3 | Recall@5 | MRR@10 |
| --- | --- | --- | --- | --- |
| dense | 0.770 | 0.926 | **0.971** | 0.961 |
| lexical | 0.740 | 0.897 | 0.912 | 0.961 |
| hybrid | **0.799** | **0.926** | 0.941 | **1.000** |

Hybrid wins on Recall@1 and MRR@10 and **loses to dense on Recall@5** - fusion
interleaves two lists, so a claim one channel ranked fourth can be pushed past
the cutoff by the other channel's confident-but-wrong candidates. The report
names the query where that happens. No relevance label was adjusted after seeing
a result.

This corpus is large enough to catch a broken retrieval channel and to compare
two configurations. It is **not** evidence of production retrieval quality, and
these numbers should not be quoted as if it were.

### Uploaded files are never committed

`STORAGE_ROOT` points outside the repository (a Docker volume by default), and
`.gitignore` refuses `*.pdf` and the usual data directories. No real patent document
is committed as a fixture; test PDFs are generated at runtime.

## Local LLM provider

Phase 4A-1 adds the ability to generate text with a local model. **Nothing uses
it yet** - the model is not connected to claim retrieval, and there is no grounded
answering, citation, or analysis. That is Phase 4A-2. Full design notes are in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) section 10.

### The stack does not need a model

`LLM_PROVIDER=fake` is the default. The fake is a real implementation of the
provider protocol whose transport is replaced - it runs the same request
validation, JSON extraction, and schema validation as the network adapters, and
given any schema it synthesises a conforming payload. So `docker compose up`
works with nothing downloaded, the `/llm` page works end to end, and the test
suite never touches the network.

`/health` and `/ready` do not consult the LLM. A model server that is down is
reported by `GET /api/v1/llm/status`, not by making the whole service look
unhealthy.

### Running a real model

Two deployment shapes. The documented default is **Ollama on the host**, because
it reuses models you have already pulled instead of downloading a second copy
into a container volume:

```bash
ollama serve
ollama pull qwen2.5:1.5b
LLM_PROVIDER=ollama docker compose up -d api
```

Or as an optional Compose service, behind a profile so a normal `up` never starts
it:

```bash
docker compose --profile llm up -d ollama
docker compose exec ollama ollama pull qwen2.5:1.5b
LLM_PROVIDER=ollama LLM_OLLAMA_BASE_URL=http://ollama:11434 docker compose up -d api
```

Then open http://localhost:3000/llm, or:

```bash
curl http://localhost:8000/api/v1/llm/status
curl -X POST http://localhost:8000/api/v1/llm/diagnostics/generate \
     -H 'Content-Type: application/json' \
     -d '{"prompt":"특허 청구항이란 무엇인지 한 문장으로 설명하세요."}'
curl -X POST http://localhost:8000/api/v1/llm/diagnostics/structured \
     -H 'Content-Type: application/json' \
     -d '{"prompt":"센서 데이터를 수집하여 무선으로 전송하는 통신 장치."}'
```

The diagnostics endpoints are development tooling: they default to on in
development and off in every other environment, and return 404 when disabled.
Neither accepts a model, a provider, a base URL, or a JSON Schema - the model
comes from server configuration, and an unknown field is a 422 rather than a
silently ignored one.

### An OpenAI-compatible server (vLLM)

For a **local or private** server only. The hosted OpenAI service is deliberately
not a supported target: unpublished patent text should not leave the deployment
because an adapter made it convenient.

```bash
LLM_PROVIDER=openai_compatible
LLM_OPENAI_COMPATIBLE_BASE_URL=http://<host>:8000/v1
LLM_OPENAI_COMPATIBLE_MODEL=Qwen/Qwen2.5-1.5B-Instruct
LLM_STRUCTURED_OUTPUT_MODE=native_json_schema
```

`LLM_STRUCTURED_OUTPUT_MODE` is declared rather than probed, because compatibility
is a spectrum: vLLM enforces a JSON Schema, some servers guarantee only valid
JSON, and some accept `response_format` and quietly ignore it. When a mode weaker
than native schema enforcement is used, the response carries a **warning** saying
so, and the `/llm` page shows it. A prompt-only fallback is never presented as
native enforcement.

This adapter is **contract-tested against a mocked HTTP transport; no real vLLM
server has been run.** See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) section 10
for the exact setup to reproduce it.

### Structured output is validated even when the server enforces it

Ollama constrains decoding to the JSON Schema it is given, and the reply is still
parsed and validated on arrival. That is not belt-and-braces: during Phase 4A-1
validation `qwen2.5:1.5b` returned `"confidence": 3` against a schema declaring
`minimum: 0.0, maximum: 1.0`, in both Korean and English. **Constrained decoding
guarantees types and structure, not value ranges.** The post-validation rejected
it with `llm_structured_output_validation_failed` rather than passing an
out-of-range number to a caller.

Invalid output is never coerced into valid output. JSON extraction is strict:
exactly one complete JSON value, no prose before or after, no second value, no
comments, truncation reported distinctly from malformedness, and unknown fields
refused unless the schema opts into them.

### The model this was validated with

`qwen2.5:1.5b` - 986 MB, pulled in 61 s, on a CPU-only Windows host. Health check
28-46 ms; cold generation 27.6 s (first call, model load included); warm
generation 0.18-0.38 s; structured generation 0.61-0.94 s.

**This is a smoke-test model, not a patent analyst.** A 1.5B model is not fit for
claim analysis, and none of these numbers says anything about analysis quality.

### Nothing about a prompt reaches the logs

Log lines carry provider, model, request id, prompt **character count**, message
count, token limits, duration, finish reason, token counts, and error code. They
never carry prompts, system instructions, generated output, structured values, API
keys, authorization headers, or raw provider payloads. The request correlation id
is random rather than derived from the prompt, which would be a weak fingerprint
of confidential text in every line.

Provider error bodies are read to classify the failure and then discarded - an
OpenAI-compatible error routinely echoes the offending request back, which here
would be patent text. API keys are held as secrets, excluded from repr and
serialisation, and never returned by any endpoint.

### No migration was added

Prompts, completions, provider health, and token usage are **not persisted**.
Provider diagnostics are runtime infrastructure, not domain data, and persisting
prompts and completions would create a store of confidential patent text that no
feature depends on. The schema stays at revision `0004`.

## Current limitations

- Retrieval stops at claims. No bibliographic/abstract/description parsing, no
  claim element decomposition, no description-level chunking, and no reranking -
  see [docs/ROADMAP.md](docs/ROADMAP.md).
- Generation exists but nothing uses it. The LLM is not connected to retrieval:
  no grounded answering, no citations, no analysis. Phase 4A-2.
- No streaming, tool calling, chat history, or conversation memory.
- The OpenAI-compatible adapter is contract-tested only; no real vLLM server has
  been run.
- Generation is synchronous and in-request, bounded by `LLM_MAX_TIMEOUT_SECONDS`.
- Korean lexical retrieval has no morphological analysis; it is token and
  trigram matching, described above.
- One embedding width (384). A model of a different dimension needs a migration.
- Claim indexing is synchronous, and the first request after a restart pays the
  model load (~9.5 s) inside the request.
- Retrieval evaluation runs on a 26-claim synthetic corpus. It detects breakage;
  it does not measure production quality.
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
| 3A | Claim indexing, pgvector, hybrid retrieval, RRF - **complete** |
| 4A-1 | Local LLM provider boundary (Ollama + OpenAI-compatible vLLM + deterministic fake) - **complete** |
| 4A-2 | Evidence-grounded generation over Phase 3A retrieval, with structured citations resolving only to stored source locators |
| 2C | Claim element decomposition schema and deterministic review boundary |
| 3B | Description-level chunking and optional cross-encoder reranking |
| 5 | Claim decomposition and element-level evidence comparison, with grounding enforced |
| 6 | Offline evaluation harness, regression gates, reproducible demonstration |

## License

MIT - see [LICENSE](LICENSE).
