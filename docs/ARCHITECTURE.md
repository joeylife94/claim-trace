# ClaimTrace Architecture

Status: **`main` after the v1.0 Proof (tag `v1.0-proof`), as of the 2026-11-11
first wrap-up. Alembic head `0009`; no milestone is active.** This document
describes what exists today and the boundaries where later work attaches.
Reranking is not built, so it is not specified here. Claim element decomposition
and a retrieval-only claim comparison are built (sections 12 and 13). Sections 1-11
describe the original phases; sections 12-16 cover what was added after them,
section 17 the extension points, and section 18 the known gaps.

Phase 4A-2 connects the Phase 4A-1 model boundary to Phase 3A retrieval and
answers questions from stored claim text. Every returned statement carries a
citation that resolves to a canonical stored source locator, because the model
selects from server-issued evidence identifiers and never names a source itself
(section 11). It still reaches no legal conclusion: claim decomposition and
claim-to-claim comparison are Phase 5.

> **Update (2026-11-11 wrap-up):** Both now exist on `main`. Deterministic claim
> element decomposition with append-only human review is described in section 12,
> and claim comparison in section 13. Comparison is retrieval-only: it ranks the
> claims of one reference document against one target claim, and it still reaches
> no legal conclusion.

---

## 1. Component architecture

```
                    ┌──────────────────────────────┐
   browser ────────▶│ web (Next.js, App Router)    │
                    │ apps/web                     │
                    │ - /  system status panel     │
                    │ - /documents, /documents/[id]│
                    │ - /search, /grounded         │
                    │ - /compare, /reviews/[runId] │
                    │ - /llm diagnostics           │
                    │ - server actions run POSTs   │
                    └───────────────┬──────────────┘
                                    │ HTTP (JSON), CORS-controlled
                                    ▼
                    ┌──────────────────────────────┐
                    │ api (FastAPI)                │
                    │ apps/api                     │
                    │ - /health   liveness         │
                    │ - /ready    readiness        │
                    │ - /api/v1/* versioned API:   │
                    │   system, documents, cases,  │
                    │   claims, claim_elements,    │
                    │   claim_element_reviews,     │
                    │   descriptions, search,      │
                    │   comparison, llm, grounded  │
                    │ - embedding model, in-process│
                    └───────────────┬──────────────┘
                                    │ SQLAlchemy 2.x async + psycopg 3
                                    ▼
                    ┌──────────────────────────────┐
                    │ postgres 17 + pgvector       │
                    │ - 20 tables (0001 to 0009)   │
                    │ - extensions: vector, pg_trgm│
                    └──────────────────────────────┘

   the api container also mounts two named volumes and holds the embedding model:

   document_storage ──▶ /data/uploads   original PDFs      (STORAGE_ROOT)
   model_cache      ──▶ /models         embedding weights   (EMBEDDING_CACHE_DIR)
   embedding model      in-process: sentence-transformers, or "fake" (tests, offline)

   the API additionally speaks to one optional, configurable model server:

                    ┌──────────────────────────────┐
   api ────────────▶│ LLM provider (Phase 4A-1)    │
     HTTP (JSON)    │ ollama | openai_compatible   │
                    │ or "fake", in-process        │
                    │ - never on the request path  │
                    │   of ingestion or retrieval  │
                    └──────────────────────────────┘
```

The three core services run as containers described by `docker-compose.yml`. There
is no message broker, cache, or object store yet; none is needed by the current
scope. Original uploads sit on a local named volume (section 7), and the embedding
model runs inside the api process with its weights in a second named volume
(section 9).

The model server is *optional and out of band*. `docker compose up` starts the
stack with `LLM_PROVIDER=fake`, which needs no model, no weights, and no network;
`/health` and `/ready` do not consult it. An Ollama container is available behind
the `llm` Compose profile, and the documented default instead points the API at
an Ollama running on the host. See section 10.

### Deployment posture

The system is designed to run entirely on-premise: a single Compose project, no
outbound network dependency at runtime, and no managed cloud service. That
constraint is what later drives the choice of local model providers over hosted
APIs.

---

## 2. Backend module layout

```
apps/api/src/claimtrace_api/
├── main.py              application factory, middleware, lifespan, error handling
├── core/
│   ├── config.py        Settings (pydantic-settings), single source of config
│   ├── errors.py        ErrorCode taxonomy + HTTP status mapping
│   └── logging.py       stdout logging, text or JSON
├── api/
│   ├── deps.py          FastAPI dependencies (engine, session, storage, parser, service)
│   ├── health.py        unversioned operational probes
│   └── v1/
│       ├── router.py    aggregates every v1 router
│       ├── system.py    GET /api/v1/system/info
│       ├── documents.py document upload, retry, listing, detail, page text
│       ├── claims.py    claim parsing, claim reads, claim indexing
│       ├── search.py    POST /api/v1/search/claims
│       ├── claim_elements.py         element decomposition (section 12)
│       ├── claim_element_reviews.py  append-only review of a run (section 12)
│       ├── comparison.py             POST /api/v1/compare/claims (section 13)
│       ├── descriptions.py           description derive, index, search (section 14)
│       ├── cases.py                  analyst Cases and their results (section 15)
│       ├── llm.py       LLM status + development generation diagnostics
│       └── grounded.py  POST /api/v1/grounded/answers
├── services/
│   ├── ingestion.py     the ingestion use case: validate → store → parse → persist
│   ├── claim_parsing.py the claim structural parsing use case
│   ├── claim_indexing.py the indexing use case: embed → persist search records
│   ├── claim_search.py  the search use case: profile → retrieve → fuse → hydrate
│   ├── llm_generation.py the generation use case: validate → bound → generate
│   ├── grounded_generation.py  retrieval + generation: the Phase 4A-2 use case
│   ├── source_resolution.py    locator → the stored page text it addresses
│   ├── claim_comparison.py     one target claim against one reference document
│   ├── claim_elements.py       the element decomposition use case
│   ├── claim_element_reviews.py  append and read review records
│   ├── description_evidence.py derive, index and search description segments
│   ├── cases.py                analyst Cases and document association
│   └── case_grounded_results.py  persist and reopen Case grounded results
├── llm/                 the LLM boundary (Phase 4A-1). Imports no web framework
│   ├── base.py          LLMProvider protocol, StructuredGeneration
│   ├── models.py        messages, options, response, capabilities, metadata
│   ├── errors.py        LLMErrorCode taxonomy + typed exceptions
│   ├── json_output.py   strict JSON extraction and schema validation
│   ├── retry.py         conservative retry policy
│   ├── transport.py     URL validation, timeouts, httpx error mapping
│   ├── fake.py          deterministic provider (tests, offline, CI)
│   ├── ollama.py        Ollama adapter
│   ├── openai_compatible.py  local OpenAI-compatible (vLLM) adapter
│   └── registry.py      builds the one configured provider
├── grounding/           evidence-grounded answering (Phase 4A-2). No web
│   │                    framework, no database, no provider - pure rules
│   ├── evidence.py      the request-local evidence catalog and its opaque id
│   ├── context.py       deterministic prompt building and the context budget
│   ├── draft.py         GroundedAnswerDraft: the model's output contract
│   └── validation.py    post-generation citation and invariant checking
├── indexing/
│   ├── normalization.py the normalised search representation
│   ├── profile.py       IndexProfile: what makes two index runs comparable
│   └── embeddings/
│       ├── base.py      EmbeddingProvider protocol
│       ├── fake.py      deterministic hash provider (tests, offline)
│       └── sentence_transformers.py  the real local model
├── retrieval/
│   ├── base.py          Candidate, FusedCandidate, RetrievalMode
│   ├── dense.py         pgvector cosine retrieval
│   ├── lexical.py       PostgreSQL full-text + trigram retrieval
│   └── fusion.py        Reciprocal Rank Fusion
├── parsing/
│   ├── base.py          DocumentParser protocol, ParsedDocument/ParsedPage
│   ├── pymupdf_parser.py PyMuPDF implementation for digital PDFs
│   ├── claims/
│   │   ├── base.py      ClaimParser protocol and the parsed-claim dataclasses
│   │   └── korean_rules.py  KoreanRuleBasedClaimParser
│   └── elements.py      DeterministicElementParser (section 12)
├── storage/
│   ├── base.py          FileStorage protocol, storage-key validation
│   └── local.py         local filesystem implementation
├── db/
│   ├── base.py          DeclarativeBase, Alembic's target metadata
│   ├── session.py       async engine + session factory
│   ├── models.py        ORM models (app_metadata, documents, pages, claims, index runs,
│   │                    search records)
│   ├── element_models.py ORM models for decomposition runs, elements and spans
│   ├── review_models.py ORM model for decomposition reviews
│   └── health.py        SELECT 1 probe
└── schemas/             Pydantic request/response models, including locators.py
```

ORM models are split over three modules: `models.py` (the baseline, ingestion,
claim parsing, and claim indexing tables), `element_models.py`, and
`review_models.py`. The tables added by revisions 0007 to 0009 - description
evidence and analyst Cases - have no ORM model; their services read and write
them with raw SQL.

Two rules keep this layout honest:

1. **Routes depend on dependencies, never on module-level globals.** Every external
   resource (engine, session, storage, parser, service) is injected, which is why
   the test suite can isolate PostgreSQL without a socket.
2. **Dependencies point inward.** `parsing/`, `storage/`, `llm/`, and
   `grounding/` know nothing about FastAPI or about each other; `services/`
   composes them; `api/` only translates HTTP. A different PDF engine or a
   different storage backend is a new module behind an existing protocol, not a
   refactor.

   `grounding/` is the strictest case: it holds the rules that decide whether a
   citation is legitimate, and it imports no session, no ORM model beyond the
   `ClaimType` enum, and no provider. That is what lets the citation-integrity
   tests run with no database, no model, and no network - which in turn is what
   makes it affordable to test them exhaustively.

> **Update (2026-11-11 wrap-up):** Both rules were written for the layout at
> Phase 4A-2, and the later modules depart from them in five places. The routes in
> `api/v1/cases.py` construct `AnalystCaseService` and `CaseGroundedResultService`
> inline instead of taking them from `api/deps.py`, and the same module imports the
> private `_answer_response` mapper from `api/v1/grounded.py`.
> `api/v1/claim_elements.py` checks the document, the claim parse snapshot, and the
> claim number in the route before calling its service, which is orchestration in
> `api/`. `api/v1/descriptions.py` reads `service._settings` to get the RRF `k`.
> And `services/description_evidence.py` implements dense, lexical, and rank-fusion
> retrieval in raw SQL itself instead of composing `retrieval/` (section 14). They
> are listed so that the rules above are not read as stricter than the code.

---

## 3. Request flow

### `GET /health`

```
client → CORS middleware → route → HealthResponse(status="ok") → 200
```

No dependency is resolved. The endpoint answers as long as the process is
scheduled, which is exactly what a liveness probe should mean.

### `GET /ready`

```
client → CORS middleware → route
              ↓ Depends(get_postgres_ready)
         db.health.check_postgres(engine)
              ↓ engine.connect(); SELECT 1
         success → 200 {"status":"ready","dependencies":{"postgres":"ok"}}
         failure → log warning (with cause, server-side only)
                 → 503 {"status":"not_ready","dependencies":{"postgres":"unavailable"}}
```

Failure detail never reaches the client, because the failure cause can contain the
connection string.

### `GET /api/v1/system/info`

```
client → CORS middleware → route → Depends(get_settings) → 200 {name, version, environment}
```

Only non-sensitive fields are exposed. Adding a field here is a deliberate act:
settings also hold credentials, so the response model is explicit rather than a
dump of the settings object.

### `POST /api/v1/documents`

```
client → route: read_upload() streams the body, aborting past UPLOAD_MAX_BYTES
              ↓ DocumentIngestionService.ingest()
         1. validate    extension → declared type → non-empty → size → %PDF- magic
                        (a rejection here stores nothing and creates no record)
         2. sha256      digest the bytes
         3. deduplicate SELECT ... WHERE sha256 = ?  → hit: return existing, 200
         4. store       LocalFileStorage.write(<aa>/<sha256>.pdf), atomic rename
         5. register    INSERT documents (status=uploaded) → commit
                        UPDATE status=processing              → commit
         6. parse       LocalFileStorage.read(storage_key)
                        → PyMuPDFDocumentParser.parse(bytes) → ordered pages,
                          after its per-page text-layer classification
         7. persist     reject a document-wide total below MIN_EXTRACTED_CHARACTERS,
                        then INSERT every page + UPDATE status=completed → ONE commit
              ↓
         201 Created + DocumentResponse
```

Failure branches:

| When | Result |
| --- | --- |
| Validation (step 1) | 4xx, nothing stored, no record |
| Original cannot be written (4) | `storage_failure`, 500; nothing is registered, so no document record exists |
| `uploaded → processing` commit fails (5) | The session is rolled back and the already-registered document is terminalized as `failed` with `internal_error` when failure-state persistence succeeds; client receives a safe 500 ingestion failure. P4 verified this service contract with deterministic fault injection, not a real PostgreSQL commit fault. |
| Stored-file read fails after registration (6) | The document is terminalized as `failed` with `storage_failure` when failure-state persistence succeeds; the raw storage exception is not returned to the client. |
| Parser rejection (6): unreadable, encrypted, or a mixed text layer | Document marked `failed` with the parser's error code (`malformed_pdf`, `encrypted_pdf`, or `no_extractable_text` for a mixed layer), 422, and the record is returned inside the error envelope |
| Document-wide text below `MIN_EXTRACTED_CHARACTERS` (7) | Document marked `failed` with `no_extractable_text`, 422, record returned in the same envelope |
| Page/completion persistence fails (7) | The page/completion transaction rolls back, so no partial page set is accepted as `completed`; the document is then terminalized as `failed` with `internal_error` when failure-state persistence succeeds. |
| Concurrent identical upload | Unique digest violation is caught and resolved to the winner's record, 200 |

Step 7 is deliberately a single commit: a partially written page set must never be
visible as a `completed` document, because a citation into a half-ingested document
would be silently wrong. If that commit fails, the page/completion transaction is
rolled back before the service attempts to persist the terminal failure state.

The terminalization paths above describe failure handling, not automatic recovery.
Ingestion is synchronous and has no background retry or resume worker. Because
content-addressed deduplication returns an existing row even when it is `failed`,
re-uploading identical bytes does not automatically re-run parsing; operator recovery
beyond the documented request path is not verified here.

Step 5's first commit makes stored bytes traceable before processing begins. The
second commit records `processing`; accepted P4 handling attempts to persist
`failed` if that transition commit itself fails. This does not establish crash
recovery: process termination between commits or during parsing has no automatic
resume path.

> **Update (2026-11-11 wrap-up):** Explicit retry now exists.
> `POST /api/v1/documents/{id}/retry` re-runs parsing and persistence for a
> document whose status is `failed`, from its stored original and under the same
> document id (section 7, "Failure terminalization and retry"). It is
> operator-driven. There is still no automatic or background retry, and
> re-uploading identical bytes still returns the failed row unchanged. A row
> stranded in `uploaded` or `processing` after a crash is not recoverable this
> way: retry accepts only `failed` rows and answers 409 `document_retry_not_allowed`
> for any other status.

Parsing is synchronous. A 20 MB text PDF parses in well under a second, and a queue
would add a broker, a worker, and a retry policy to buy nothing at this size. When
OCR arrives - minutes per document, not milliseconds - that trade flips, and the
`processing` state already exists to support it.

### `GET /api/v1/documents{,/{id},/{id}/pages}`

Straight reads. Listing is newest-first with explicit `limit`/`offset`; pages come
back in reading order, each carrying the locator that spans it. `storage_key` is
never serialised - where bytes live is server-side detail.

### Frontend flow

```
browser GET /  →  app/page.tsx (server component, force-dynamic)
                     ↓ lib/api.ts loadSystemStatus()
                  GET /health, /ready, /api/v1/system/info   (web runtime → api)
                     ↓ Promise.allSettled - an unreachable API is a rendered state,
                       not an error page
                  SystemStatusPanel (server-rendered)
                     └─ RefreshButton (client) → router.refresh() → re-runs the above
```

Status is fetched by the server component, so the page never ships a loading
flash and the API does not have to be exposed to browsers at all - a better fit
for an on-premise deployment. `/ready` answering `503` is a valid outcome rather
than an error, so `lib/api.ts` explicitly accepts that status and reads the body.

Two base URLs exist for one reason: the Next.js runtime and the browser sit on
different networks. `API_INTERNAL_BASE_URL` (`http://api:8000` in Compose) is used
for server-side fetches; `NEXT_PUBLIC_API_BASE_URL` (`http://localhost:8000`) is
the fallback and the value any future browser-side call would use. Only
`NEXT_PUBLIC_*` values are compiled into the client bundle.

> **Update (2026-11-11 wrap-up):** The flow above is the home page only. The web
> app now has eight routes under `apps/web/app/`: `/`, `/documents`,
> `/documents/[id]`, `/search`, `/grounded`, `/compare`, `/llm`, and
> `/reviews/[runId]`. Pages still read through server components that use `lib/`.
> Every mutation, and every POST-based query, goes through a Next.js server action
> that runs in the web runtime and calls the API from there:
>
> | Area | Server actions |
> | --- | --- |
> | Upload and retry | `uploadDocumentAction`, `retryDocumentAction` (`app/documents/actions.ts`) |
> | Claim parsing and indexing | `parseClaimsAction`, `indexClaimsAction` (`app/documents/[id]/actions.ts`) |
> | Decomposition and review | `decomposeAndReviewAction` (`app/documents/[id]/review-actions.ts`), `submitElementReviewAction` (`app/reviews/[runId]/actions.ts`) |
> | Search, grounded answers, comparison | `searchClaimsAction`, `askGroundedAction`, `compareClaimsAction` |
> | LLM diagnostics | `generateTextAction`, `generateStructuredAction` |
>
> No file marked `"use client"` calls `fetch`, and none imports a `lib/` function
> that does, so the API still does not have to be exposed to browsers. The flows
> for decomposition, review, comparison, description evidence, and Cases are in
> sections 12 to 15; they are not repeated here.

---

## 4. Service responsibilities

| Service | Owns | Does not own |
| --- | --- | --- |
| `web` | Presentation, server-side reads, and server actions that proxy mutations to the API | Business rules, database access, secrets |
| `api` | HTTP contract, configuration, validation, persistence, migrations | Rendering, UI state |
| `postgres` | Durable state, `vector` extension | Application logic |

Anything the browser must not see (credentials, model endpoints, internal hosts)
stays in the API's environment. Only `NEXT_PUBLIC_*` values are exposed to the
client bundle.

---

## 5. Configuration strategy

- One source of truth: `Settings` in `core/config.py`, populated from environment
  variables with `.env` as a local fallback.
- No credential is ever hardcoded, including in `alembic.ini`, which deliberately
  omits `sqlalchemy.url` and lets `alembic/env.py` resolve it from `Settings`.
- `.env.example` documents every key with safe placeholder values; `.env` is
  git-ignored.
- Compose passes discrete `POSTGRES_*` variables so the same values configure both
  the database container and the API. `DATABASE_URL` exists as a single-value
  override for deployments that hand out a full DSN.
- CORS origins come from `CORS_ALLOW_ORIGINS` (comma-separated), so no code change
  is needed to front the API with a different host.
