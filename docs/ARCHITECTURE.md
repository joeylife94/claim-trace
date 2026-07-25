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
│   └── logging.py       stdout logging, text or JSON
├── api/
│   ├── deps.py          FastAPI dependencies (engine, session, readiness probe)
│   ├── health.py        unversioned operational probes
│   └── v1/
│       ├── router.py    aggregates every v1 router
│       └── system.py    GET /api/v1/system/info
├── db/
│   ├── base.py          DeclarativeBase, Alembic's target metadata
│   ├── session.py       async engine + session factory
│   ├── models.py        ORM models (app_metadata only)
│   └── health.py        SELECT 1 probe
└── schemas/             Pydantic response models
```

The rule that keeps this layout honest: **routes depend on dependencies, never on
module-level globals.** Every external resource (engine, session, readiness result)
is injected, which is why the test suite can isolate PostgreSQL without a socket.

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

### Error handling

A catch-all handler logs the traceback server-side and returns
`{"detail": "Internal server error"}`. Stack traces, SQL, and DSNs are never
serialised into a response.

---

## 6. Database and migration strategy

- PostgreSQL 17 with pgvector (`pgvector/pgvector:pg17`).
- Alembic owns the schema. The application never calls `create_all`, so the running
  schema is always reproducible from `alembic/versions/`.
- The baseline revision `0001` enables the `vector` extension and creates
  `app_metadata` (`key`, `value`, `created_at`, `updated_at`). It exists to prove
  the pipeline works; no domain table is defined yet.
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

## 7. Extension points for later phases

Each item below names the seam, not the implementation. The intent is that adding a
capability means adding a module behind an existing boundary, not reshaping the
application.

### Document parsing (Phase 2)

- Seam: a new `ingestion` package with a `DocumentParser` protocol -
  `bytes + media type → structured document` (sections, claims, figures).
- Format-specific parsers register against that protocol; the API layer never
  branches on file format.
- Parsed output is persisted through new Alembic revisions; parsing never writes
  schema of its own.

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

## 8. Known architectural gaps

These are deliberate for Phase 1 and listed so they are not mistaken for
oversights: no authentication or authorisation, no multi-tenancy, no rate limiting,
no request-ID propagation or tracing, no background worker, no production web
image (the container runs `next dev`), and no CI pipeline.
