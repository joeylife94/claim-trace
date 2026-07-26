# ClaimTrace Architecture

Status: **Phase 3A - claim indexing and hybrid retrieval.** This document
describes what exists today and the boundaries where later phases will attach. It
intentionally does not specify the internals of reranking or generation.

---

## 1. Component architecture

```
                    ┌──────────────────────────────┐
   browser ────────▶│ web (Next.js, App Router)    │
                    │ apps/web                     │
                    │ - landing page               │
                    │ - live system status panel   │
                    └───────────────┬──────────────┘
                                    │ HTTP (JSON), CORS-controlled
                                    ▼
                    ┌──────────────────────────────┐
                    │ api (FastAPI)                │
                    │ apps/api                     │
                    │ - /health   liveness         │
                    │ - /ready    readiness        │
                    │ - /api/v1/* versioned API    │
                    └───────────────┬──────────────┘
                                    │ SQLAlchemy 2.x async + psycopg 3
                                    ▼
                    ┌──────────────────────────────┐
                    │ postgres 17 + pgvector       │
                    │ - app_metadata               │
                    │ - vector extension enabled   │
                    └──────────────────────────────┘
```

All three services run as containers described by `docker-compose.yml`. There is no
message broker, cache, or object store yet; none is needed by the current scope.

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
│       └── documents.py document upload, listing, detail, page text
├── services/
│   ├── ingestion.py     the ingestion use case: validate → store → parse → persist
│   ├── claim_parsing.py the claim structural parsing use case
│   ├── claim_indexing.py the indexing use case: embed → persist search records
│   └── claim_search.py  the search use case: profile → retrieve → fuse → hydrate
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
│   └── pymupdf_parser.py PyMuPDF implementation for digital PDFs
├── storage/
│   ├── base.py          FileStorage protocol, storage-key validation
│   └── local.py         local filesystem implementation
├── db/
│   ├── base.py          DeclarativeBase, Alembic's target metadata
│   ├── session.py       async engine + session factory
│   ├── models.py        ORM models (documents, pages, claims, index runs, search records)
│   └── health.py        SELECT 1 probe
└── schemas/             Pydantic request/response models, including locators.py
```

Two rules keep this layout honest:

1. **Routes depend on dependencies, never on module-level globals.** Every external
   resource (engine, session, storage, parser, service) is injected, which is why
   the test suite can isolate PostgreSQL without a socket.
2. **Dependencies point inward.** `parsing/` and `storage/` know nothing about
   FastAPI, SQLAlchemy, or each other; `services/` composes them; `api/` only
   translates HTTP. A different PDF engine or a different storage backend is a new
   module behind an existing protocol, not a refactor.

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
         6. parse       PyMuPDFDocumentParser.parse(bytes) → ordered pages
         7. persist     INSERT every page + UPDATE status=completed  → ONE commit
              ↓
         201 Created + DocumentResponse
```

Failure branches:

| When | Result |
| --- | --- |
| Validation (steps 1) | 4xx, nothing stored, no record |
| Parse or no-text (6) | Document marked `failed` with an error code, 422, and the record is returned inside the error envelope |
| Page write fails (7) | Rollback; no pages, status stays `processing`; 500 |
| Concurrent identical upload | Unique digest violation is caught and resolved to the winner's record, 200 |

Step 7 is deliberately a single commit: a partially written page set must never be
visible as a `completed` document, because a citation into a half-ingested document
would be silently wrong.

Steps 5's two commits are what make failures traceable. The `uploaded` row exists
before parsing begins, so a crash mid-parse leaves a record pointing at stored bytes
rather than an orphaned file nobody knows about.

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

---

## 4. Service responsibilities

| Service | Owns | Does not own |
| --- | --- | --- |
| `web` | Presentation, server-side status fetching | Business rules, database access, secrets |
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
| `MIN_EXTRACTED_CHARACTERS` | Below this total, a PDF counts as having no text layer. |

### Error handling

A catch-all handler logs the traceback server-side and returns
`{"detail": "Internal server error"}`. Stack traces, SQL, and DSNs are never
serialised into a response.

Ingestion failures are different: they are expected outcomes with a stable
`error_code` from `core/errors.py`, which is both the API contract and the value
persisted on failed documents. Clients branch on the code, never on the message.

| Code | Status | Meaning |
| --- | --- | --- |
| `unsupported_file_type` | 415 | Extension, declared type, or magic bytes are not a PDF |
| `file_too_large` | 413 | Exceeds `UPLOAD_MAX_BYTES` |
| `empty_file` | 400 | Zero bytes |
| `malformed_pdf` | 422 | Unreadable, or repaired into a zero-page document |
| `encrypted_pdf` | 422 | Password protected |
| `no_extractable_text` | 422 | Below `MIN_EXTRACTED_CHARACTERS`; scanned or image-only |
| `document_not_found` | 404 | Unknown document id |

---

## 6. Database and migration strategy

- PostgreSQL 17 with pgvector (`pgvector/pgvector:pg17`).
- Alembic owns the schema. The application never calls `create_all`, so the running
  schema is always reproducible from `alembic/versions/`.