- Environment-sensitive behaviour is limited and explicit: `/docs` and
  `/openapi.json` are disabled when `ENVIRONMENT=production`.
- Logs go to stdout in `text` or `json` format (`LOG_FORMAT`), leaving collection
  to the container runtime.

Ingestion adds these keys:

| Variable | Purpose |
| --- | --- |
| `STORAGE_ROOT` | Where originals are written. Must be outside the source tree. |
| `UPLOAD_MAX_BYTES` | Hard ceiling, enforced while streaming (default 20 MB). |
| `UPLOAD_ALLOWED_CONTENT_TYPES` / `UPLOAD_ALLOWED_EXTENSIONS` | Accepted upload types. |
| `MIN_EXTRACTED_CHARACTERS` | Below this total, a PDF counts as having no text layer. A mixed text layer is rejected separately, by the parser (section 7). |

### Error handling

A catch-all handler logs the traceback server-side and returns
`{"detail": "Internal server error"}`. Stack traces, SQL, and DSNs are never
serialised into a response.

Ingestion failures are different: they are expected outcomes with a stable
`error_code` from `core/errors.py`, which is both the API contract and the value
persisted on failed documents. Clients branch on the code, never on the message.

> **Update (2026-11-11 wrap-up):** The Cases API (section 15) is the exception. It
> raises FastAPI `HTTPException`, so its error bodies are `{"detail": ...}` with no
> `error_code`, and a client of those routes can branch only on the status code
> and the `detail` string. Request-validation failures elsewhere also keep
> FastAPI's default 422 list shape rather than the envelope; an unknown review
> status (section 12) is one example.

| Code | Status | Meaning |
| --- | --- | --- |
| `unsupported_file_type` | 415 | Extension, declared type, or magic bytes are not a PDF |
| `file_too_large` | 413 | Exceeds `UPLOAD_MAX_BYTES` |
| `empty_file` | 400 | Zero bytes |
| `malformed_pdf` | 422 | Unreadable, or repaired into a zero-page document |
| `encrypted_pdf` | 422 | Password protected |
| `no_extractable_text` | 422 | Below `MIN_EXTRACTED_CHARACTERS`; scanned or image-only |
| `storage_failure` | 500 | The stored original cannot be read during an already-registered ingestion |
| `internal_error` | 500 | A processing-transition or page/completion persistence failure is mapped to a client-safe ingestion failure |
| `document_not_found` | 404 | Unknown document id |
| `document_not_completed` | 409 | The document's ingestion has not completed; claim parsing, claim indexing, and description derivation refuse it |
| `document_retry_not_allowed` | 409 | Retry was requested for a document whose status is not `failed` |
| `claim_parse_failed` | 422 | Claim parsing ran and failed; the failed result is recorded |
| `claim_parse_not_found` | 404 | The document has no claim parse result |
| `claim_not_found` | 404 | The claim number is not in the document's claim set |
| `comparison_invalid_request` | 400 | Target and reference document are the same. The request schema normally rejects this first, with a 422, so the code comes from the service only |
| `element_decomposition_run_not_found` | 404 | No element decomposition run has this id |
| `grounded_generation_unavailable` | 503 | Grounded answering is switched off by `GROUNDED_GENERATION_ENABLED=false` (default `true`) |

The retrieval, LLM, and grounded phases add further codes, listed in sections 9, 10,
and 11.

> **Update (2026-11-11 wrap-up):** Two rows above are broader than they read.
> `storage_failure` is also raised before any document is registered, when the
> original cannot be written; the response is then an ordinary
> `{detail, error_code}` body with no `document`, because no record exists.
> `no_extractable_text` is also returned for a mixed text layer, not only for a
> total below `MIN_EXTRACTED_CHARACTERS` (section 7).

---

## 6. Database and migration strategy

- PostgreSQL 17 with pgvector (`pgvector/pgvector:pg17`).
- Alembic owns the schema. The application never calls `create_all`, so the running
  schema is always reproducible from `alembic/versions/`.
- The baseline revision `0001` enables the `vector` extension and creates
  `app_metadata` (`key`, `value`, `created_at`, `updated_at`). It exists to prove
  the pipeline works; it defines no domain table.
- Revision `0002` adds the two ingestion tables described in section 7,
  revision `0003` the four claim-parsing tables in section 8, and revision
  `0004` the two retrieval tables in section 9. `0004` also enables `pg_trgm`.

> **Update (2026-11-11 wrap-up):** Five further revisions follow, and the chain is
> linear from `0001` to the head, `0009`. Across it `op.create_table` creates 20
> tables.
>
> | Revision | Tables | Described in |
> | --- | --- | --- |
> | `0005` | `element_decomposition_runs`, `claim_elements`, `claim_element_spans` | section 12 |
> | `0006` | `element_decomposition_reviews` | section 12 |
> | `0007` | `description_derivation_runs`, `description_segments`, `description_search_records` | section 14 |
> | `0008` | `analyst_cases`, `analyst_case_documents` | section 15 |
> | `0009` | `analyst_case_results`, `analyst_case_evidence` | section 15 |
- `infra/postgres/init/10-extensions.sql` also creates the extension at initdb
  time. That covers on-premise installations where the migration role is not a
  superuser; both paths are idempotent.
- Migrations run explicitly (`make migrate`), not on container start, so a rolling
  restart can never trigger a surprise schema change.
- Timestamps are `TIMESTAMPTZ` with `server_default now()`; `updated_at` is
  maintained by SQLAlchemy's `onupdate`.

> **Update (2026-11-11 wrap-up):** That holds for the ORM-mapped tables that carry
> `updated_at`: `app_metadata`, `documents`, `claim_parse_results`, `claims`,
> `claim_index_runs`, and `claim_search_records`. Among the tables added since,
> only `analyst_cases` has an `updated_at`, and it has no ORM model, so the services
> set it with an explicit `UPDATE ... SET updated_at = now()` when a document is
> associated or removed and when a result is stored. The other tables from `0005` on
> are immutable or append-only and carry only `created_at`; the exceptions are
> `analyst_case_documents`, which has `associated_at`, and `analyst_case_evidence`,
> which has no timestamp.
- The application engine is async (psycopg 3); Alembic uses a synchronous engine
  against the same URL.

> **Update (2026-11-11 wrap-up):** `alembic/env.py` imports only three ORM modules
> (`models`, `element_models`, `review_models`) and sets `target_metadata` to
> `Base.metadata` with no `include_object` filter. The seven tables from `0007` to
> `0009` are not in that metadata (section 2). `make migration` (autogenerate) was
> not run against this state while writing this note; by reading only, it would be
> expected to propose dropping those tables, so an autogenerated revision needs
> review before it is applied.

---

## 7. Document ingestion (Phase 2A)

### Schema

```
documents                              document_pages
─────────────────────────────          ────────────────────────────────────
id                 uuid  PK            id               uuid  PK
original_filename  varchar(512)        document_id      uuid  FK → documents.id
content_type       varchar(128)                               ON DELETE CASCADE
size_bytes         bigint  > 0         page_number      integer  ≥ 1
sha256             varchar(64) UNIQUE  text             text
storage_key        varchar(512)        character_count  integer  ≥ 0
status             varchar + CHECK     text_sha256      varchar(64)
page_count         integer  NULL       created_at       timestamptz
extracted_character_count integer      UNIQUE (document_id, page_number)
parser_name/_version varchar(64)
error_code/_message  varchar
created_at/updated_at timestamptz
```

Decisions worth stating:

- **`status` is VARCHAR + CHECK, not a native enum.** Adding a lifecycle state later
  is then an ordinary migration instead of an `ALTER TYPE` that locks the table.
- **`ON DELETE CASCADE`** is intentional: a page has no meaning without its
  document, and leaving orphaned page text after a deletion would mean retaining
  document contents the operator believes they deleted.
- **`UNIQUE (document_id, page_number)`** makes "page 3 of this document" a single
  row, which is what lets a locator be a stable address.
- **`text_sha256` per page** lets a future re-parse detect whether a page's text
  actually changed, and therefore whether existing citations into it still hold.
- **No sections, claims, chunks, or embeddings tables.** Those are Phase 2B and 3.
  This was the decision at revision `0002`; section 6 lists what followed.

### Lifecycle

`uploaded → processing → completed | failed`. All four states are used: `uploaded`
is committed as soon as the bytes are stored, so a crash during parsing leaves a
traceable record rather than an unreferenced file.

> **Update (2026-11-11 wrap-up):** A `failed` document can re-enter `processing`
> through explicit retry, so the lifecycle also has the path
> `failed → processing → completed | failed`. See "Failure terminalization and
> retry" below.

### Duplicate policy: content-addressed idempotency

`documents.sha256` is unique, and it is also the storage key. Re-uploading identical
bytes returns the existing record with **200** instead of creating a second document
or storing a second copy — including when that record is a `failed` one, so a user
who re-uploads a broken file sees the same explanation rather than an accumulating
pile of failures.

The filename is not part of identity: the same PDF under a different name is the
same document, and the first upload's filename is kept. The rule is enforced by the
database constraint, not just by the pre-check, so two concurrent identical uploads
resolve to one record rather than racing.

The trade-off: a document that is genuinely revised produces different bytes and is
therefore a different document, with no version link between them. Versioning is a
later concern and would be a new relation, not a relaxation of this constraint.

> **Update (2026-11-11 wrap-up):** A failed row is no longer a dead end. Explicit
> retry re-runs it in place, under the same id, digest, and stored original;
> re-uploading identical bytes still returns the failed row unchanged. See
> "Failure terminalization and retry" below.

### Failure terminalization and retry

This subsection was added after the original chapter text, in P2–P4 (failure
terminalization) and P8–P10 (explicit retry). It extends the lifecycle above with one
edge: `failed → processing`, taken only by an explicit retry. `completed` is never
re-entered.

Every failure after the original is stored and its `uploaded` row committed ends in
`failed`, with an `error_code`, a fixed client-safe `error_message` (cut to 512
characters), and null `page_count` and `extracted_character_count`. The failed row
travels back inside the ingestion error envelope.

| Failure | `error_code` | HTTP |
| --- | --- | --- |
| Commit of `uploaded → processing` fails | `internal_error` | 500 |
| Stored original cannot be read | `storage_failure` | 500 |
| Parser rejects the bytes (malformed, encrypted, mixed text layer) | the parser's code | 422 |
| Document-wide total below `MIN_EXTRACTED_CHARACTERS` | `no_extractable_text` | 422 |
| Commit of the pages and `completed` fails | `internal_error` | 500 |
| Retry only: commit of `failed → processing` fails | `internal_error` | 500 |

(Failing to write the original at all happens before any row exists: a plain 500
`storage_failure`, no document record.)

`_mark_failed` does the recording. It rolls the session back first, which discards a
half-built page set, then writes the failed state and commits. If that commit also fails,
nothing catches it: the client gets the generic 500 without the envelope, and the row
keeps whatever was last committed, normally `processing`. This is by reading; no test
injects a failure into the recovery commit.

`POST /api/v1/documents/{id}/retry` takes no body and returns the document with 200. It
loads the row `FOR UPDATE`; answers 404 `document_not_found` for a missing row and 409
`document_retry_not_allowed` for any status other than `failed`; sets `processing`, clears
the error fields and counts, and commits (if that commit fails the row is re-marked
`failed` and the client gets 500); then runs the same `_parse_and_persist` path as a
first upload.

Decisions worth stating:

- **Retry is operator-driven and reads the stored bytes.** The route accepts no upload.
  Identity is the digest, so different bytes would be a different document. Retry keeps the
  row id, `sha256` and `storage_key`, and never creates a second row.
- **The success path is shared**: the gates, the single page-plus-`completed` commit, and
  the failure handling are those of a first attempt.
- **A failed row never has pages.** Pages are written only in the commit that sets
  `completed`, and a failed commit is rolled back, so retry inserts pages fresh.
- **The lock covers the status check and the move to `processing`.** The intent is that two
  concurrent retries serialise there and the second gets 409. That is by reading only: the
  unit test asserts that `with_for_update=True` is passed, and no test runs two retries at
  once.

Not provided: automatic or background retry, backoff, an attempt limit or counter; recovery
for a row stranded in `uploaded` or `processing` by a crash (it is not `failed`, so retry
answers 409); and any change to the duplicate rule, so re-uploading identical bytes still
returns the failed row. A deterministic failure fails again, because retry re-runs the same
gates (by reading; not tested).

Evidence: the terminalization paths are tested with fault-injected stub sessions, not real
PostgreSQL faults. Same-row recovery and the 409 for a completed document run against
PostgreSQL in the integration tier; the browser and real-stack checks are in section 16.
The web offers retry only on `/documents`, as a "Retry ingestion" button on failed rows;
the detail page shows the error without a button. Claim-graph persistence failures are a
separate lifecycle, described in section 8.

### Storage strategy

`FileStorage` is a four-method protocol (`write`, `read`, `exists`, `delete`) with
one local-filesystem implementation, chosen because ClaimTrace is on-premise: the
originals sit beside the database with no object-store dependency.

- The key is `<first two hex chars>/<sha256>.pdf` — derived from content, never from
  the client's filename, and the prefix keeps directory sizes sane.
- Keys are validated against a strict pattern (no absolute paths, no `..`, no
  backslashes, no NUL), and the resolved path is re-checked to be inside the root, so
  a symlink planted in the storage tree cannot redirect a write.
- Writes go to a temp file in the destination directory and are `os.replace`d into
  position, so a reader never sees a half-written original.
- The API never returns `storage_key`.

### Parser boundary

```python
class DocumentParser(Protocol):
    name: str
    version: str
    def supports(self, *, content_type: str, filename: str) -> bool: ...
    def parse(self, data: bytes) -> ParsedDocument: ...   # raises ParserError
```

`ParsedDocument` carries ordered `ParsedPage`s, the parser's name and version, and a
whitelisted subset of PDF metadata. The parser takes bytes and returns plain
dataclasses: no FastAPI, no SQLAlchemy, no storage types. That is what makes a second
implementation — a different engine, an XML format, an OCR pipeline — a new class
rather than a change to the ingestion service.

`parser_name` and `parser_version` are persisted per document, so it is always
answerable which code produced a given page text.

### Digital-text-only limitation

This phase supports PDFs that already carry a text layer. A scanned page holds an
image, and no amount of extraction will produce text from it.

The threshold is deliberately simple: if the **whole document** yields fewer than
`MIN_EXTRACTED_CHARACTERS` (default 32) characters, ingestion fails with
`no_extractable_text` and a message telling the user a text layer is required. A
document-wide total is used rather than a per-page rule because a legitimate patent
PDF often has a near-empty drawing page, and rejecting the document for that would be
wrong.

> **Update (2026-11-11 wrap-up):** Since D6-01 a per-page classification runs in the
> parser as well. A PDF with at least one text-bearing page and at least one
> text-empty page (no text, or whitespace only) is rejected with
> `no_extractable_text` as a mixed or ambiguous text layer, so a text patent with
> one truly blank page is now rejected. A page that yields any non-whitespace
> character still counts as text-bearing. The document-wide total check above still
> applies as well. See "Text-layer classification: mixed PDFs fail closed (D6-01)"
> below.

No OCR is attempted, and none is silently substituted. An empty result is reported as
a failure rather than ingested as a document with no text, because a document that
looks ingested but has nothing to cite is worse than a clear rejection.

### Text-layer classification: mixed PDFs fail closed (D6-01)

D6-01 postdates the original text of this chapter and **reverses one decision in it**. The
subsection above chose a document-wide total over a per-page rule, because a patent PDF often
has a near-empty drawing page. That is no longer how ingestion behaves: a PDF in which some
pages carry text and at least one carries none is rejected, so a text patent with one truly
empty page fails. The document-wide total still exists, as the second of two gates.

1. **Classification, inside the parser.** After the encrypted and zero-page checks and once
   every page is extracted, `classify_pdf_text_layer` asks only whether `page.text.strip()`
   is non-empty. `text_native`: every page has text. `image_only_or_no_text`: none does.
   `mixed_or_ambiguous`: some do. Only the mixed class raises, as `ParserError` with code
   `no_extractable_text` and a message that the layer is mixed or ambiguous and OCR is not
   used.
2. **The document-wide total, in the service.** `character_count` sums page text lengths,
   whitespace included. Below `MIN_EXTRACTED_CHARACTERS` (default 32) the service raises
   `no_extractable_text` with the scanned-or-image-only message. A PDF with no text at all
   is stopped here, not by the classifier.

Both end the same way: 422 `no_extractable_text`, the document persisted as `failed` with
null `page_count`, and no pages. The two causes share the code and differ only in message.
The code gives its reason: a document with both text-bearing and text-empty pages "is
ambiguous for the text-native evidence contract", so it fails closed "instead of silently
presenting a partial source-verifiable document".

Decisions worth stating:

- **No OCR, no image inspection.** One non-whitespace character makes a page text-bearing,
  so a drawing page with a figure label passes and a truly blank one does not.
- **Embedded-OCR blind spot.** A scan whose every page already carries a text layer is
  classed `text_native` and its text is extracted as it stands. ClaimTrace does not decide
  whether a layer is native.
- **The classification is not stored or returned.** It is not on `documents`, in
  `ParsedDocument`, or in any response. Outside the parser only tests call it; the D3
  acceptance test recomputes it that way.
- **Parser identity did not change.** `parser_version` is the installed PyMuPDF version and
  `parser_name` is unchanged, so rows cannot be told apart as before or after D6-01.
  Documents completed earlier are not re-validated: no migration or backfill touches them,
  and the parser runs only at upload and retry, which takes only `failed` rows. A mixed PDF
  fails again on retry, since retry re-runs both gates (by reading; not tested).

The false rejection and the blind spot are the accepted D6-01 risks in
`CLAIMTRACE_V1_MASTER.md`, section 16, item 7. One edge was found by reading and is
untested: a PDF whose pages are all whitespace but total 32 characters or more classifies
as `image_only_or_no_text`, which does not raise, and the total counts whitespace, so
nothing in ingestion rejects it. Evidence is synthetic: tests use a generated PDF with one
text page and one graphics-only page, and the D3 acceptance test requires both pinned real
public PDFs to classify `text_native`. No real mixed or image-only PDF was exercised.

### Source locator semantics

A locator is `(document_id, page_number, start_char, end_char)` — a half-open span
`[start_char, end_char)` over `document_pages.text` **as stored**.

Why this is the canonical coordinate:

- **The page is verifiable by a human.** A reviewer can open the original PDF at page
  7 and check the quotation. A chunk index is unverifiable and meaningless the moment
  the chunker changes.
- **It survives every later phase.** Chunking, embeddings, retrieval strategy, and
  reranking all change how text is *found*; none of them change where it *is*.
  Anything narrower — a claim element, a sentence, a chunk — is a sub-span of a page,
  so later phases refine this coordinate instead of replacing it.
- **Offsets index persisted text, not a parser buffer.** The stored string is
  immutable for the life of the row, so offsets recorded today mean the same thing
  later. Extraction normalises line endings before persistence, and that is the only
  transformation applied, precisely so the mapping stays stable.
- **Re-parsing invalidates loudly, not silently.** New pages are new rows;
  `SourceLocator.resolve()` raises if a span runs past the end of the text rather
  than truncating, because a silently shortened quote is a fabricated citation.

