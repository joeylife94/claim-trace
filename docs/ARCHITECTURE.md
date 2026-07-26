# ClaimTrace Architecture

Status: **Phase 1 - foundation.** This document describes what exists today and the
boundaries where later phases will attach. It intentionally does not specify the
internals of parsing, embedding, retrieval, reranking, or generation.

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
│   └── ingestion.py     the ingestion use case: validate → store → parse → persist
├── parsing/
│   ├── base.py          DocumentParser protocol, ParsedDocument/ParsedPage
│   └── pymupdf_parser.py PyMuPDF implementation for digital PDFs
├── storage/
│   ├── base.py          FileStorage protocol, storage-key validation
│   └── local.py         local filesystem implementation
├── db/
│   ├── base.py          DeclarativeBase, Alembic's target metadata
│   ├── session.py       async engine + session factory
│   ├── models.py        ORM models (app_metadata, documents, document_pages)
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
- Revision `0002` adds the two ingestion tables described in section 7.
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

## 9. Extension points for later phases

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

### Embedding providers (Phase 3)

- Seam: an `EmbeddingProvider` protocol - `list[str] → list[vector]` plus a
  declared dimension and model identifier.
- The dimension belongs to the stored index, so the provider identity and
  dimension are recorded alongside every embedding; changing provider is a
  migration plus a re-index, never an in-place mutation.
- pgvector is already enabled, so no extension-level migration is needed later.

### Retrieval (Phase 3)

- Seam: a `Retriever` protocol - `query + filters → ranked candidates with source
  locations`.
- Lexical, vector, and hybrid retrievers implement the same protocol; the
  composition strategy is configuration, not control flow inside route handlers.
- Every candidate must carry enough locator data (document, section, offsets) to
  support citation, since evidence grounding is the product's premise.

### Reranking (Phase 3-5)

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

## 10. Known architectural gaps

Deliberate as of Phase 2B, listed so they are not mistaken for oversights:

- No authentication, authorisation, or multi-tenancy; no rate limiting.
- No request-ID propagation or tracing.
- No background worker. Ingestion is synchronous, which is fine until OCR.
- No virus scanning of uploads.
- No delete endpoint. Rows can be removed in SQL (pages, parse results, claims,
  spans, and edges all cascade), but the stored original is not garbage-collected
  by the application.
- Claim parsing is Korean-only apart from a minimal English heading fallback.
- Claim parsing is synchronous, like ingestion.
- No production web image (the container runs `next dev`); no CI pipeline.
- The whole upload is held in memory while hashing and parsing. Bounded by
  `UPLOAD_MAX_BYTES`, so it is a known ceiling rather than an open-ended one.