- The baseline revision `0001` enables the `vector` extension and creates
  `app_metadata` (`key`, `value`, `created_at`, `updated_at`). It exists to prove
  the pipeline works; no domain table is defined yet.
- Revision `0002` adds the two ingestion tables described in section 7,
  revision `0003` the four claim-parsing tables in section 8, and revision
  `0004` the two retrieval tables in section 9. `0004` also enables `pg_trgm`.
- `infra/postgres/init/10-extensions.sql` also creates the extension at initdb
  time. That covers on-premise installations where the migration role is not a
  superuser; both paths are idempotent.
- Migrations run explicitly (`make migrate`), not on container start, so a rolling
  restart can never trigger a surprise schema change.
- Timestamps are `TIMESTAMPTZ` with `server_default now()`; `updated_at` is
  maintained by SQLAlchemy's `onupdate`.
- The application engine is async (psycopg 3); Alembic uses a synchronous engine
  against the same URL.

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

### Lifecycle

`uploaded → processing → completed | failed`. All four states are used: `uploaded`
is committed as soon as the bytes are stored, so a crash during parsing leaves a
traceable record rather than an unreferenced file.

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

No OCR is attempted, and none is silently substituted. An empty result is reported as
a failure rather than ingested as a document with no text, because a document that
looks ingested but has nothing to cite is worse than a clear rejection.

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

---

## 9. Claim indexing and hybrid retrieval (Phase 3A)

Retrieval only. No generation, no summarisation, no reranking, and no legal
reasoning: a search returns claims that already exist in the corpus, each
carrying the page coordinates it came from.

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

## 10. Extension points for later phases

Each item below names the seam, not the implementation. The intent is that adding a
capability means adding a module behind an existing boundary, not reshaping the
application.

### Document and claim parsing (Phases 2A and 2B - built)

- The `DocumentParser` protocol and the PyMuPDF implementation exist (section 7);
  the `ClaimParser` protocol and the Korean rule-based implementation exist
  (section 8). Implementations register against a protocol; no route branches on
  file format or language.
- A second language's claim conventions would be another `ClaimParser`, selected
  in `deps.py`. Nothing above the boundary changes.
- Bibliographic header, abstract, and description sections remain unparsed.
  When they arrive they attach the same way claims did: new tables, new revision,
  spans on pages, page tables untouched.
- OCR would arrive as another `DocumentParser` implementation. It needs the
  asynchronous path that the `processing` state already anticipates.

### Embedding providers and retrieval (Phase 3A - built)

- The `EmbeddingProvider` protocol and both implementations exist (section 9), as
  do the dense, lexical, and fusion retrievers. Swapping the model is a settings
  change plus a re-index; swapping the *width* is a migration.
- Provider identity, model version, dimension, and normalisation policy are
  recorded on every index run and combined into a `profile_key`, so incompatible
  indexes can coexist without ever being ranked against each other.
- Description-level and element-level retrieval would attach the same way claims
  did: new tables, new revision, spans on pages, existing tables untouched.
  Nothing in the retrieval layer assumes a claim is the only indexable unit
  beyond the table it reads from.

### Reranking (Phase 3B-5)

- Seam: an optional `Reranker` - `query + candidates → reordered candidates`.
- Absence of a reranker is a valid configuration; the pipeline must produce results
  without one.

### LLM providers (Phase 4)

- Seam: an `LLMProvider` protocol covering completion and structured output, with
  provider selection and endpoint driven by environment variables.
- Local, self-hosted inference is the target; the protocol exists so the choice of
  runtime is a deployment decision rather than a code dependency.
- No prompt content, model, or vendor SDK is committed in this phase.

### Claim analysis (Phase 5)

- Seam: a service layer over retrieval that decomposes claims into elements and
  attaches retrieved evidence per element.
- Constraint that shapes the design: every produced statement must be traceable to
  a stored source locator. Output without evidence is a bug, not a degraded mode.

### Evaluation (Phase 6)

- Seam: an offline harness that consumes fixed datasets and reports retrieval and
  grounding metrics.
- Runs outside the request path, reads the same provider protocols, and never
  requires a network model provider in CI.

---

## 11. Known architectural gaps

Deliberate as of Phase 3A, listed so they are not mistaken for oversights:

- No authentication, authorisation, or multi-tenancy; no rate limiting.
- No request-ID propagation or tracing.
- No background worker. Ingestion, claim parsing, and claim indexing are all
  synchronous, which is fine until OCR - and already means the first index
  request after a restart holds a connection open for the model load.
- No virus scanning of uploads.
- No delete endpoint. Rows can be removed in SQL (pages, parse results, claims,
  spans, edges, index runs, and search records all cascade), but the stored
  original is not garbage-collected by the application.
- Claim parsing is Korean-only apart from a minimal English heading fallback,
  and lexical retrieval has no Korean morphological analysis (section 9).
- One embedding width. A model of a different dimension needs a migration.
- No reranking, and no evaluation gate in CI.
- No production web image (the container runs `next dev`); no CI pipeline.
- The whole upload is held in memory while hashing and parsing. Bounded by
  `UPLOAD_MAX_BYTES`, so it is a known ceiling rather than an open-ended one.