`GET /documents/{id}/pages` returns each page's full-page locator, so the coordinate
is visible in the product from the first phase that has any text at all.

### Security considerations

- Uploads are bounded while streaming, so an oversized body is never fully buffered.
- Type is checked three ways — extension, declared content type, and the `%PDF-`
  signature — because the first two are attacker-controlled.
- The filename never reaches the filesystem; keys are content hashes and are
  validated before any path is built.
- Responses never contain paths, tracebacks, SQL, or DSNs. Parser failures log the
  exception type only, since the exception text can quote file contents.
- PDF metadata is whitelisted and truncated before being kept.
- Ingestion logs carry document id, size, a 12-character digest prefix, parser
  identity, page count, duration, status, and error code — never document text, and
  never a full digest, which would be enough to prove possession of a file.
- Uploads live in a Docker volume owned by the non-root runtime user, outside the
  Git tree, and `.gitignore` refuses `*.pdf` and the usual data directories.

Still absent, and still deliberate: authentication, per-user isolation, virus
scanning, and rate limiting. This service belongs on a trusted network.

---

## 8. Claim structural parsing (Phase 2B)

Deterministic rules only. No model, no embedding, no similarity, no legal
reasoning: the same page text always produces the same claim graph.

### Lifecycle, separate from ingestion

```
claim_parse_results.status:  processing → completed | no_claims_found | failed
```

**A claim parse never changes `documents.status`.** A document that ingested
cleanly stays `completed` even when parsing finds nothing or fails outright.
Conflating the two would make a perfectly readable PDF look broken because it
happens not to be a patent.

`no_claims_found` is its own status, not an empty success. The distinction
matters: "this document has no claims" and "we could not parse it" call for
different actions from the reader.

### Parser boundary

```python
class ClaimParser(Protocol):
    name: str
    version: str
    def parse(self, pages: Sequence[SourcePage]) -> ParsedClaimSet: ...
```

`SourcePage` is `(document_id, page_number, text)` - persisted page text, nothing
else. `ParsedClaimSet` carries ordered `ParsedClaim`s (number, classification,
spans, reconstructed text, resolved dependencies) plus `ParseWarning`s and the
parser's identity. The parser returns plain dataclasses: no FastAPI, no
SQLAlchemy, no session, no HTTP status. Orchestration lives in
`services/claim_parsing.py`, HTTP translation in `api/v1/claims.py`.

The one implementation is `KoreanRuleBasedClaimParser`
(`korean-rule-based-claims`, version `0.1.0`).

### Supported Korean patterns

Headings, each matched at the start of a line:

| Form | Example |
| --- | --- |
| Bracketed | `【청구항 1】`, `[청구항 1]`, `〔청구항 1〕` |
| Bare | `청구항 1`, `청구항 1.` |
| With 제/항 | `청구항 제1항` |
| Full-width digits | `【청구항 １】` |
| English fallback | `Claim 1` on a line of its own |

A bare `청구항 N` followed by a dependency particle or a connector
(`에 있어서`, `또는`, `및`, `내지`, …) is treated as a **reference, not a heading**.
Without that rule, a dependent claim whose body happens to start a line would be
mistaken for the heading of the claim it references.

The claims region starts at `【청구범위】` / `특허청구범위` / `청구의 범위` when
present, and ends at the first section that can only follow the claims
(`요약서`, `요약`, `초록`, `도면`, `명세서`) so the last claim does not swallow the
abstract.

Dependency expressions - a run of references **plus a required particle**
(`에 있어서`, `에 따른`, `에 따라`, `에 기재된`, `에 기재의`, `에 의한`):

| Form | Resolves to |
| --- | --- |
| `제1항에 있어서` / `청구항 1에 있어서` | 1 |
| `제1항에 따른` / `청구항 1에 따른` | 1 |
| `제1항 또는 제2항에 있어서` | 1, 2 |
| `제1항 및 제2항에 있어서` | 1, 2 |
| `제1항, 제2항에 있어서` | 1, 2 |
| `제1항 내지 제3항 중 어느 한 항에 있어서` | 1, 2, 3 |

Requiring the particle is what keeps arbitrary technical numbers out of the
graph: `온도 100도`, `도 2에 도시된`, and `3개의 부재` produce no edges, and neither
does a bare `제1항` with no dependency particle after it.

### Classification

| Detected references | Resolved | Result |
| --- | --- | --- |
| none | - | `independent` |
| some | none | `unknown` |
| some | exactly one | `dependent` |
| some | two or more (including an expanded range) | `multiple_dependent` |

`unknown` is used rather than a guess whenever the parser can see that a claim
points somewhere but cannot say where. Classification is syntactic; it is not a
legal characterisation and implies nothing about scope or validity.

### Dependencies as a graph

Edges are stored individually: `제1항 및 제2항에 있어서` on claim 3 produces `3→1`
and `3→2`, not one flattened parent. A tree cannot represent a
multiple-dependent claim, so the database keeps the graph and the UI renders it
as a list.

Refused, with a warning rather than a fabricated edge: references to claims that
are not in the document, self-references, and backwards ranges. Cycles are
detected and reported; real claims cannot contain one, so it is a signal that
something about the document is wrong. Gaps in claim numbering are legal and
produce no warning.

### Source spans and page boundaries

A claim's source is one or more `claim_spans` rows, ordered by
`sequence_number`, each a half-open `[start_char, end_char)` range on one page.
A claim crossing a page break has one span per page:

```
Claim 3
  seq 0 · page 1 · [100, 125)
  seq 1 · page 2 · [0, 16)
```

There is **no flattened document offset anywhere**. The parser concatenates page
text into a temporary buffer so a claim can be matched across a break, and every
buffer offset is mapped back to page coordinates before leaving the module. The
canonical coordinate stays the Phase 2A locator.

Reconstructed claim text is *defined* as the ordered spans resolved against
`document_pages.text` and joined with a single `"\n"` (`PAGE_SPAN_SEPARATOR`) -
the same character page text already uses as its only line separator. `claims.text`
stores that value; tests assert it equals the join of its spans.

Span boundaries exclude the heading and any surrounding whitespace. That is a
choice of *where the claim begins*, not an edit: offsets are moved, text is never
trimmed, so every span still resolves to the exact stored characters. Interior
whitespace is preserved.

### Parser versioning and idempotency

`claim_parse_results` is unique on `(document_id, parser_name, parser_version)`.

| Situation | Behaviour |
| --- | --- |
| First parse | `201` with the new result |
| Same parser version, already `completed` or `no_claims_found` | `200` with the existing result; nothing re-parsed |
| Previous attempt `failed` or stranded in `processing` | Retried **in place**: the old graph is deleted and the same row is reused |
| A future parser version | A new row beside the current one |

Retrying in place is why attempts cannot accumulate without bound, and keeping a
row per version is why an upgraded parser can be introduced without overwriting
a result that existing citations may point at.

### Transaction behaviour

`processing` is committed before parsing begins, so a crash leaves a record that
is distinguishable from a completed one. Then claims, spans, dependency edges,
`claim_count`, and the terminal status are written in **one** transaction, with a
flush in the middle so the composite foreign keys can see the claim rows. A
reader therefore never sees a completed result with missing claims, claims
without spans, edges pointing at absent claims, or a `claim_count` that disagrees
with the rows.

If that commit fails, everything rolls back and the status stays `processing`.

> **Update (2026-11-11 wrap-up):** Since P13 that is no longer the whole story. When
> the graph commit fails, the service rolls back and then commits the result as
> `failed` with `internal_error` and a fixed message, and raises
> `ClaimParsingFailed`, which maps to 422 `claim_parse_failed`. The status stays
> `processing` only if that second commit also fails. The same result row is reused
> by the next parse request, as for any failed attempt. The test for this
> (`test_progression_claim_persistence_terminalization.py`) injects a failure into
> the first commit only; the second-commit branch is known from reading the code.

### Schema (revision 0003)

```
claim_parse_results                     claims
──────────────────────────────          ─────────────────────────────
id                    uuid PK           id              uuid PK
document_id  → documents.id CASCADE     parse_result_id → claim_parse_results.id
status       varchar + CHECK                            CASCADE
parser_name / parser_version            claim_number    integer ≥ 1
claim_count / warning_count             claim_type      varchar + CHECK
warnings              jsonb             text            text
error_code / error_message              UNIQUE (parse_result_id, claim_number)
started_at / completed_at               UNIQUE (id, parse_result_id)
created_at / updated_at
UNIQUE (document_id, parser_name, parser_version)

claim_spans                             claim_dependencies
─────────────────────────────           ────────────────────────────────────
id              uuid PK                 id                  uuid PK
claim_id → claims.id CASCADE            parse_result_id     uuid
sequence_number integer ≥ 0             dependent_claim_id  uuid
page_number     integer ≥ 1             referenced_claim_id uuid
start_char      integer ≥ 0             UNIQUE (dependent, referenced)
end_char        > start_char            CHECK dependent <> referenced
UNIQUE (claim_id, sequence_number)      FK (dependent_claim_id, parse_result_id)
                                           → claims (id, parse_result_id)
                                        FK (referenced_claim_id, parse_result_id)
                                           → claims (id, parse_result_id)
```

Deviations from the suggested design, and why:

- **`warnings` is a JSONB column, not a fifth table.** Warnings are always read
  with their result and never queried on their own; a table would add a join and
  an index for no query benefit. `warning_count` is kept alongside it.
- **`claims` has no `document_id`.** It is reachable through `parse_result`, and
  duplicating it would let a claim disagree with its own parse result about which
  document it came from.
- **`claim_dependencies` carries `parse_result_id`** and uses two composite
  foreign keys into `claims (id, parse_result_id)`. This is what makes
  "same-parse-result integrity" a database guarantee instead of an application
  convention: without it nothing would stop an edge from pointing at another
  document's claim. It is also why `claims` carries the otherwise redundant
  `UNIQUE (id, parse_result_id)`.
- **`end_char > start_char`**, so an empty span cannot be stored: a zero-length
  span cites nothing.

### Quality safeguards

Warnings (recorded, never silently repaired): duplicate claim number (the first
occurrence is kept, and the duplicate heading still acts as a boundary so the
previous claim does not absorb it), empty claim body, out-of-order headings,
malformed claim number, unresolved reference, self-dependency, backwards or
incomplete range, dependency cycle.

Hard failures (the parse is marked `failed` rather than persisted): spans outside
page bounds, and overlapping spans between different claims. Both are structural
invariants of the extraction itself; persisting a violation would corrupt every
citation built on it.

### Known limitations

Korean claim conventions with a minimal, line-anchored English fallback. Nothing
else is attempted: no other language, no claim element decomposition, no
inference of an implicit dependency from wording alone, no OCR. Parsing is
synchronous, and a document with unusual formatting may produce
`no_claims_found` rather than a partial guess - which is the intended behaviour.

> **Update (2026-11-11 wrap-up):** Claim element decomposition now exists, as a
> separate use case over persisted claims (section 12). `ClaimParser` itself still
> does not decompose, and nothing in claim parsing, retrieval, grounding,
> comparison, or Cases consumes elements.

---

## 9. Claim indexing and hybrid retrieval (Phase 3A)

Retrieval only. No generation, no summarisation, no reranking, and no legal
reasoning: a search returns claims that already exist in the corpus, each
carrying the page coordinates it came from.

> **Update (2026-11-11 wrap-up):** A second retrieval surface exists:
> `POST /api/v1/search/descriptions` searches description segments, separately from
> claim search (section 14). This section describes claim retrieval.

```
completed claim parse result
  → deterministic search representation   (indexing/normalization.py)
  → dense embedding                       (indexing/embeddings/…)
  → pgvector row + tsvector               (claim_search_records)
  → dense candidates ┐
  → lexical candidates ┘ → RRF → hydrate with claim_spans → result
```

### The three lifecycles stay separate

```
documents.status            uploaded → processing → completed | failed
claim_parse_results.status  processing → completed | no_claims_found | failed
claim_index_runs.status     processing → completed | failed
```

Indexing writes **neither** of the first two. It is the only one of the three
that depends on an external model, so it is the only one that can fail for
reasons that say nothing about the document or its claims. A document whose
claims cannot be embedded is still a perfectly good document with a perfectly
good claim graph, and it should not start looking broken because a model was
missing.

Only a `completed` claim parse result may be indexed. `no_claims_found` is
rejected with `claim_parse_not_completed` rather than producing an empty index:
reporting "indexed 0 claims" as a success would make an unindexable document
look indexed.

### The embedding provider boundary

```python
class EmbeddingProvider(Protocol):
    name: str            # persisted on every index run
    model: str
    model_version: str   # includes the prompt-prefix scheme, not just weights
    dimension: int
    normalized: bool
    def embed_query(self, text: str) -> tuple[float, ...]: ...
    def embed_documents(self, texts: Sequence[str]) -> list[tuple[float, ...]]: ...
```

Plain Python in, plain Python out: no FastAPI object, no SQLAlchemy model, no
session, no pgvector type. Queries and documents are embedded through *separate*
methods because several current retrieval models - E5 among them - are trained
with asymmetric prefixes and score measurably worse when a query is embedded as
though it were a passage. A single `embed()` would make that mistake
unrepresentable.

Two implementations:

| | `FakeEmbeddingProvider` | `SentenceTransformerEmbeddingProvider` |
| --- | --- | --- |
| Vectors from | SHA-256 of each token | a real local model |
| Downloads | nothing | weights, once, into a cache volume |
| Used by | the whole test suite, offline installs | development and the evaluation |
| Semantic | **no** | yes |

The fake provider is not a mock. It is a real implementation whose vectors are
hash-derived, deterministic across processes, and *lexically* sensitive - texts
sharing tokens land closer together - so retrieval tests can assert exact
orderings. It cannot match a paraphrase, and no number produced with it says
anything about retrieval quality.

### The model this phase was validated with

`intfloat/multilingual-e5-small`, 384 dimensions, unit-normalised, CPU.

Chosen because this phase validates a retrieval *architecture* on a CPU-only
host: it loads in seconds rather than minutes and indexes a claim set without a
GPU. Measured in the API container on this machine:

| | |
| --- | --- |
| Cold load + first query | 9.5 s |
| Embedding a 26-claim batch | 139 ms (5.4 ms/claim) |
| Query embedding | 8.7 ms |
| Model cache on disk | 941 MiB (multiple serialisation formats) |
| First index request, 12 claims | 12.3 s (includes cold load) |
| Second index request, 14 claims | 0.1 s (model already resident) |

**This is not a claim that it is the best Korean embedding model.** No Korean
retrieval benchmark was run to choose it, and the synthetic evaluation in
`evals/` is far too small to rank models. BAAI/bge-m3 is stronger on most
multilingual benchmarks and is a reasonable future upgrade - it is also
1024-dimensional, which under the fixed-width column below means a migration
rather than a settings change.

### Fixed vector dimension, and what that costs

`claim_search_records.embedding` is `vector(384)`, migrated at that width, with
an HNSW index built on it.

- **A different model of the same width** is a settings change plus a re-index.
  It gets a new index run beside the existing one, and both can coexist.
- **A model of a different width** needs a new migration, and realistically a
  storage-profile table so several widths can coexist during a transition.

This is a deliberate MVP limitation rather than an oversight. A fully dynamic
multi-dimension vector store is a meaningful amount of machinery to carry for a
capability nothing currently needs, and the cost of adding it later is one
migration - paid when a second width actually exists.

### The retrieval profile

Vectors from different models are not points in the same space, and neither are
records normalised by different rules or tokenised by different lexical
strategies. Mixing them produces a ranking that looks fine and means nothing, so
compatibility is explicit:

```
profile_key = provider | model | model_version | dimension
            | normalized | normalization_version
            | lexical_strategy | lexical_strategy_version
```

That single string is stored on every index run, and it does two jobs:

1. **Idempotency.** `UNIQUE (claim_parse_result_id, profile_key)` *is* the
   identity rule. This is the one material deviation from a nine-column unique
   constraint, which would be both unreadable and easy to get subtly wrong at
   query time. The individual columns are still stored, because a run has to be
   readable in `psql` without decoding a key.
2. **Profile selection.** Search filters on one indexed equality instead of
   matching nine columns.

Search selects **one index run per document**: the newest completed run whose
profile matches the configured one, via `DISTINCT ON (document_id)`. A document
with several parse results - one per claim parser version - therefore
contributes each claim once, and an upgraded parser's index supersedes its
predecessor without the old rows having to be deleted. Nothing outside the
active profile is searched, so a deployment that switches models sees an empty
result set with `searched_index_run_count = 0` until it re-indexes, rather than
silently ranking against stale vectors.

### The search representation

What gets indexed is derived from persisted claim data only:

```
청구항 3 다중종속항 인용 제1항 제2항
<the claim body, normalised>
```

The header carries facts that are already deterministic and that people actually
search for. It exists mostly for lexical search: a dependent claim's body does
not always name its parents in a form full-text search can tokenise.

Normalisation, applied identically to indexed text and to incoming queries -
because a query folded differently from the corpus simply will not match:

1. **NFKC**, which also maps full-width digits to ASCII, so `１００도` and `100도`
   are the same string.
2. **Line-ending normalisation** before whitespace collapsing, so a claim
   reconstructed on one platform matches the same claim from another.
3. **Whitespace collapsing**, including U+3000, which NFKC leaves alone.
4. **Case folding** - a no-op for Hangul, but it makes the Latin fragments in a
   Korean patent (units, symbols, an English fallback claim) match.

Punctuation is deliberately left alone: stripping it would merge `제1항` with
`제1 항` but would also destroy decimal points and hyphenated part numbers,
which are exactly the tokens a patent search needs to keep.

**Normalised text is not a coordinate system.** Folding changes string lengths,
so an offset into it addresses nothing in the source document. `claims.text` is
never modified, and `claim_search_records` deliberately stores no offsets of its
own - provenance resolves through `claim_spans` and nowhere else.

### Lexical retrieval, and its Korean limits

PostgreSQL has no Korean morphological analyser. The `simple` configuration
splits on whitespace and punctuation and lowercases; that is all. For an
agglutinative language that has one dominating consequence: the corpus contains
`센서에서` and `데이터를` while a user types `센서` and `데이터`, and full-text
search sees those as unrelated tokens.

So the lexical channel retrieves through three indexed branches at once:

| Branch | Index | What it recovers |
| --- | --- | --- |
| `search_vector @@ tsq` | GIN on tsvector | whole-token matches: numbers, units, Latin terms, `제1항` forms |
| `normalized_text LIKE '%q%'` | GIN trigram | verbatim substrings |
| `q <% normalized_text` | GIN trigram | approximate substrings - Korean compounds and josa-suffixed forms |

> **Update (2026-11-11 wrap-up):** For claims there is now a fourth, term-level
> eligibility predicate, OR-ed with these three. See "Term-level lexical fallback"
> below.

The tsquery is an **OR** of one `plainto_tsquery` call per normalised term. AND
semantics would mean a single unmatched word suppresses the whole result, which
is fatal here because particle attachment guarantees some words will not match
exactly. `plainto_tsquery` rather than `to_tsquery` because it treats its
argument as plain text: a term containing `&`, `|`, `!` or a bracket is data,
not syntax, and cannot raise a parse error mid-request.

The trigram threshold is **0.25**, set from measurement rather than taste:
`환경감시모듈` scores 0.286 against a claim reciting `환경 감시 모듈`, because
inserting a space changes the trigrams on both sides of every word boundary.
pg_trgm's default of 0.6 would reject exactly the match this channel exists for.
It is set with `set_config(..., is_local => true)` per transaction, so the
ranking cannot depend on what a pooled connection was last used for.

Scoring is a fixed weighted sum of three components, each in `[0, 1]`:

```
0.45 × ts_rank_cd(…, normalisation flag 32)   whole-token evidence
0.30 × word_similarity(query, text)           trigram heuristic
0.25 × exact containment (0 or 1)             the query, verbatim, in the claim
```

Ordered by score, then claim number, then claim id - so the same corpus and
query always produce the same list.

**Do not overstate this.** It is substring and token matching, not morphology.
It cannot resolve a synonym, and it will occasionally match a coincidental
substring. Real Korean lexical search wants an analyser such as mecab-ko behind
a custom text-search configuration, which is a database provisioning decision
rather than an application change.

### Term-level lexical fallback (P11)

The fallback was added in P11, after the original text of this chapter; P12 added its
boundary tests without changing runtime code. The lexical channel now admits candidates
through four OR-ed branches, not the three listed above.

**The problem.** A multi-word Korean question can fail every older gate even when one noun
differs from the claim only by a particle. In the regression test the query
`측정값은 완전히무관한질문토큰` meets a claim reciting `측정값을`: no full-text match, not a
verbatim substring, and whole-query `word_similarity` below 0.25. The claim never reaches
fusion.

**The change.** One more eligibility predicate in `retrieval/lexical.py`:
`GREATEST(word_similarity(:term_i, normalized_text), …) >= :term_similarity_threshold`,
with the threshold fixed at 0.60 and passed as a bound parameter, so unlike the `<%` branch
it does not depend on the session setting. The terms are those that already feed the
tsquery: `query_terms()` splits the normalised query on whitespace and keeps the first 32.

**What did not change.** The score formula and weights, the ordering, the `LIMIT`, fusion,
the dense channel, and the stored search records. `LEXICAL_STRATEGY_VERSION` stayed `"v1"`,
so `profile_key` is unchanged. The fallback is query-time only: it alters which stored
records are eligible, no record is touched, and no index run needs rebuilding. The module
states the contract: term-level checks "affect only candidate eligibility and do not
introduce a second score scale".

Decisions worth stating:

- **0.60 here, 0.25 for the whole query.** The code says why: the permissive compound
  threshold, applied per term, "admits too many unrelated multi-word-query candidates and
  disturbs fusion". The fallback only recovers a locally near-identical token.
- **Claims only.** `ClaimSearchService` calls the lexical retriever in `lexical` and
  `hybrid` modes, so the fallback reaches `POST /search/claims`, grounded answers, claim
  comparison, and Case grounded results (which wrap the grounded service). A comparison
  query is the whole target claim, so only its first 32 terms feed the fallback. Description
  search has its own lexical SQL, with three branches and no term fallback.

It is still trigram and substring matching, not morphology, and cannot resolve a synonym.
Coincidental matches can enter the candidate set, a risk P11 records; ordering decides
whether they surface. The predicate is a function call, not the `<%` operator, and whether
PostgreSQL serves it from the trigram index was not measured.

**Verification.** `test_progression_term_lexical_fallback.py` runs on PostgreSQL with
`pg_trgm`, against one synthetic claim. Positive: for the query above, full-text and phrase
matches are false, whole-query similarity is under 0.25, term similarity is at least 0.60,
and lexical-mode search returns the claim. Negative: for `측정가치는 …` term similarity is
under 0.60 and the claim is not returned. Separately, `make verify-deterministic-regression`
requires `g01-single-storage` to succeed with `collector#1` cited, under the fake embedding
provider, the case P11 recorded this change as recovering. Both are regression evidence,
not a measure of retrieval quality.

### Dense retrieval

Cosine similarity through pgvector's `<=>` operator, reported as `1 - distance`
so that larger is better, matching how the lexical and fused scores already read.
Cosine is exact here because the provider normalises at encode time.

The ANN index is **HNSW** (`vector_cosine_ops`) rather than IVFFlat: it needs no
training pass over an existing corpus and no list-count tuning, which matters
when an index starts at a handful of claims and grows. An IVFFlat index built on
a small corpus stays badly tuned until it is rebuilt.

One structural detail worth knowing before editing that query: pgvector can only
serve an `ORDER BY` that is *exactly* the distance expression. Adding tie-break
columns there silently turns the whole thing into a sequential scan. So the
candidate set is taken in an inner query ordered by distance alone, and the outer
query re-sorts that small set by `(distance, claim_number, claim_id)` for
determinism.

No vector is ever pulled into Python to be compared - the embedding column is not
even selected.

On the 26-claim validation corpus the planner chooses a bitmap scan plus sort
over the HNSW index, which is correct: traversing a graph to order 12 rows is
slower than sorting them. The index is present, valid, and verifiably used once
the planner is asked to use it; it earns its keep at a corpus size this project
has not yet reached.

### Reciprocal Rank Fusion

```
fused_score(claim) = Σ over channels  1 / (k + rank_in_that_channel)
```

RRF is used instead of a weighted sum of the raw scores because the raw scores
are not comparable. A cosine similarity of 0.82 and a lexical score of 0.74 are
numbers produced by unrelated procedures on unrelated scales; adding them - or
even min-max normalising them per query - invents a relationship that does not
exist and makes the blend depend on how tightly the day's result set happens to
be clustered. Ranks discard the magnitudes and keep only the ordering each
channel is actually entitled to assert.

`k` defaults to **60**, the value from the original formulation. It sets how
sharply rank 1 outweighs rank 10: a large `k` flattens the curve so that
agreement between channels matters more than either channel's top position.

- A claim retrieved by both channels appears once and receives both
  contributions.
- A claim retrieved by only one channel remains eligible, and the other
  channel's rank and score are reported as **null** - which is information, not
  missing data. `dense_rank: null` means the dense channel did not retrieve this
  claim, and a client must render that rather than coerce it to zero.
- Ties break by claim number, then claim id. Both are properties of the data
  rather than of the query, which is what makes a retrieval regression test
  meaningful.

`dense` and `lexical` modes go through fusion too, with one channel. Since
`1/(k + rank)` is strictly decreasing in rank, the fused order is exactly that
channel's own order, and the response shape stays identical across all three
modes instead of having a fused score that sometimes exists.

### Index lifecycle, idempotency, and retry

```
1. refuse anything but a completed document with a completed parse result
2. return an existing completed run for the same profile, untouched
3. commit 'processing'  ← before the model runs
4. embed
5. write every search record + 'completed' in ONE transaction
```

Step 3 exists because model loading is the slowest and least reliable step in the
system; a crash there must leave a record distinguishable from both "never
started" and "finished". Step 5 is one commit because a partially embedded claim
set must never be visible as a completed index - search would return a subset of
a document's claims as though it were all of them.

| Situation | Behaviour |
| --- | --- |
| First index for a profile | `201` with the new run |
| Same profile, already `completed` | `200` with the existing run; nothing re-embedded |
| Previous attempt `failed` or stranded in `processing` | Retried **in place**: records deleted, same row reused |
| A different profile | A new run beside the current one |

Retrying in place is why attempts cannot accumulate: the unique constraint means
one row per `(parse result, profile)`. The row is locked `FOR UPDATE` while it is
being retried, so two concurrent index requests for the same document serialise
instead of racing to write the same records.

### Schema (revision 0004)

```
claim_index_runs                          claim_search_records
────────────────────────────────────      ──────────────────────────────────────
id                       uuid PK          id               uuid PK
claim_parse_result_id →  CASCADE          index_run_id  → claim_index_runs CASCADE
status         varchar + CHECK            claim_id      → claims            CASCADE
profile_key    varchar(512)               document_id   → documents         CASCADE
embedding_provider / _model / _version    claim_number     integer
embedding_dimension      integer > 0      normalized_text  text
vectors_normalized       boolean          search_vector    tsvector
normalization_version    varchar(32)      embedding        vector(384)
lexical_strategy / _version               created_at / updated_at
indexed_claim_count      integer ≥ 0      UNIQUE (index_run_id, claim_id)
error_code / error_message
started_at / completed_at                 GIN   (search_vector)
created_at / updated_at                   GIN   (normalized_text gin_trgm_ops)
UNIQUE (claim_parse_result_id,            HNSW  (embedding vector_cosine_ops)
        profile_key)
```

Decisions worth stating:

- **`profile_key` instead of a nine-column unique constraint.** Explained above.
- **`document_id` is denormalised onto the search record.** It is reachable
  through `claim_id → claims → claim_parse_results`, but document scoping is on
  the hot search path and would otherwise cost two joins. The indexing service is
  the only writer, so it cannot drift.
- **Everything CASCADEs from `documents`.** A search record must never outlive
  the claim it projects, or a query could return text an operator believes they
  deleted. Deleting a parse result likewise removes the index built from it.

  > **Update (2026-11-11 wrap-up):** That is true of the retrieval tables this
  > revision adds, but not of every table that references `documents`.
  > `analyst_case_evidence.document_id` is `ON DELETE RESTRICT` (revision `0009`), so
  > a document cited by a stored Case result cannot be deleted in SQL until that
  > result, or its Case, is deleted (section 15). The description-evidence tables
  > (`0007`) and the Case document associations (`0008`) do cascade from
  > `documents`.
- **`search_vector` is maintained by the application**, not a trigger, so the
  exact text that was embedded is also the text that was tokenised. The two
  channels can never disagree about what a record contains.
- **Search records are derived artifacts.** They are not the source of truth for
  claim content, and they hold no source offsets. `claims` and `claim_spans`
  remain the only citation coordinate.
- **pg_trgm is enabled by this migration**, alongside the `vector` extension
  from 0001.

### Retrieval API

| Endpoint | Behaviour |
| --- | --- |
| `POST /documents/{id}/claims/index` | Synchronous. `201` for a new completed run, `200` for an equivalent existing one |
| `GET /documents/{id}/claims/index` | The most recent run, whatever profile it used |
| `POST /search/claims` | `query`, `mode`, `document_ids`, `top_k`, candidate counts |
| `POST /search/descriptions` | The same shape over description segments, not claims; separate from claim search (section 14) |
| `POST /compare/claims` | One target claim against one reference document, by retrieval only (section 13) |

Search is a POST rather than a GET with query parameters. The request has
structure that does not flatten into a query string cleanly, and - the deciding
reason - a patent search query is confidential: a GET would put it in the URL,
where it lands in access logs, proxy logs, and browser history by default.

New error codes:

| Code | Status | Meaning |
| --- | --- | --- |
| `claim_parse_not_completed` | 409 | A parse result exists but did not complete |
| `claim_index_failed` | 422 | Indexing ran and could not finish |
| `claim_index_not_found` | 404 | Nothing indexed for this document yet |
| `embedding_model_unavailable` | 503 | Model missing, uncached, or out of memory - retryable |
| `embedding_dimension_mismatch` | 500 | Provider width ≠ migrated column; a configuration error |

`503` rather than `500` for a missing model is deliberate: the caller is being
told to retry, not that their request was wrong.

> **Update (2026-11-11 wrap-up):** Only the indexing path maps the provider failure
> to this code: `ClaimIndexingService` catches `EmbeddingError` and records a failed
> run. At query time - claim search, comparison, grounded answers, and description
> indexing and search - the provider's exception is not an `AppError` and nothing
> catches it, so by reading `main.py` the generic handler would answer 500
> `{"detail": "Internal server error"}`. The search, comparison, and
> description-search routes still declare 503 in their OpenAPI responses. This is
> by reading; no test covers it.

Every result carries `source_spans` in the canonical
`(document_id, page_number, start_char, end_char)` form - the same coordinates
the claim endpoints return, resolvable against `document_pages.text`. Retrieval
changes how a claim is *found*; it never changes where the claim *is*.

### Query privacy

A patent search query is a statement of what someone is working on, which in this
domain is confidential before anything is filed - and logs outlive requests and
get shipped elsewhere. So the query itself is never logged.

| Logged | Never logged |
| --- | --- |
| query length, 12-char digest prefix | the query |
| retrieval mode, profile, index run id | claim text, page text |
| candidate counts, result count | embedding values |
| duration, error code | full document digests, cache paths |

The digest prefix is enough to correlate a report ("my search returned nothing")
with a log line, and not enough to reconstruct what was searched for. Model-load
failures log the exception *type* only, because the exception text can contain a
cache path or a URL with a token.

### Known limitations of this phase

- Korean lexical matching is token and trigram based, with no morphological
  analysis. See above; this is the largest quality gap.
- One vector width. A wider model needs a migration.

  > **Update (2026-11-11 wrap-up):** Two tables are now migrated at `vector(384)`:
  > `claim_search_records` (`0004`) and `description_search_records` (`0007`).
- Indexing is synchronous and holds a request open. Acceptable at claim scale -
  26 claims embed in 139 ms once the model is resident - but the first request
  after a restart pays the ~9.5 s model load.
- No reranking. A cross-encoder over the fused top-k is the obvious next
  retrieval-quality lever and is deliberately out of scope here.
- The evaluation corpus is 26 synthetic claims. It can detect a broken channel
  and compare two configurations; it cannot establish retrieval quality.
- No incremental indexing: re-indexing a document rewrites all of its records.
- Search has no pagination beyond `top_k`.

---

## 10. Local LLM provider boundary (Phase 4A-1)

This phase adds the ability to generate text with a local model, and nothing
that uses it. There is no retrieval-grounded answering, no claim analysis, no
chat, and no citation - those are Phase 4A-2 and later. What exists is the
boundary, three implementations of it, and a narrow diagnostics surface to prove
it works.

The reason for building it as its own phase: generation quality is unmeasurable
until generation is *reliable*, and reliability here means timeouts, error
mapping, and schema enforcement rather than prompt design. Getting those wrong
under a prompt is much harder to see.

### What the boundary is

`claimtrace_api/llm/` imports no web framework, no ORM, no database driver, and
nothing that knows what a claim is. A test asserts this by scanning the package
for forbidden imports, so it is a property of the build rather than a habit.

The protocol (`llm/base.py`):

```python
class LLMProvider(Protocol):
    @property
    def name(self) -> str: ...
    def get_metadata(self) -> ProviderMetadata: ...          # sync, no network
    async def check_health(self) -> HealthStatus: ...        # never raises
    async def generate(self, request) -> GenerationResponse: ...
    async def generate_structured(self, request, output_model) -> StructuredGeneration[T]: ...
    async def aclose(self) -> None: ...
```

Two generation methods rather than one. `generate` returns whatever the model
said; `generate_structured` returns a *validated instance of a type the caller
named*, or raises. Collapsing them into one method returning `str` would push
JSON parsing, schema validation, and the choice of how hard to constrain the
model onto every caller, and each caller would get it slightly wrong.

`get_metadata()` is synchronous and side-effect free so the status endpoint can
render configuration even when the provider is unreachable. `check_health()`
never raises, because an unavailable model server is a result to report, not an
exception to survive.

### Request and response types

Plain frozen dataclasses (`llm/models.py`), validated on construction.

A `GenerationRequest` carries an ordered `tuple[Message, ...]`, a
`GenerationOptions`, and a correlation id. The message sequence is constrained
rather than free-form: at least one message, at most one system message and only
in first position, and the last message must be from the user. Every target
server treats a mid-conversation system turn differently, and a request ending on
an assistant turn is asking the model to continue its own text - a different
operation this phase does not offer.

**There is no model field on the request.** The model comes from server
configuration and cannot be selected per call, so nothing reaching the
diagnostics endpoint can repoint the deployment at another model. A test asserts
the attribute's absence.

`GenerationOptions` covers temperature, max output tokens, stop sequences, seed,
and a per-request timeout, each bounded absolutely as well as by configuration.
`None` means "the provider's default", which is deliberately not the same as a
zero: `temperature=0.0` requests greedy decoding, `temperature=None` leaves
whatever the server was started with.

A `GenerationResponse` carries the text, provider, model, model version, finish
reason, `TokenUsage`, duration, provider request id, the structured-output mode
used, the attempt count, and `warnings`. Every token count is independently
nullable, because "the provider did not report it" is a real state and reporting
it as `0` would be a fabricated measurement.

`warnings` is where a degraded capability becomes visible - a prompt-only JSON
fallback, a seed requested at non-zero temperature, or output truncated at the
token limit. A caller that ignores warnings still gets a correct answer; a caller
that reads them can tell how strongly it was enforced.

### Capability model

Every capability defaults to *unsupported*. A flag is turned on only where the
adapter implements it against a documented API and a test covers it - "the server
might support this" is not a capability, because the service above uses these
flags to decide whether an answer can be trusted.

| Capability | fake | ollama | openai_compatible |
|---|---|---|---|
| text generation | yes | yes | yes |
| structured output | native JSON Schema | native JSON Schema | configurable |
| seed | yes | yes | yes |
| usage metadata | yes | yes | yes |
| model listing | yes | yes | yes |
| streaming | **no** | **no** | **no** |

Streaming is represented in the contract and reported unsupported everywhere.
Ollama's `/api/chat` does support it; this adapter does not implement it, and a
capability describes what the adapter has been validated to do.

`StructuredOutputMode` is ordered by strength:

- `native_json_schema` - the server constrains decoding to the schema.
- `native_json_object` - valid JSON guaranteed, the schema is not.
- `prompt_constrained_json` - nothing enforced; the schema is described in the
  prompt and the reply is validated strictly on arrival. Always warned about.
- `unsupported` - structured output is refused rather than faked.

`supports_structured_output` and `structured_output_is_native` are separate
properties, and the diagnostics UI shows both. "Supported" and "enforced by the
server" are different claims.

### Structured output pipeline

1. Convert the requested Pydantic model to JSON Schema.
2. Send the strongest structured-output instruction the provider supports.
3. Receive the reply.
4. Extract exactly one JSON value.
5. Validate it against the schema.
6. Return the validated value *and* the response metadata.

Step 5 runs even when the server enforced the schema in step 2. An older Ollama
silently ignores an unknown `format`, a truncated reply is still truncated, and -
as Phase 4A-1 validation established - **constrained decoding does not enforce
value constraints** (see "What real Ollama validation found"). Enforcement
upstream is a reason to expect valid output, never a reason to skip checking it.

Nothing is coerced. A reply that does not satisfy the schema produces
`llm_structured_output_validation_failed`, never a partially populated model.

### JSON extraction and validation policy

`llm/json_output.py` is deliberately unforgiving. A model that wraps its answer
in an apology, emits two objects, or stops half way through has not answered the
question, and a parser that digs the "probably intended" object out of that text
turns a visible failure into an invisible one.

Accepted:

- exactly one complete JSON value, with only whitespace around it;
- an object when the schema describes one, an array when it describes one
  (detected from the model's own JSON Schema, so a `RootModel[list[...]]` works);
- that value wrapped in a single Markdown fence, in one narrow anchored form.

Rejected, each with its own message:

- prose before the JSON, prose after it, or a second JSON value;
- **truncated** JSON, reported distinctly - the usual cause is the output token
  limit, which is fixed by raising it rather than by reprompting;
- comments, trailing commas, and every other JSON5-ism;
- values that parse but fail the schema;
- **unknown fields**, unless the schema opts in with `extra="allow"`. Pydantic
  ignores them by default, which for generated output is the wrong default: a
  model that invents a field has misunderstood the schema, and dropping the
  evidence hides that.

Fence removal is anchored at both ends of the whole text, and refuses when a
third fence appears. An unterminated fence is left alone so the failure is
reported rather than silently repaired.

Notably absent is any search for the first `{` in a blob of prose. That technique
works right up until a model writes `{` in a sentence.

Validation failures are summarised as field path plus rule - `confidence:
less_than_equal` - derived from the schema and never from the generated values.
Pydantic's own `str(exc)` embeds the offending input, which for a model response
is exactly the content this project keeps out of logs and error bodies.

### Error taxonomy

`LLMErrorCode` (`llm/errors.py`) is provider-neutral; adapters map every provider
failure onto it. Each code has a matching `ErrorCode` and HTTP status in
`core/errors.py`, and a test asserts the two enums stay in step, so a new provider
failure cannot reach HTTP unmapped.

| Code | HTTP | Retryable | Meaning |
|---|---|---|---|
| `llm_configuration_error` | 500 | no | a required setting is missing or invalid |
| `llm_provider_unavailable` | 503 | **yes** | reachable but not ready to serve |
| `llm_connection_error` | 503 | **yes** | the request was never delivered |
| `llm_request_timeout` | 504 | no | the deadline expired |
| `llm_model_not_found` | 503 | no | the configured model is not present |
| `llm_authentication_error` | 500 | no | *our* credential to the upstream was rejected |
| `llm_rate_limited` | 429 | **yes** | the provider is throttling us |
| `llm_context_length_exceeded` | 422 | no | prompt + output exceeds the window |
| `llm_invalid_request` | 400 | no | malformed request |
| `llm_invalid_provider_response` | 502 | no | unrecognised response shape |
| `llm_malformed_json` | 502 | no | structured output was not parseable JSON |
| `llm_structured_output_validation_failed` | 422 | no | JSON parsed, schema not satisfied |
| `llm_generation_cancelled` | 503 | no | the caller went away |
| `llm_unsupported_capability` | 501 | no | asked for something unvalidated |
| `llm_internal_provider_error` | 502 | no | the provider failed internally |
| `llm_diagnostics_disabled` | 404 | no | the diagnostics endpoints are off |

The split that matters is between "the operator must change something" (5xx - a
caller cannot fix a missing model or a wrong base URL) and "the request was
wrong" (4xx - too long, or a schema the model cannot satisfy). `model_not_found`
is 503 rather than 404 because the *model* is missing, not the endpoint, and the
remedy is an `ollama pull` on the server.

Every error carries a safe public code, a safe public message, a retryable flag,
the provider and model where known, and the upstream status where safe. The
originating exception is attached with `raise ... from` so a traceback reaches the
log, and is never rendered into the message.

**Provider error bodies are read to classify and then discarded.** Every message
returned from an adapter is written from values the adapter already holds. An
OpenAI-compatible error routinely echoes part of the offending request back, which
for this application is patent text; tests assert that a prompt planted in an
error body does not reach the message or the repr.

### Timeout policy

Three deadlines, because they mean different things and are tuned against
different failures:

- `LLM_CONNECT_TIMEOUT_SECONDS` (5s) - "nothing is listening" should fail in a
  second or two.
- `LLM_READ_TIMEOUT_SECONDS` (120s) - a small model on CPU genuinely takes this
  long. Generous on purpose.
- `LLM_MAX_TIMEOUT_SECONDS` (180s) - bounds one whole call *including retries*.

A per-request timeout may only ever **lower** the ceiling; anything larger is
clamped rather than rejected, because the configured maximum is the operator's
decision and a caller does not get to raise it. Lowering the overall deadline also
lowers the read timeout, so the call fails at the deadline with a timeout error
rather than hanging past it.

The overall deadline wraps the retry loop, not each attempt. `asyncio.timeout`
re-raises `TimeoutError` only when it was the one that cancelled the body, so an
external `CancelledError` passes straight through and stays a cancellation -
never converted into a generic internal error. The service logs cancellation and
re-raises it unchanged.

### Retry policy

Two attempts by default, not five. A local model server is not a flaky cloud API:
when it refuses a connection the usual cause is that it is not running, and
hammering it four more times converts a fast, clear failure into a slow one.

Retried: connection failures, connect and pool timeouts (the request was never
delivered, so a replay has no side effects), `429` with an optional `Retry-After`,
and `502/503/504`.

Not retried: authentication, invalid request, model-not-found, context length,
malformed JSON, and schema validation failures - each fixed by changing
something, never by asking again. And **not read timeouts**: by the time a read
times out the server may already be generating, and a replay doubles the load on a
machine that has just demonstrated it is too slow.

Backoff is exponential from 250 ms, capped per-wait at 4 s and in total at 8 s, so
a generous attempt count can never become an unbounded wait. A provider-supplied
`Retry-After` wins over the computed backoff but is still clamped - an upstream
does not get to hold a request open for five minutes.

Retryability is decided by the adapter that mapped the failure and travels on the
error; the retry module only reads the flag and never re-inspects a status code.
`run_with_retry` takes its sleep function as an argument, so tests exercise the
real backoff arithmetic without spending the real seconds.

### The Ollama adapter

Speaks the documented HTTP API directly: `GET /api/tags` to enumerate installed
models, `POST /api/chat` with `stream: false` to generate. Structured output uses
the `format` parameter, which since v0.5 accepts a full JSON Schema and constrains
decoding to it.

Health separates two states that fail separately and are fixed differently: an
unreachable server is an infrastructure problem, a missing model tag is one
`ollama pull` away. The health message includes the exact command.

A bare model name is matched against the `:latest` form as well, because
`ollama pull qwen2.5` installs `qwen2.5:latest` and the most common way to pull a
model would otherwise report as missing. The model digest discovered from
`/api/tags` is recorded as the model version: an Ollama tag is mutable, so the
digest is what actually identifies the weights that answered.

### The OpenAI-compatible adapter

Targets a model server **on your own network** - vLLM, llama.cpp's server, LM
Studio, TGI. The hosted OpenAI service is explicitly not a supported target and is
not documented as one: ClaimTrace processes unpublished patent text, and sending
that to a third party is a decision for a deployment to make deliberately, not
something an adapter should make easy by accident.

No vendor SDK. `POST /chat/completions` and `GET /models` are a few dozen lines
against `httpx`, and the `openai` package would bring a second retry policy, a
second timeout model, and a second exception hierarchy into the one place in this
codebase whose job is to have exactly one of each. `httpx` moved from the dev
extra to a runtime dependency for this.

Structured output is **configurable** rather than assumed, because compatibility
is a spectrum: vLLM enforces a schema through guided decoding, llama.cpp's server
historically honoured only `json_object`, and some servers accept
`response_format` and quietly ignore it. Guessing optimistically produces
unvalidated output that looks enforced. In `prompt_constrained_json` mode the
adapter sends **no** `response_format` at all and appends the schema as a final
user turn - sending a field a server ignores is precisely how an unenforced
request comes back looking enforced.

The API key is held as a `SecretStr` for its whole life, never stored on the
instance as plain text, and reaches `str()` only inside per-request header
construction. Tests assert it appears in no repr, no metadata, no log record, and
no error.

### The fake provider

Not a mock: a real implementation of the protocol that runs the same request
validation, the same JSON extraction, and the same schema validation as the
network adapters, with only the transport replaced. A test that passes against it
has exercised every layer except the socket.

It is also the default (`LLM_PROVIDER=fake`), which is what keeps `docker compose
up` working with nothing downloaded and CI free of network. Given any schema it
synthesises a conforming payload, so the whole application - diagnostics UI
included - works end to end with no model present.

Everything a test needs to steer is a constructor argument: the text to return, a
raw string for structured calls (so malformed JSON and schema mismatches are
reachable through the production pipeline), an error to raise, how many calls it
applies to before succeeding, and how long to take. Calls are recorded so a test
can assert what the layer above actually sent. Nothing is monkey-patched.

### Provider selection

A factory (`llm/registry.py`), not a plugin system. `LLM_PROVIDER` is a `Literal`,
so an unknown name fails at configuration load. The branch that is not taken is
never constructed: a fake-provider deployment never validates an Ollama URL it
does not use, and adapter imports are deferred into their branches.

Construction opens no socket. The application must come up, serve `/health`, and
report the LLM as unreachable, rather than refusing to start because a model
server is down. The provider is built once at startup and shared, because the
HTTP adapters own a connection pool; `get_llm_provider` is the dependency a test
overrides to inject a fake.

### The application service

`services/llm_generation.py` validates requests, enforces the configured
ceilings, resolves the provider, maps the LLM taxonomy onto the application's, and
emits the safe operational log line.

Bounds are applied two different ways on purpose. An oversized prompt is
**rejected**, because silently truncating patent text would change the question
being asked. An oversized token limit or timeout is **clamped**, because those
only describe how much room the answer is given.

What it does not do, asserted by a test on its constructor signature: it takes no
database session and no retrieval collaborator. Phase 4A-1 generates; it does not
ground. Keeping this class empty of retrieval is what makes Phase 4A-2 a new
collaborator rather than an untangling.

### Diagnostics API

`GET /api/v1/llm/status` is always served and always returns 200, including when
the provider is unreachable - an unavailable model server is what this endpoint
exists to report. It distinguishes four states as separate fields (`configured`,
`available`, `model_available`, `diagnostics_enabled`) rather than collapsing them
into one status string, because "Ollama is not running" and "Ollama is running
without the model" have completely different fixes. It returns no secrets; the
base URL is reported with any userinfo removed.

`POST /api/v1/llm/diagnostics/generate` and
`POST /api/v1/llm/diagnostics/structured` are development tooling, gated on
`LLM_DIAGNOSTICS_ENABLED`. That setting is tri-state: unset follows the
environment (on in development, off everywhere else), and `true`/`false` override.
Disabled returns **404** rather than 403 - when off, the route is not part of the
deployment's surface, and "forbidden" would confirm it exists.

Neither endpoint accepts a model, a provider, a base URL, or a JSON Schema.
Request models are `extra="forbid"`, so attempting any of them is a 422 rather
than a silently ignored field. The structured endpoint validates against one fixed
built-in schema (`title`, `keywords[]`, `confidence`); internal Python callers may
pass any approved Pydantic model to the service directly.

The structured endpoint returns the *validated object*, never the raw text. That
would be the one place in this API where unvalidated model output is echoed back
verbatim.

`/health` and `/ready` are untouched. The LLM is optional infrastructure, and
making the liveness of the whole service depend on a model server would be a
regression in operability.

### Diagnostics UI

`/llm` renders provider identity, reachability, capability flags, and the
configured limits, then offers two independent one-shot forms. It is not a chat
interface: no history, no message list, no streaming, no retrieval context, and no
arbitrary schema input.

Nullable usage fields render as an em dash rather than `0`, matching the
convention the search UI already uses for an absent retrieval channel: "not
reported" and "zero" are different facts and only one is a measurement. Warnings
render rather than being swallowed, so a prompt-only fallback is visibly
distinguishable from a server-enforced one.

### Observability and privacy

Structured log lines carry provider, model, request id, prompt **character
count**, message count, requested token limit, structured-or-plain mode, attempt
number, duration, finish reason, token counts, safe error code, and retryable
flag.

They never carry prompts, system instructions, generated output, structured
values, API keys, authorization headers, raw HTTP payloads, or document and claim
text. `log_fields()` on the request, the response, and the error is the only path
into a log line, and tests plant confidential strings in prompts, replies, and
error bodies and assert they do not appear in emitted records.

The request correlation id is a random `uuid4` prefix, not a hash of the prompt. A
content-derived id would be a weak fingerprint of confidential text sitting in
every log line.

Expected failures - an unreachable server, a schema mismatch - log at info with
safe fields and no traceback. A stack trace for "the model server is not running"
is noise that trains an operator to ignore stack traces.

### Security

Provider URLs come only from server configuration, never from a request body,
query parameter, or header, so there is no user-controlled URL to defend. What
`validate_base_url` guards is operator error: the scheme must be `http` or
`https`, a host must be present, and plaintext `http` is permitted only for a
local address - loopback, a private or link-local IP, `host.docker.internal`, or a
single-label Compose service name. Anything with a dot must use TLS, so a
credential cannot be sent in the clear to a routable host. Rejection names the
setting rather than quoting the URL, which might carry a credential.

Prompt size, output tokens, and timeout are bounded at the schema, at the service,
and absolutely in the domain model.

### Database policy

**No migration was added, and this is deliberate.** The schema remains at revision
0004. Prompts, responses, model diagnostics, provider health history, and token
usage are not persisted: provider diagnostics are runtime infrastructure, not
domain data, and persisting prompts and completions would create a store of
confidential patent text with no feature depending on it. No empty migration was
created to advance the revision number.

> **Update (2026-11-11 wrap-up):** The schema has moved on since this phase:
> revisions `0005` to `0009` added domain tables (section 6). Prompts, raw
> completions, and provider diagnostics are still not persisted. The Case path does
> store model-derived text, however: `POST /api/v1/cases/{id}/grounded-results`
> keeps the server-composed `answer` and its `statements`, whose wording comes from
> the model's validated draft, together with generation metadata (provider, model,
> token usage, duration), warnings, and per-evidence metadata. It does not store
> quotes (section 15).

### The model this phase was validated with

| | |
|---|---|
| Model | `qwen2.5:1.5b` (Ollama) |
| Digest | `65ec06548149` |
| Size on disk | 986.1 MB |
| Pull time | 61 s |
| Host | Windows 11, Docker Desktop, CPU-only, Ollama 0.17.1 |
| Health check | 28-46 ms |
| Cold generation | **27.58 s** (first call; includes model load into memory) |
| Warm generation | **0.18-0.38 s** (31-45 output tokens, temperature 0) |
| Structured generation | **0.61-0.94 s**, validated against the built-in schema |

Chosen because it is small, multilingual with usable Korean, instruction-tuned,
practical on CPU, and capable of schema-constrained JSON. Reasoning-mode models
were avoided: their thinking preamble is expensive on CPU and interacts badly with
constrained decoding.

**This model is a smoke test, not a patent analyst.** A 1.5B model is not fit for
claim analysis, and no measurement here says anything about analysis quality. It
exists to prove the boundary works.

### What real Ollama validation found

Two findings worth recording, both of which changed the code.

**Constrained decoding does not enforce value constraints.** Given a schema with
`confidence: {type: number, minimum: 0.0, maximum: 1.0}`, `qwen2.5:1.5b` returned
`"confidence": 3` - and `5` on a second prompt - in both Korean and English.
Ollama's grammar guarantees a *number in that position*, not a number within
bounds. The post-validation step rejected it with
`llm_structured_output_validation_failed`, which is the designed behaviour and the
clearest possible argument for validating even in `native_json_schema` mode.

The fix is not to relax the bound. The range is now also stated in prose in the
smoke test's system instruction, because words are the only lever that reaches the
model; the bound is still enforced on arrival, and a model that ignores both is
reported rather than corrected. With the instruction in place, all three test
prompts validate (`confidence: 0.95`).

**A schema description is prompt text.** The smoke-test model's class docstring
became the JSON Schema `description` and was sent to the model - several hundred
characters of internal rationale spent from a small model's context window to tell
it something it must not act on. The rationale moved to a comment above the class;
descriptions in that model are now written *for the model* and kept short.

### vLLM validation status

**Contract-tested only. No real vLLM server was run.**

The adapter is covered by tests against `httpx.MockTransport` reproducing the
chat-completions wire format: model listing, plain completion, all three
structured-output modes, usage parsing, finish-reason mapping, authentication
failure, rate limiting, model-not-found, context-length errors, timeouts,
malformed and unexpected response shapes, retry behaviour, and API-key redaction.
The real request is built, serialised, and routed by httpx; only the socket is
replaced.

Actual vLLM runtime validation was not performed: no suitable GPU hardware or
compatible local model assets were already available, and the phase brief
explicitly rules out installing GPU infrastructure to satisfy it. To do it later:

```bash
# on a CUDA host, with a model already present
vllm serve Qwen/Qwen2.5-1.5B-Instruct --port 8000

# then, in .env
LLM_PROVIDER=openai_compatible
LLM_OPENAI_COMPATIBLE_BASE_URL=http://<host>:8000/v1
LLM_OPENAI_COMPATIBLE_MODEL=Qwen/Qwen2.5-1.5B-Instruct
LLM_STRUCTURED_OUTPUT_MODE=native_json_schema

curl -s localhost:8000/api/v1/llm/status | jq
```

### Reproduction commands

```bash
# Default stack: no model server needed, LLM_PROVIDER=fake
docker compose up -d
curl -s localhost:8000/api/v1/llm/status | jq

# Option A (documented default): Ollama on the host
ollama serve
ollama pull qwen2.5:1.5b
LLM_PROVIDER=ollama docker compose up -d api

# Option B: Ollama as an optional Compose service
docker compose --profile llm up -d ollama
docker compose exec ollama ollama pull qwen2.5:1.5b
LLM_PROVIDER=ollama LLM_OLLAMA_BASE_URL=http://ollama:11434 docker compose up -d api

# Diagnostics
open http://localhost:3000/llm

# Backend checks (host Python is unreliable; run in Docker)
docker compose run --rm api pytest
docker compose run --rm api ruff check --no-cache .
docker compose run --rm api ruff format --check --no-cache .
```

### Known limitations of this phase

- Streaming is not implemented, in the contract or in either adapter.
- No tool calling, no function calling, no multimodal input.
- `strict_model` tightens unknown-field policy at the **top level only**. A nested
  model keeps whatever policy it declares.
- Structured-output capability for the OpenAI-compatible adapter is *declared* by
  configuration, not probed. A deployment that declares `native_json_schema`
  against a server that ignores `response_format` gets prompt-quality enforcement
  with a native-quality label - the strict post-validation still catches bad
  output, but the warning that would explain it is absent.
- Only the delta-seconds form of `Retry-After` is honoured.
- No real vLLM validation (above).
- Generation is synchronous and in-request. A slow model holds a worker for the
  duration, bounded by `LLM_MAX_TIMEOUT_SECONDS`.
- No token accounting, quota, or per-caller rate limiting.

---

## 11. Evidence-grounded generation (Phase 4A-2)

Phase 4A-1 built a model boundary that nothing used. This phase connects it to
retrieval and answers questions from stored claim text - under one rule, from
which everything else in the section follows:

> **The model may not name a source. It may only select from sources the server
> named for it.**

### The inversion that makes citations checkable

The obvious design is to ask the model for an answer with citations, then check
the citations. It does not work, because a model asked for a page number will
produce a page number, and a plausible-but-wrong locator is indistinguishable
from a right one until someone opens the document. Post-hoc validation turns
that into "reject some fabrications", which is a filter, not a guarantee.

So the model is never given the raw material for a citation and never given a
field to put one in. It sees a numbered list of claim texts and answers with the
numbers:

```
validated question
  → ClaimSearchService (the real Phase 3A path, no second retriever)
  → request-local evidence catalog: EV-001, EV-002, …
  → bounded prompt containing only what the catalog describes
  → LLMGenerationService.generate_structured(GroundedAnswerDraft)
  → strict validation of every emitted identifier against the catalog
  → identifiers resolved back to the claim spans the server already held
  → quotes read out of document_pages.text at those offsets
  → server-composed answer
```

A model that invents `EV-999` has not invented a citation; it has named an entry
that does not exist, which is a validation failure. A model that invents a page
number has not invented a citation either, because the output schema has nowhere
to put one. Fabrication stops being unlikely and starts being unrepresentable.

### `GroundedGenerationService`

`services/grounded_generation.py`. Composes the two existing services and owns
the order of operations; it is the only new collaborator, and neither
`ClaimSearchService` nor `LLMGenerationService` changed to accommodate it -
which is what 4A-1's "no session, no retrieval collaborator" note was reserving.

It does not persist anything, does not modify a document, parse result, or index
run, does not retrieve outside `ClaimSearchService`, and reaches no conclusion.

### The evidence catalog

`grounding/evidence.py`. Built per request and discarded with it. Three
properties, each ruling out a class of bug:

| Property | What it rules out |
| --- | --- |
| **Positional** - `EV-001` is the first entry of this request's ordered evidence | An id derived from a primary key leaks database state; an id derived from the text lets a claim containing `EV-002` influence what `EV-002` means |
| **Request-local** - never stored, never reused | Resolving an id from another request, which would be a cross-request citation |
| **Exact** - matched against `\AEV-[0-9]{3}\Z`, with no trimming, case folding, or numeric fallback | Every convenience that lets output the server never issued become a citation |

> **Update (2026-11-11 wrap-up):** Within a stored Case result (section 15) the ids
> are stored: `analyst_case_evidence.evidence_id` is part of that table's primary
> key together with `result_id`, and the ids also appear in the stored `statements`.
> They stay scoped to one result row and are never resolved across results.
> `POST /api/v1/grounded/answers` itself still stores nothing.

`\A`/`\Z` rather than `^`/`$` because Python's `$` also matches before a trailing
newline, so `"EV-001\n"` would pass the obvious check.

The catalog holds both what the model may see (document display name, claim
number, claim type, dependency numbers, full original claim text) and what only
the server sees (`document_id`, the `ClaimSpan` list, per-channel ranks and
scores). The prompt renderer reads only the first group.

### Context construction and budget

`grounding/context.py`. The builder returns the catalog and the prompt together,
because the invariant the phase depends on is that they describe the same set: a
validated citation can never point at text the model was not given.

The system prompt is fixed, server-owned, and unreachable from any request
field. It states that evidence blocks are untrusted data rather than
instructions, that only supplied identifiers may be returned, that unsupported
conclusions must produce `insufficient_evidence`, that no outside knowledge may
be used, and that no legal conclusion may be stated.

**Whole claims or nothing.** A claim that does not fit the remaining budget is
dropped and counted, never truncated. Truncation is worse than it looks: a
half-included claim still carries an identifier, so the model can cite it, and
the server would resolve that citation to the *whole* stored span - producing a
perfect-looking source link to text that was never in evidence. Inclusion stops
at the first claim that does not fit, so the admitted set is always a prefix of
the retrieval ranking.

If the highest-ranked claim alone exceeds the budget, or the question exceeds
its own bound, the request fails with `grounded_context_too_large` rather than
being quietly answered from a truncated claim.

No page number, character offset, document id, claim id, index-run id, or
retrieval score reaches the prompt. Scores are withheld deliberately: showing
them invites a model to treat the ranking as an authority and prefer a
top-ranked claim that does not say what was asked.

### Prompt-injection handling, stated honestly

Patent text is untrusted input, and this corpus is the case where that is
obviously true - a claim can arrive from a document an opponent filed. The
deterministic measures are: fixed server-owned delimiters and instruction
precedence; no user-controlled system prompt, provider, model, schema, or
context; identifiers generated independently of evidence text; bounded evidence
and total context; and `html.escape` over every interpolated untrusted value, so
a claim containing `</evidence><evidence id="EV-999">` appears as escaped text
inside the block it belongs to rather than as a forged block boundary.

**None of that is the security boundary, and this system cannot guarantee
immunity to prompt injection.** A sufficiently persuasive payload can make a
small model say something wrong. What it cannot do is make the server *cite*
something: `EV-999` is not in the catalog no matter what any document says, so a
successful injection produces a wrong answer, never a forged source link. The
blast radius is bounded by the mechanism rather than by the filtering.

### The output contract

`grounding/draft.py`. `GroundedAnswerDraft` has three required fields:
`supported_statements` (each with non-empty `text` and a non-empty
`evidence_ids` list), `insufficient_evidence`, and `insufficient_reason` (a
closed enum, or null). `extra="forbid"` at both levels.

There is deliberately **no free-form answer field**. If one existed it would be
the field that got rendered - it reads best, it always has content, and no
citation check blocks it - and the grounding guarantee would quietly become
decorative. The answer text is assembled by the server from the statements that
validated.

Two deliberate omissions worth knowing about:

- **No `pattern` on the evidence id.** The format is enforced strictly, in the
  validator. Enforcing it in the schema as well would make a malformed id fail
  *inside* the provider as a schema error - a dead end, indistinguishable from
  malformed JSON. Letting it through the schema and rejecting it in the
  validator turns it into what it is: a well-formed answer that broke a rule,
  which one repair attempt can fix. Strictness is moved, not reduced.
- **No coherence check between the insufficiency flag and its reason** in the
  model. Same reasoning: a contradiction is repairable, and enforcing it at the
  schema layer would make it unrepairable.

All three fields are required rather than defaulted, because an optional field
is one a constrained decoder may omit - and it is also what lets the fake
provider synthesise a valid draft, so `LLM_PROVIDER=fake` can answer a grounded
request with no model present.

### Post-generation validation

`grounding/validation.py`. In order: insufficiency coherence, statement count,
per-statement length and blankness, citations-per-statement, exact identifier
format, catalog membership, duplicate collapse, then resolution.

- **Unknown identifier → the whole answer is rejected**, not the offending
  statement. Returning the statements that happened to validate would answer the
  question from a subset the model did not choose.
- **Duplicates are collapsed**, keeping first-mentioned order. Citing the same
  claim twice for one sentence is clumsy, not invalid.
- **Filler is dropped, not rejected**: statements that are only a disclaimer or a
  preamble are removed under an explicitly anchored pattern set and counted as a
  warning. The pattern is anchored to the whole string so a real statement that
  merely *begins* with "제공된 증거에 따르면" is kept - deleting a genuine
  statement is a far worse failure than rendering an empty-sounding one.
- The configured ceilings are re-checked here even though the schema declares
  them, because constrained decoding enforces structure, not values. Ollama's
  grammar guarantees an array where an array is declared; it does not enforce
  `maxItems`.

### Repair: one bounded corrective attempt

Default 1, configurable, 0 disables. A repair reuses the *same* catalog and the
same rendered evidence and appends only server-owned corrective text: the rule
that was broken and the list of identifiers that exist. It never echoes the
rejected output - not the statements, not the offending id - because that would
put generated text into a prompt and into whatever surrounds it, and a malformed
id echoed back can survive by being read as an example. Retrieval is not re-run.

Repair applies only to grounding-rule violations. A timeout, an unreachable
server, or a missing model is never repaired; those are the transport layer's
business and are raised before validation runs.

Failure codes distinguish three outcomes an operator needs to tell apart:
`grounded_unknown_evidence_id` (a fabrication, no repair configured),
`grounded_repair_failed` (corrected once and still wrong), and
`grounded_output_invalid` (every other broken rule).

### Insufficient evidence is a 200

Four situations are kept distinct:

| Situation | Result |
| --- | --- |
| Retrieval returned nothing | 200, `insufficient_evidence: true`, **the provider is never contacted** - asking a model to answer from an empty evidence list is asking it to answer from memory |
| Nothing indexed for the active profile | 200, same, plus a warning. Consistent with `POST /search/claims`, which also answers 200 with `searched_index_run_count: 0` |
| The model judged the evidence insufficient | 200, with a fixed server-owned limitation sentence chosen by the reason enum |
| The model's output broke a grounding rule | 502 - invalid provider output, which is *not* insufficient evidence |

No universal score threshold is applied. Dense and lexical scores are on
unrelated scales and RRF's fused score is a rank artefact, so a single cut-off
across all three modes would have no defensible semantics.

### Citation resolution and what it proves

Validated identifiers resolve to their catalog entry's `ClaimSpan` list, and each
span's quote is read out of `document_pages.text` at its own offsets by
`services/source_resolution.py`. The quote is never taken from the model: a model
asked to reproduce text it cited will paraphrase it or normalise its spacing, and
the result is a quote that no longer appears in the document it claims to come
from. Reading the substring makes the quote a *consequence* of the locator rather
than a second, independently fallible assertion about it. A span that does not
resolve raises `grounded_citation_resolution_failed` rather than returning a
blank quote.

Multi-page claims keep one span per page, in order. The canonical coordinate is
unchanged: `(document_id, page_number, start_char, end_char)`, half-open. **No
new citation coordinate system was introduced.**

**What a resolved citation establishes:** the statement points at retrieved
source text, the text is stored by this deployment, and a reader can open the
exact page and character range it came from.

**What it does not establish:** that the cited claim *entails* the statement. No
amount of identifier checking can prove a sentence is a faithful reading of the
text it cites; that is a semantic judgement, and this pipeline makes none. A
grounded answer is a **checkable** answer, not a verified one - the citation is
what lets a reader do the checking, not a substitute for it. This caveat is
attached to every response as a warning and stated in the endpoint's own OpenAPI
description, so it travels with the data rather than living only here.

### API

`POST /api/v1/grounded/answers`. Accepts `query`, optional `document_ids`,
optional `mode`, optional bounded `top_k` - and nothing else. `extra="forbid"` is
the enforcement point rather than tidiness: a body carrying `model`, `provider`,
`system`, `temperature`, `seed`, `output_schema`, `evidence_ids`, `page_number`,
or `context` is rejected with a 422. Silently ignoring those would be worse,
because a client could ship code that appears to pin a model and never did. The
internal dense and lexical candidate counts are server-controlled: those are a
cost decision, not a relevance one.

There is deliberately no companion diagnostics endpoint exposing the prompt, the
raw draft, or the catalog. A second surface revealing what the first one refuses
to reveal would make the refusal decorative.

### Database policy: no migration

**No migration was added, and the schema is unchanged at revision 0004.**

A grounded answer is request-scoped. The question, the prompt, the catalog, the
draft, the statements, the citations, and the provider usage are all constructed
per request and dropped. Persisting them would mean storing confidential
questions and unvalidated model output in a system whose retention policy nobody
has decided yet - and the phase needs none of it: every identifier is positional
within one request, so there is nothing to look up later. An integration test
asserts the live schema contains no table matching `grounded`, `answer`,
`generation`, or `citation`, so adding one becomes a visible decision.

> **Update (2026-11-11 wrap-up):** The text above stays as the Phase 4A-2 decision.
> `POST /api/v1/grounded/answers` is still unpersisted, and
> `GroundedGenerationService` still persists nothing. But a second endpoint wraps
> the same service and does persist. `POST /api/v1/cases/{id}/grounded-results`
> (section 15) stores the question, a snapshot of the request, the server-composed
> answer and statements, retrieval and generation metadata, and per-evidence
> metadata and locators, in `analyst_case_results` and `analyst_case_evidence`
> (revision `0009`). It does not store quotes; they are re-resolved from
> `document_pages` each time a result is read. The integration test described above
> still passes, but only because those tables are named `analyst_case_results` and
> `analyst_case_evidence`: neither name matches its patterns, so its stated purpose,
> making a new table a visible decision, no longer holds. "Unchanged at revision
> 0004" is likewise historical; the head is `0009`.

### Observability and privacy

One structured event per answer, carrying counts, codes, and server-issued
identifiers only: question length and a 12-character SHA-256 prefix, document
filter count, retrieval mode, index-run count, retrieved/included/omitted
evidence counts, provider, model, generation duration, repair attempts,
statement count, cited evidence count, the insufficiency flag and reason, warning
count, and total duration.

Never logged: the question, any claim text, the prompt, the system instructions,
generated statements, catalog contents, quotes, page contents, embeddings, or
credentials. A rejected answer logs its violation code and nothing else - an
invalid answer is still an answer about confidential text. Expected validation
failures log at info without a stack trace.

### Frontend

`/grounded`. Not a chat: no history, no follow-up, no memory. One question
produces one answer, rendered as ordered statements, each with badges linking to
the evidence it was validated against. Cited evidence is listed with its
document, claim number, type, dependencies, per-channel ranks, the
server-resolved quote, and locator links into the existing page viewer, which
highlights the exact stored range. Model text is rendered as plain text in
ordinary elements - never `dangerouslySetInnerHTML`, never a Markdown renderer.

> **Update (2026-11-11 wrap-up):** `/grounded` and `/search` accept a
> `?document=<id>` query parameter that preselects the document scope in the form,
> and the document detail page links to both pages with its own id.

---

## 12. Claim element decomposition and human review (Phase 2C)

Decomposition splits one persisted claim into ordered elements, each with the
exact source spans it came from. It is deterministic and machine-produced: no
model, no embedding, no similarity. Human review is a **separate record** that
points at one decomposition run and never edits it. Neither says anything about
claim scope, infringement, validity, novelty, equivalence, inventive step, or
patentability; the review vocabulary is `accepted` and `needs_correction`, and no
response contract has a field that could hold a legal conclusion.

### Schema (revisions 0005 and 0006)

```
element_decomposition_runs                 claim_elements
────────────────────────────────────       ───────────────────────────────────
id              uuid PK                    id              uuid PK
claim_id → claims.id CASCADE               run_id → runs.id CASCADE
parser_name     varchar(64)                sequence_number integer ≥ 0
parser_version  varchar(32)                text            text, length > 0
element_count / warning_count  ≥ 0         UNIQUE (run_id, sequence_number)
warnings        jsonb, default '[]'
created_at                                 claim_element_spans
UNIQUE (claim_id, parser_name,             element_id → elements.id CASCADE
        parser_version)                    sequence_number ≥ 0, page_number ≥ 1
                                           start_char ≥ 0, end_char > start_char
element_decomposition_reviews              UNIQUE (element_id, sequence_number)
run_id → runs.id CASCADE
status  varchar(32)  CHECK IN ('accepted', 'needs_correction')
id uuid PK, created_at
```

Decisions worth stating:

- **A run is immutable and has no status column.** The service writes the run, its
  elements, and their spans in one commit, and only after the parser has returned.
  A run exists complete or not at all, and there is no `updated_at`.
- **A run is identified by `(claim_id, parser_name, parser_version)`**, enforced by
  a unique constraint. Re-running the same version is idempotent; a future parser
  version creates a second run beside the first without rewriting its provenance.
- **No `document_id` on any of these tables.** The document is reached through the
  claim and its parse result rather than stored as a copy that could disagree.
- **Reviews are append-only and attach to a run, not a claim.** A judgement is
  meaningful only against the exact elements it was made about, so it stays on that
  run id even after a later parser version yields a different run. The table holds
  an id, the run, one of two statuses, and a timestamp: no reviewer identity, no
  comment, no per-element verdict, no correction payload.
- **Everything CASCADEs** down `documents → claim_parse_results → claims → runs →
  elements → spans`, and `runs → reviews`. Reviews are immutable through the API
  but not undeletable: removing a run, claim, parse result, or document in the
  database removes them.

### The parser

`DeterministicElementParser` (`parsing/elements.py`) is named
`deterministic-semicolon-elements`, version `"1"`. It is a pure function over a
`ParsedClaim` and the document's `SourcePage`s. `deps.py` constructs it directly
for each request; unlike the claim parser it is not a protocol and not on
`app.state`.

1. **Provenance check.** It rebuilds the claim text from the claim's spans, joined
   with `PAGE_SPAN_SEPARATOR` (`"\n"`). If that differs from `claims.text` it raises
   `ValueError` and nothing is stored.
2. **Split on the ASCII `;` only.** An element is the whitespace-trimmed payload up
   to and including its `;`; text after the last `;` is a final element if not blank.
3. **Map back to pages** by intersecting each element's range with the claim's span
   chunks.

Warnings are recorded on the run, never silently repaired. `no_structural_delimiter`:
the claim has no `;` and is kept as one element rather than inventing structure.
`empty_segment`: an empty segment between semicolons, or an empty trailing one, was
dropped; a claim with no non-whitespace text yields zero elements and this warning.

### Locator preservation

Every element span is a half-open sub-span of an existing claim span on one page. An
element crossing a page break gets **one span per page**. Its `text` contains the
synthetic `"\n"` that joined the pages, but no span includes it, so each span still
resolves to exact stored characters. Responses add a `SourceLocator` per span; the
`document_id` comes from the request path (decompose) or the claim's parse result
(review).

### Endpoints

| Endpoint | Behaviour |
| --- | --- |
| `POST /documents/{id}/claims/{n}/elements/decompose` | `201` new run; `200` when a run for this parser version exists |
| `POST /element-decomposition-runs/{run_id}/reviews` | Body `{"status": …}`; `201` with the full snapshot |
| `GET /element-decomposition-runs/{run_id}/reviews` | `200` snapshot: elements, spans, review history |

The snapshot lists reviews by `(created_at, id)` and marks none as current. **No
endpoint reads or lists runs by claim**: a run is re-read by id through the reviews
endpoint, or by repeating the decompose request. Decompose works from the document's
newest claim parse result (any parser version), the one the claims endpoints show.

| Code | Status | Meaning |
| --- | --- | --- |
| `document_not_found`, `claim_parse_not_found`, `claim_not_found` | 404 | Decompose: unknown document, no parse result, no such claim number |
| `claim_parse_not_completed` | 409 | The newest parse result is not `completed` (including `no_claims_found`) |
| `element_decomposition_run_not_found` | 404 | Reviews: unknown run id |
| (FastAPI validation) | 422 | Unknown review status or extra field: a `detail` list, not the `error_code` envelope |

The decompose route declares a `422` in the `ApiErrorResponse` shape, but no code
path raises one (by reading). A provenance mismatch raises a plain `ValueError`, not an
`AppError`, so it surfaces as the generic `500` `{"detail": "Internal server error"}`.

### Idempotency and concurrency

Decompose looks up a run for `(claim, parser name, version)` and returns it with
`created=False`; otherwise it inserts and commits once. If two requests race, the
loser's commit fails on the unique constraint, rolls back, and returns the winner's
run with `200` (an `IntegrityError` with no winner is re-raised). Tests cover the
stale-lookup path and a second parser version coexisting with the first.

Review is the opposite on purpose. `add_review` checks the run, inserts one row,
commits, and returns a fresh snapshot. There is no unique constraint and no
idempotency key, so **each POST appends a row**; a double-submit records two
reviews. What keeps the table append-only is the API surface (no PUT, PATCH, or
DELETE on the path) and the service. There is no database trigger and no revoked
privilege. There is no state machine and no "current status": the history is the
list. A test snapshots the machine rows before and after two reviews and after a
second parser version's run is inserted for the same claim; the machine rows do
not change and the reviews stay on the first run.

### Web

Each claim card has a **Decompose & review** button ("Machine decomposition remains
unchanged by review."). It posts to a server action that calls the decompose
endpoint and redirects to `/reviews/{run id}`, or back to the document page with
`?review_error=`.

`/reviews/[runId]` shows the parser name and version, element and review counts, each
element with links to its exact spans in the original document, two buttons,
**Accept decomposition** and **Mark needs correction**, and the review history. The
action redirects back with `?review_saved=<status>` or `?review_error=`. The page does
not show the run's warnings, because the review snapshot has no `warnings` field.

### Known limitations

- Only the ASCII `;` splits: no full-width `；`, no comma, particle, or "포함하는"
  grammar, no preamble/body split, no claim construction.
- No reviewer identity or comment, and a review covers a whole run, not one element.
- Elements are not read by retrieval, grounded generation, comparison, or Cases; no
  module outside the decomposition and review code imports them.
- A later claim-parser version would create new `claims` rows. By reading
  `ClaimParsingService.snapshot` (newest parse result of any version) and the run
  key, decompose would then start fresh runs for those claims while existing runs and
  reviews stay on the old claim ids. Only one claim parser version exists (`0.1.0`),
  so no test exercises this.

---

## 13. Claim comparison (Phase 5A)

Claim comparison ranks the claims of **one reference document** by textual
correspondence to **one stored claim** of a target document. It is retrieval only:
no LLM, no evidence catalog, no citation validator, no described relationship, no
verdict. It persists nothing and adds no table or migration.

This differs from the seam the original extension-points section predicted for
Phase 5A, "a service over the grounded pipeline … reusing the evidence catalog and
the citation validator". `ClaimComparisonService` composes `ClaimParsingService` and
`ClaimSearchService` only. The constraint that prediction named still holds: no
response field can hold "anticipated" or "infringes", and a test asserts that none
of the legal-conclusion keys appear.

### Composition

One request runs these steps in order:

1. Reject a target equal to the reference (`comparison_invalid_request`).
2. Require that both documents exist (`document_not_found`).
3. Read the target's **newest** claim parse result, any parser version: none is
   `claim_parse_not_found`, a status other than `completed` is
   `claim_parse_not_completed`.
4. Find the claim by number (`claim_not_found`).
5. Call `ClaimSearchService.search` with the target claim's stored text verbatim,
   `document_ids=[reference]`, `top_k` (already clamped by the route to
   `search_top_k_max`), and the candidate counts from settings.
6. **Second scope check.** A returned claim from any other document raises
   `internal_error`. Search already restricts by index run; one foreign claim would
   turn a comparison into a provenance leak, so the service checks again.
7. Derive `no_correspondence_reason`: `reference_not_indexed` if search covered zero
   index runs, `no_matches` if it covered some and returned nothing.

Search uses the newest completed index run per document under the active profile, so
a reference indexed under another embedding profile counts as not indexed.

### Endpoint

`POST /api/v1/compare/claims`. The body rejects unknown fields (`extra="forbid"`):
`target_document_id`, `target_claim_number` (≥ 1), `reference_document_id` (must
differ), `mode` (`hybrid` default, `dense`, `lexical`), `top_k` (1 to 50, default 5).
**Callers cannot supply query text or candidate counts**: the query is always the
target claim as stored, so the target side always has source locators.

| Status | When |
| --- | --- |
| `200` | Matches, or `no_correspondence_found: true` with a reason |
| `404` | `document_not_found`, `claim_parse_not_found`, `claim_not_found` |
| `409` | `claim_parse_not_completed`: raised by the service, **not in the route's `responses`** |
| `422` | Same document twice, an extra field, or a bound violated; Pydantic validation runs first |
| `500` | `internal_error` from the step 6 scope check |

The route also declares `400` and `503`. The `400` (`comparison_invalid_request`) is
not reachable over HTTP, because the request schema rejects a same-document request
first; only a direct service test reaches it. For `503`: nothing on this path maps an embedding
failure to an `AppError`, so it would surface as the generic `500` (by reading; no
test covers it; see section 9). Tests check the `422` by status code only.

### Response invariants

The schema enforces these again, so no future caller can serialise a contradiction:
target and reference differ and every match belongs to the reference;
`match_count == len(matches)`; `no_correspondence_found` is true exactly when
`matches` is empty; `no_correspondence_reason` is null with matches and required
without them, with `reference_not_indexed` needing zero searched index runs and
`no_matches` at least one; the target and every match carry at least one
`source_span`, all on their own document. `no_correspondence_found` means retrieval
returned no claim from the reference. It says nothing about novelty or equivalence.

### Locator preservation

Target and matches carry one `SourceLocator` per stored `claim_spans` row in
`sequence_number` order, so a multi-page claim keeps one span per page. An integration
test resolves every span against stored page text, joined with `"\n"`, and expects the
claim text exactly.

### Known limitations

- The target needs a completed parse but no index. The reference needs a completed
  index run for the active profile; without one the answer is `200` with
  `reference_not_indexed`, not an error.
- **Query length.** `/search/claims` caps `query` at 512 characters. Comparison has no
  query field, so a long claim is passed whole. The lexical channel uses at most 32
  whitespace terms (`query_terms`) for the full-text OR and the term-level fallback;
  the whole-query trigram and `LIKE` predicates use the complete normalised text. The
  dense channel passes the full text to the embedding provider; whether a model
  truncates it is not shown here and is unverified.
- One target claim against one reference document: no claim-to-claim matrix, no
  element-level comparison (section 12 elements are unused), no description evidence
  (section 14).

### Web

`/compare?target=<id>` lists up to 100 `completed` documents and fetches claims for
those whose parse is `completed`; it needs at least two. The panel offers a target
document and claim, a reference document (the target is disabled there), a mode, and
**Matches** of 3, 5, 10, or 20 (default 5; other values fall back to 5). Results show
the target card and one card per match with dense, lexical, and fused rank and score,
a source link per span into `/documents/{id}?page&start&end`, and a message per
no-match reason. The page does not check that the reference is indexed.

The entry point is **Compare against another document →** in the document page's
"Analyze this document" panel, shown only when that document's index run is
`completed`. No other page or component links to `/compare`.

---

## 14. Description-evidence derivation and retrieval (D4-01)

Retrieval over the description part of a patent, as a second kind of evidence.
Every hit is `evidence_kind = "description"` and is a span of stored page text: a
page number and a character range into `document_pages.text`, the same
coordinate system as claims. Nothing is summarised.

This is API-only. No page, component or e2e test in `apps/web` calls these
endpoints. The one contact with the web app is each hit's `source_url`, a deep link
into the existing document page, which already reads `page`, `start` and `end`
and highlights that range. Description evidence is **not** an input to grounded
answers (section 11), claim comparison (section 13) or Cases (section 15); those
remain claim-only.

### The segmenter

`korean-patent-description-sections`, version `v1`: a pure function over the
persisted pages. It never re-reads the PDF.

- **A heading is mandatory.** A line is a heading when, after removing whitespace,
  brackets, angle and parenthesis marks, digits, periods, middle dots and hyphens,
  at most 40 characters remain and they equal or start with a known heading.
- **Start:** 발명의설명, 발명의상세한설명, 기술분야, 배경기술, 발명의내용,
  도면의간단한설명, 발명을실시하기위한구체적인내용.
- **Stop:** 특허청구의범위, 청구범위, 청구항. A stop before any start is ignored, so a
  claims block ahead of the description does not end the search. A stop after a
  start ends derivation for the whole document, on every later page.
- **Regions are page-local.** A region closes at each page end and reopens at
  offset 0 on the next, so a segment never spans a page break.
- **Chunking.** At most 700 characters per chunk, cut at the rightmost of a blank
  line, newline, `다. `, `. ` or space, never within a chunk's first 40 characters;
  otherwise a hard cut. Surrounding whitespace is excluded from the span. A chunk
  under 40 characters is dropped.
- **Two `unsupported` outcomes, both with zero segments:**
  `description_heading_not_found`, and
  `description_heading_found_but_no_substantive_text`.

There is deliberately no fallback of "everything that is not a claim". The code's
reason: it would silently turn front matter or an ambiguous structure into
accepted description evidence, so missing structure is an explicit `unsupported`.
A document with no recognised heading is not searchable here.

Matching is by prefix, so a short body line that begins with a heading word reads
as a heading (from the code; untested). The unit tests cover a clean description,
claims before it, a stop after it, and no heading.

### Schema (revision 0007)

```
description_derivation_runs        description_segments
document_id → documents CASCADE    run_id, document_id → CASCADE (both)
status  completed | unsupported    segment_index ≥ 0, section_heading null
segmenter_name / _version          page_number ≥ 1, start_char ≥ 0, end_char > start_char
segment_count ≥ 0, warnings jsonb  text, evidence_kind CHECK = 'description'
UNIQUE (document_id, name, version)  UNIQUE (run_id, segment_index)

description_search_records
segment_id → segments CASCADE, document_id → documents CASCADE
segment_index, profile_key varchar(512), normalized_text
search_vector tsvector, embedding vector(384)
UNIQUE (segment_id, profile_key)
HNSW (embedding, cosine) · GIN (search_vector) · GIN (normalized_text, trigram)
```

Decisions worth stating:

- **No ORM models; raw SQL.** Only `services/description_evidence.py` touches
  these tables, through `text()` statements.
- **No index-run table.** The profile sits on each record as `profile_key`, so
  "indexed for this profile" is a count of records, not a lifecycle row. That is
  why there is no `processing` or `failed` state, unlike section 9.
- **A second `vector(384)` column**, with its own HNSW index. The width is the
  fixed dimension section 9 explains; a wider model needs a migration here too.
- **Everything CASCADEs**, from `documents` to runs, segments and records, so no
  record outlives the text it was built from.

### Locator preservation

A segment's `text` is the slice `page.text[start_char:end_char]`, not a
normalised form. The unit tests assert that identity, and the acceptance test
re-resolves every returned span against `/documents/{id}/pages`. Responses carry
`source_span` and a `source_url` of
`/documents/{id}?page={page}&start={start}&end={end}`. `normalized_text` serves
matching only; it is never a coordinate and is not returned.

### API

Under `/api/v1`.

| Endpoint | Behaviour |
| --- | --- |
| `POST /documents/{id}/descriptions/derive` | `201` new run; `200` existing, including a cached `unsupported`. `404 document_not_found`, `409 document_not_completed` |
| `POST /documents/{id}/descriptions/index` | Derives first if needed. `201` when records were written; `200` when already indexed or `unsupported` (nothing embedded). `500 embedding_dimension_mismatch`; `422 claim_index_failed` on a vector-count mismatch |
| `POST /search/descriptions` | `query` 1–512, `mode`, `document_ids` ≤ 50, `top_k` (10, ≤ 50), candidate counts (30, ≤ 200). `200`, with per-channel ranks and scores |

`claim_index_failed` is the claim-indexing code, reused. The `document_id` path
parameter of the first two routes is a `str` parsed by hand, so a malformed id
raises `ValueError` and returns the generic `500`, not a `422`.

### Retrieval behaviour

A separate implementation in `services/description_evidence.py`, not a
composition of `retrieval/`: it reuses `normalize_search_text`, `query_terms`,
`profile_for` and the embedding provider, but not `dense.py`, `lexical.py`,
`fusion.py` or `source_resolution.py`.

- **Lexical:** the three branches of section 9 (OR of `plainto_tsquery`, `LIKE`,
  `<%` at 0.25), with different weights: **0.55 / 0.30 / 0.15** for token,
  trigram and containment, against 0.45 / 0.30 / 0.25 for claims. The code gives
  no reason for the difference.
- **No term-level fallback.** The bounded fallback claim search gained after v1.0
  (section 9, "Term-level lexical fallback") does not apply here, yet the profile
  reports the same `lexical_strategy` and version as claims, so it cannot tell the
  two behaviours apart.
- **RRF** is its own small implementation with the configured `rrf_k`; ties break
  on `(segment_index, segment_id)`, not claim number.
- **No `searched_index_run_count`.** "Nothing indexed" and "nothing matched" both
  return an empty `results`.

### Idempotency and concurrency

- **Derive** looks for a run on `(document, segmenter, version)` and returns it;
  otherwise it inserts the run and segments in one transaction. There is no
  `IntegrityError` handling, so two simultaneous first derives of one document
  could collide and surface as a `500`. By reading only; untested.
- **Index** derives, then counts records for `(document, profile)`. Equal to the
  segment count: `200`, nothing done. Otherwise it embeds, deletes that
  document's records for the profile and reinserts them in one commit. Embedding
  precedes the delete, so a failed embed keeps the old records. Derive commits
  separately, so a failed index still leaves the segments.

### Known limitations

- **No logging.** The service and routes import no logger, so there is no
  equivalent of section 9 "Query privacy": queries are not logged, but because
  nothing is, including counts and timings.
- **Embedding errors are unmapped.** Only claim indexing turns `EmbeddingError`
  into `embedding_model_unavailable`. Here it reaches the generic `500`, although
  the search route's OpenAPI lists `503`. By reading; no test covers it.
- **Mechanics, not quality.** The acceptance test uses deterministic fake
  embeddings and queries with the first 160 characters of the longest segment,
  then asserts that segment comes back. Its own report says this proves
  mechanics, not model quality. It runs one document, the first in the corpus
  manifest.
- **Not fused with claims.** A resolved span shows where text is, not that it
  answers the query.

---

## 15. Analyst Cases and persisted grounded results (D5-01, D5-02)

A Case is a durable workspace identity: a title and references to documents that
already exist. A Case can also hold grounded results a reader can reopen later,
whose quotes are **always re-read from canonical page text** rather than stored.
This is API-only: nothing in `apps/web/app`, `components`, `lib` or `e2e` refers to
Cases or `grounded-results`. There is no owner column and the routes check no
identity.

### Schema (revisions 0008 and 0009)

```
analyst_cases           id PK, title varchar(200) CHECK length(trim(title)) > 0,
                        created_at, updated_at
analyst_case_documents  PK (case_id, document_id); case_id → analyst_cases CASCADE;
                        document_id → documents CASCADE; associated_at
analyst_case_results    id PK; case_id → analyst_cases CASCADE;
                        request_fingerprint varchar(64); query varchar(512) non-blank;
                        request_snapshot jsonb; result_snapshot jsonb; created_at
                        UNIQUE (case_id, request_fingerprint); INDEX (case_id, created_at, id)
analyst_case_evidence   PK (result_id, evidence_id varchar(16));
                        result_id → analyst_case_results CASCADE;
                        document_id → documents ON DELETE RESTRICT;
                        evidence_snapshot jsonb; locator_snapshot jsonb
```

Decisions worth stating:

- **No ORM models; raw SQL.** Only `services/cases.py` and
  `services/case_grounded_results.py` touch these tables, through `text()`.
- **The title CHECK backs up the request model**, which strips the title and
  rejects a blank one; the database refuses it as well. Titles are not unique.
- **Composite primary keys** on the two association tables, with no surrogate id.
- **`updated_at` is bumped by explicit SQL**, not by an ORM hook:
  `UPDATE analyst_cases SET updated_at = now()` on a new association, a removal,
  and a stored result. Only `analyst_cases` has the column; the other tables are
  never updated.
- **`analyst_case_evidence.document_id` is `ON DELETE RESTRICT`**, the only
  reference in these tables that does not cascade. A document cited by any stored result
  cannot be deleted until that result, or its Case, is gone. No API route deletes
  documents or Cases today, so this is reachable only through direct SQL.

### Modules and API

`AnalystCaseService` (identity and association) and `CaseGroundedResultService`
(scope, fingerprint, persistence, rehydration) are constructed inline in the
routes of `api/v1/cases.py`, not through `deps.py`. The result route wraps the
unchanged `GroundedGenerationService` (section 11) and reuses the private
`_answer_response` mapper from `api/v1/grounded.py`. Under `/api/v1`:

| Operation | Behaviour |
| --- | --- |
| `POST /cases` | `{title}`, stripped, non-blank, at most 200. `201` |
| `GET /cases` | `200`, every Case with its documents, by `created_at`; no pagination |
| `GET /cases/{id}` | `200`; `404` |
| `PUT /cases/{id}/documents/{doc}` | `200 {case, changed}`; `changed` is `false` on a repeat. `404` for a missing Case or document |
| `DELETE /cases/{id}/documents/{doc}` | `204`; `404` for a missing Case or a document not associated |
| `POST /cases/{id}/grounded-results` | Body is `GroundedAnswerRequest`. `201`, **also** when it returns an already stored result. `404` Case; `409` scope; grounded `AppError`s pass through and nothing is stored |
| `GET /cases/{id}/grounded-results` | `200` summaries `{id, case_id, query, created_at}`, oldest first |
| `GET /cases/{id}/grounded-results/{rid}` | `200`; `404` if absent or in another Case; `409` if a locator no longer resolves |

Errors here are FastAPI `HTTPException` bodies carrying `detail` **without**
`error_code`, unlike the rest of the API (section 5); the tests assert on the
`detail` strings. Association needs only that the document row exists, not that
it completed. A Case cannot be renamed or deleted, nor a result deleted.

### Scope rule and fingerprint

`scope_document_ids` fixes what a result may search:

- requested `document_ids` must be a subset of the Case's documents, else `409`;
- an empty list means **all** associated documents, and a Case with none is `409`;
- more than 50 documents (the grounded request limit) is `409`;
- the list is sorted and written back into the request before anything else.

The fingerprint is the SHA-256 of the canonical JSON (sorted keys, no spaces) of
that scoped request, which is its four fields: `query`, `document_ids`, `mode`,
`top_k`. The query is hashed as sent, so whitespace changes make a new result.
With `document_ids` omitted, changing the Case's document set changes the
fingerprint. `persist` then re-checks against a fresh read of the associations
that the request's documents, every evidence document and every locator's
document belong to the Case, so a change during generation is `409`, not a
stored result.

### What is stored, and what is re-derived

**Stored:** the scoped request (and the question again in `query`); the
server-composed `answer`, the model's `statements`, the insufficiency fields,
retrieval and generation metadata and warnings; per evidence item its
`evidence_id`, `document_id`, filename, claim number and type, dependencies,
`crosses_pages`, ranks and scores, and its canonical locators.
**Not stored:** any quote, page text or claim text.

The integration test asserts that no returned quote appears anywhere in the stored
JSON. Statement text is model-written and stored, and may repeat claim wording.

On every read, including the one that builds the response to a new `POST`:

1. each stored locator is validated as a `SourceLocator` and must name the row's
   own `document_id`;
2. its quote is read from `document_pages` by raw SQL, and a missing page or an
   `end_char` beyond the page's `character_count` raises, which the route returns
   as `409`;
3. the quotes are merged back into the evidence, and the whole payload is
   re-validated as `GroundedAnswerResponse`.

The integration test asserts that a reopened result equals the original response.
The check shows a range still fits inside stored text; it does not compare that
text with what it was when the answer was written. No test drives the `409`.

### Relation to section 11's "no persistence" policy

`POST /grounded/answers` is unchanged and stores nothing. The Case path is an
explicit, separate decision to persist: the question, the model-derived
statements and the generation metadata are written to the database, and there is
no retention policy and no way to delete a result. The section 11 test that scans the
live schema for `grounded`, `answer`, `generation` or `citation` still passes
only because these tables are named `analyst_case_*`.

`EV-nnn` ids are now stored: `evidence_id` is half of the evidence primary key and
appears inside `statements`. They stay scoped to one result and are never
resolved across results.

### Idempotency and concurrency

The route looks for a stored result **before** generating. A match returns it,
`201`, without contacting the model. Otherwise it generates, then `persist`
re-checks, looks again, and inserts with `ON CONFLICT (case_id,
request_fingerprint) DO NOTHING`, reopening the winner when the insert lost. By
reading, two simultaneous identical requests both generate, one row is stored and
both callers receive it. No test covers concurrency.

A stored result is a snapshot. The same request later returns the old answer even
if the index, the corpus or the model has changed; there is no regenerate
operation, and only a changed request makes a new result.

### Lifecycle consequences

- **Removing a document does not invalidate stored results.** Reads consult no
  association table, and the evidence rows keep the document. An identical `POST`
  naming a removed document is refused by the scope check before lookup.
- **Locators depend only on page rows.** No parse-result or index-run id is stored,
  and `claim_number` is a plain number, not a reference.

### Known limitations

- No owner, authentication or multi-user model; no pagination; no rename or delete
  of a Case, no delete of a result, no retention policy.
- Claim-only. A Case holds no description evidence (section 14), comparison or
  decomposition result, and a stored citation is checkable, not shown entailed.

---

## 16. Verification architecture

This section describes how evidence is organised, not the outcome of any run; outcomes
live on the pull requests and in `CLAIMTRACE_V1_MASTER.md`. No tier tests infringement,
validity, novelty, equivalence, inventive step or patentability: ClaimTrace determines none
of them.

### Test tiers

The backend suite has one pytest marker, `integration` (`apps/api/pyproject.toml`).

- **Database-free tier.** `pytest -m "not integration"`, or `make test-unit`. It uses stub
  sessions, generated PDFs and fake providers; the ingestion fault-injection, parser and
  upload tests live here.
- **Integration tier.** It needs PostgreSQL with `pg_trgm` and pgvector. The session
  fixture creates a dedicated `<database>_test` database and runs Alembic to head from
  empty. Embeddings are the fake provider. If PostgreSQL is unreachable the fixture calls
  `pytest.skip`, so on a laptop the default suite passes with the whole tier skipped, and
  a skip is not evidence. CI defeats it: General CI and the v1 gates require "N passed" in
  the output and fail on "N skipped".
- **Acceptance directories.** `d3_acceptance` and `d4_acceptance` are in `norecursedirs`,
  so default collection ignores them; their workflows invoke the files explicitly. They
  assert, not skip, when their corpus environment is missing.
- **Web.** No unit tests and no test-runner configuration: ESLint, `tsc --noEmit` and the
  browser scripts below.

On 2026-11-11, on the `f59f4df` tree, the database-free tier ran locally with 798 passed
and 144 deselected. The 144 integration tests were not run locally in the wrap-up (no
Docker daemon, no pgvector); they run in General CI.

### CI workflows

There are 16 workflows in `.github/workflows`. All trigger on `pull_request`, filtered by
path, and all but `progression-retry-ui` also by base branch `main`. Only `v1-02-verify`
also runs on push to `main`; it, `v1-04-verify` and `v1-05-verify` also take
`workflow_dispatch`. None deploys. The one with write access, `v1-07-proof-package`, can
push proof assets to the pull-request branch, and only when none are committed yet. A
change confined to `docs/` or `README.md` triggers no General CI: its path filter omits them.

| Protects | Workflows | What runs |
| --- | --- | --- |
| General CI | `ci.yml` | Compose check, image build, database-free tests, integration tests with the no-skip assertion, Ruff lint and format check; a second job runs `npm ci`, ESLint and `tsc --noEmit` |
| v1 feature gates | `v1-02-verify`, `v1-04-verify`, `v1-05-verify` | Comparison tests (`make verify-v1-02`); element parser, persistence and API tests; review tests. Integration steps are no-skip; each ends with Ruff |
| Failure states, start-up | `v1-06-failure-states`, `v1-06-clean-start` | Five named tests with `--no-deps` (non-PDF, no-text PDF, empty grounded retrieval is 200, comparison `no_matches` and `reference_not_indexed`); the clean-start script |
| Browser end to end | `v1-03-verify`, `v1-05-verify` (browser job), `v1-06-golden-path`, `v1-07-proof-package` | A compose stack on fake embeddings, a seed script, then a Playwright script. The proof workflow captures screenshots and a video into a temporary directory |
| Evaluation | `progression-deterministic-regression`, `v1-07-final-evals` | The enforced gate; and both harnesses with no thresholds (see Evaluations) |
| Retry | `progression-retry-ui`, `progression-retry-real` | The Documents-page retry against a stub API; and against the real API and PostgreSQL |
| Handoff | `progression-controlled-pilot-handoff` | `scripts/verify-controlled-pilot-handoff.sh`, then a grep of its report for the non-claim sentences |
| Real public corpus | `progression-d3-real-corpus`, `progression-d4-description-evidence` | See the real-public subsection |

The D3 and D4 path filters name `scripts/verify-deterministic-regression.sh`, which does not
exist; the gate is the Makefile target, and `apps/api/**` triggers them anyway.

### Scripts and browser checks

The four stack scripts (clean start, golden path, real retry, proof capture) each use their
own Compose project name and host ports and tear down with `down -v --remove-orphans` on
exit, so they can run beside the development stack. Clean start uses ephemeral ports, the
others fixed defaults that environment variables override, and the handoff verifier runs
three of them with distinct names and ports. They check migration from empty volumes to
head, a seeded whole-product flow on fake providers, and a real-stack retry.

The runners in `apps/web/e2e/*.mjs` are plain Node scripts with `node:assert` and
Playwright, which is not in `package.json`: workflows and scripts install 1.55.0 on the
spot with `npm install --no-save`. `progression-retry-ui` runs Next in development mode
against a stub HTTP API inside the script. The stub's first retry answers 503
`storage_failure` (the real endpoint answers 500 for that code); the script checks that the
message appears and the button stays, then that a second retry succeeds and the button
goes. It proves what the page does with an error envelope, not API behaviour.
`progression-retry-real` uses the real API, then a Python verifier checks the same row,
completed with two pages, an original that still hashes to its digest, and one document.

### Evaluations

Two harnesses in `apps/api/evals` drive the real HTTP pipeline through `TestClient` on
databases they create. `evals.run` queries `POST /search/claims` in dense, lexical and
hybrid modes over 26 synthetic claims. `evals.grounded_run` asks `POST /grounded/answers`
over 23 synthetic claims and re-reads every returned citation from `/pages`; its
deterministic tier swaps the model for an in-process oracle, so it measures the pipeline,
and its `ollama` tier uses the configured local model. Neither harness calls the
comparison, decomposition, review, description or Case endpoints.

`make verify-deterministic-regression` is the only enforced evaluation. It runs both
harnesses with the fake embedding provider, then asserts exact values: dense, lexical and
hybrid Recall@5 and MRR@10; every grounded rate at 1.0 with no forbidden citation; every
case successful and every guardrail refused; and `g01-single-storage` successful with
`collector#1` cited. The baseline is fake-provider, so it guards plumbing and ranking logic
against regression, not quality. It rewrites the result files in the working tree; CI uploads
them as artifacts. `v1-07-final-evals` has no thresholds and succeeds if both harnesses run;
its retrieval run uses the `.env.example` provider, `sentence-transformers`.

The committed `apps/api/evals/results/results.json` and
`results/grounded/results-deterministic.json` carry `generated_at` 2026-07-26 with the
`intfloat/multilingual-e5-small` profile, and `results-ollama.json` the same date.
`retrieval/lexical.py` changed on 2026-09-03 (P11). The files record that earlier run and
are not current measurements; the committed grounded file still records
`g01-single-storage` as not succeeding, which the gate now requires. Current real-embedding
numbers were not re-measured.

### Real-public corpus tier (D3, D4)

`docs/real-public-corpus/manifest.json` lists two public Korean patent PDFs, each with a
pinned SHA-256 and the status `not_asserted_do_not_commit_pdf`. The workflow downloads them
at run time and nothing commits them; `.gitignore` excludes `*.pdf`.
`scripts/verify-d3-real-corpus-inputs.sh` fails closed unless each file exists, begins with
`%PDF-`, matches its pinned hash, passes `pdftotext`, contains its publication display
number, and yields at least 500 non-space characters, 50 Hangul characters and a claim
marker. The acceptance tests re-check the hash, require `text_native`, and drive the product
path through the API. D4 does this for one document: description derivation, indexing, and a
search whose query is a prefix of its own longest segment, with every result resolved
against page text. Both run on fake embeddings, so they prove mechanics and provenance, not
retrieval quality or correctness.

### What this structure does not establish

- **Model quality.** No tier measures an embedding model or an LLM. Integration, browser and
  real-public tiers use fake providers; the gate uses an oracle; the one CI run with the real
  embedding provider has no thresholds and is not committed, and real-embedding numbers
  were not re-measured since v1.0.
- **Description search over HTTP, outside the D4 acceptance.** Only that test calls the
  description endpoints; the general suite tests the pure segmenter on synthetic text.
- **Cases beyond one file.** `test_analyst_cases_integration.py` (General CI, integration
  tier) is the only coverage; no browser script or workflow touches Cases.
- **Concurrency and real database faults.** Retry serialisation is untested, and the
  terminalization paths use stub sessions. Citation resolvability is not semantic
  entailment.

---

## 17. Extension points for later phases

Each item below names the seam, not the implementation. The intent is that adding a
capability means adding a module behind an existing boundary, not reshaping the
application.

> **Update (2026-11-11 wrap-up):** This section was rewritten at the wrap-up. Each
> heading says whether its seam is built, partly built, or not built, and where an
> earlier prediction proved wrong the correction is recorded in place.

### Document and claim parsing (Phases 2A and 2B - built; header and abstract not built)

- The `DocumentParser` protocol and the PyMuPDF implementation exist (section 7);
  the `ClaimParser` protocol and the Korean rule-based implementation exist
  (section 8). Implementations register against a protocol; no route branches on
  file format or language.
- A second language's claim conventions would be another `ClaimParser`, wired where
  `main.py` builds the application state and handed out by `deps.py`. Nothing above
  the boundary changes.
- The description is now segmented for retrieval, as a derived layer over stored
  page text (section 14). That is not a structural parse of the description. The
  bibliographic header and the abstract remain unparsed; when they arrive they attach
  the same way claims did: new tables, new revision, spans on pages, page tables
  untouched.
- OCR is not built. What was added instead is a fail-closed rule: a PDF with some
  text-bearing and some text-empty pages is rejected rather than ingested partially
  (section 7). OCR would arrive as another `DocumentParser` implementation, and it
  needs the asynchronous path that the `processing` state anticipates; there is no
  background worker yet (section 18). It is a deferred candidate for a later
  destination, not a selected one.

### Embedding providers and retrieval (Phase 3A - built; description retrieval built, element-level not built)

- The `EmbeddingProvider` protocol and both implementations exist (section 9), as
  do the dense, lexical, and fusion retrievers. Swapping the model is a settings
  change plus a re-index; swapping the *width* is a migration.
- Provider identity, model version, dimension, and normalisation policy are
  recorded on every index run and combined into a `profile_key`, so incompatible
  indexes can coexist without ever being ranked against each other.
- Description retrieval exists (section 14). Element-level retrieval is not built.

> **Update (2026-11-11 wrap-up):** This section originally predicted that
> description-level and element-level retrieval "would attach the same way claims
> did: new tables, new revision, spans on pages, existing tables untouched", and
> that "nothing in the retrieval layer assumes a claim is the only indexable unit
> beyond the table it reads from". That proved wrong. `retrieval/` is claim-shaped:
> `Candidate` carries `claim_id` and `claim_number`, and the dense and lexical
> retrievers read `claim_search_records` directly. Description retrieval was built by
> duplicating that code: `DescriptionEvidenceService` runs its own dense, lexical,
> and rank-fusion SQL over `description_search_records` (section 14). The profile
> is stored on each description record, because there is no description index-run
> table.

### Reranking (Phase 3B - not built)

- Seam: an optional `Reranker` - `query + candidates → reordered candidates`.
- Absence of a reranker is a valid configuration; the pipeline must produce results
  without one. That is the only configuration that exists: no reranker type or
  reranking code is present in `src/`.
- `docs/ROADMAP.md` groups description retrieval and reranking in Phase 3B. The first
  is built (section 14); the second is not. An earlier version of this document
  labelled the seam "3B-5".

### LLM providers (Phase 4A-1 - built)

- Built as described in section 10: `LLMProvider` covers plain and structured
  generation, provider selection is an environment variable, and no vendor SDK is
  committed.
- Local, self-hosted inference is the target; the protocol exists so the choice of
  runtime is a deployment decision rather than a code dependency.

### Evidence-grounded generation (Phase 4A-2 - built, claim-only)

- Built as predicted: `GroundedGenerationService` composes `ClaimSearchService`
  and `LLMGenerationService`, and neither changed. See section 11 above for the
  design and section 18 for what it does not do.
- Its evidence is claim text only. Description segments (section 14) and
  decomposition elements (section 12) are not given to it. A Case result
  (section 15) stores the output of the same service; `POST /grounded/answers` still
  stores nothing.

### Claim comparison (Phase 5A - built, retrieval-only)

- Built as `ClaimComparisonService` (section 13). It composes `ClaimParsingService`
  and `ClaimSearchService`: one stored target claim is the retrieval query,
  retrieval is restricted to one reference document, and the result is that
  document's ranked claims with their source locators.
- There is no LLM call, no evidence catalog, no citation validator, and no
  "described relationship". One target claim is compared against one reference
  document, not two documents mapped claim to claim.
- The constraint that shaped the design is kept: there is no output field that can
  hold a verdict. A test asserts that the response carries no `infringement`,
  `validity`, `novelty`, `equivalence`, or `patentability` key.

> **Update (2026-11-11 wrap-up):** The seam as first written read: "a service over
> the grounded pipeline that takes *two* selected documents and maps claim to claim,
> reusing the evidence catalog and the citation validator unchanged", with the
> constraint that "a mapping is a pair of citations plus a described relationship,
> never a verdict. The moment an output field can hold 'anticipated' or 'infringes',
> the system is making a legal conclusion, and there is no such field." What was built
> is the narrower service above. A comparison built over the grounded pipeline is not
> built.

### Claim analysis (Phase 5 - decomposition and review built; per-element evidence not built)

- Deterministic decomposition and append-only human review exist (section 12).
  `DeterministicElementParser` splits one persisted claim into ordered elements, and
  each element span is a sub-span of the claim's own spans, so every element keeps a
  stored source locator.
- Not built: attaching retrieved evidence per element. Nothing in retrieval,
  grounding, comparison, or Cases reads elements.
- Constraint that shapes the design: every produced statement must be traceable to
  a stored source locator. Output without evidence is a bug, not a degraded mode.

### Evaluation (Phase 6 - built; the CI gate is deterministic)

- The harness exists in `apps/api/evals` and is described in section 16: a retrieval
  evaluation and a grounded-answer evaluation. It runs outside the request path and
  reads the same provider protocols.
- A deterministic regression gate runs in CI: `make verify-deterministic-regression`,
  from the workflow `progression-deterministic-regression.yml`, runs both evaluations
  with the fake embedding provider and an in-process oracle instead of a model, then
  asserts pinned values. It guards the plumbing, not retrieval or answer quality.
- "Never requires a network model provider in CI" means an LLM provider. The
  `v1-07-final-evals.yml` workflow runs `python -m evals.run` with the
  `.env.example` default `EMBEDDING_PROVIDER=sentence-transformers`, so that job
  loads the real embedding model, which by reading downloads its weights on the
  runner. It sets no metric thresholds; it uploads the results.

### Persistent workspaces (Analyst Cases - built, deliberately small)

- Seam: a Case is a durable identity that references existing documents and stores
  grounded results whose quotes are re-read from canonical page text (section 15).
  Source text stays in `document_pages`.
- What a Case does not yet hold: an owner or any access control; description
  evidence, comparison results, or decomposition results (the only Case tables are
  `analyst_cases`, `analyst_case_documents`, `analyst_case_results`, and
  `analyst_case_evidence`); a way to rename or delete a Case or a result; or
  pagination of Cases or of results. It has no web UI; it is reachable only through
  the API.

---

## 18. Known architectural gaps

Recorded as of the 2026-11-11 wrap-up, listed so they are not mistaken for
oversights. Most are deliberate scope limits; a few, such as the unmapped query-time
embedding failure, are known defects that remain unfixed.

Not built, stated plainly:

- **No reranker.** Hybrid retrieval ranks claims and description segments; nothing
  reorders the fused list.
- **No OCR.** Image-only and mixed PDFs are rejected, not read; a scan that already
  carries an embedded text layer is ingested as text (section 7).
- **No background worker.** Everything runs in the request.
- **No web UI for Cases or for description search.** Both are API-only. A description
  hit carries a `source_url` that opens the existing document page at the exact
  range.
- **No description evidence in grounded answers.** Grounded generation is
  claim-only.
- **No ORM models for the `0007` to `0009` tables.** Their services use raw SQL, and
  they sit outside the metadata that Alembic autogenerate reads (section 6).

The remaining gaps:

- No authentication, authorisation, or multi-tenancy; no rate limiting. Cases have no
  owner column, no pagination, and no rename or delete. Review rows carry no
  reviewer identity or comment.
- No request-ID propagation or tracing. The only middleware is CORS.
- Ingestion, retry, claim parsing, claim indexing, element decomposition,
  description derivation and indexing, and Case result generation are all
  synchronous in the request. The first index request after a restart still holds a
  connection open for the model load. The description service has no logging and
  no `processing` or `failed` status lifecycle.
- No virus scanning of uploads.
- No document, Case, or result delete endpoint. The one DELETE route removes a
  Case-document association. Rows can be removed in SQL, and most derived tables
  cascade from `documents`, but a document cited by a stored Case result cannot be
  deleted (sections 9 and 15). The stored original is not garbage-collected by the
  application.
- Claim parsing is Korean-only apart from a minimal English heading fallback.
  Lexical retrieval has no Korean morphological analysis; the term-level fallback is
  trigram matching, not morphology (section 9). Element decomposition splits only on
  the ASCII `;`.
- One embedding width. Two tables are migrated at it, so a model of a different
  dimension needs a migration that touches both (section 9). A failure to embed a
  query is also unmapped and, by reading, would surface as a generic 500; no test
  covers it (section 9).
- Grounded answering has no reranking: the claims that reach the model are the ones
  hybrid retrieval ranked, and a claim ranked just outside the evidence budget is
  simply absent (section 11). The g01 case in the evaluation was the recorded
  example. The deterministic gate now pins g01 to succeed: the `Makefile` target
  asserts that `g01-single-storage` succeeds with `collector#1` cited. The committed
  result files were generated on 2026-07-26, before the term-level lexical change,
  and still show g01 failing. Whether g01 passes with the real embedding model has not
  been re-measured.
- A grounded answer still cites whole claims. Decomposition exists (section 12), but
  grounding does not use elements, so an answer about one limitation points at the
  entire claim it sits in.
- Prompt injection is bounded, not prevented (section 11).
- No streaming anywhere, and generation is synchronous and in-request.
- No production web image: the container runs `next dev`. Sixteen workflows in
  `.github/workflows` verify the repository; none deploys anything. The evaluation
  gate they include is the deterministic fake-provider tier (section 16), which
  guards plumbing rather than quality.
- The whole upload is held in memory while hashing and parsing, and a retry reads
  the whole stored original back. Bounded by `UPLOAD_MAX_BYTES`, so it is a known
  ceiling rather than an open-ended one.
