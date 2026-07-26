# ClaimTrace Roadmap

Six phases, each ending in something runnable and verifiable. Nothing from a later
phase is implemented early: the point of the sequence is that every phase can be
demonstrated on its own.

Current state: **Phase 1 complete.**

---

## Phase 1 - Foundation (complete)

**Goal:** a monorepo that a reviewer can start with two commands and understand in
one reading.

Delivered:

- FastAPI service with `/health`, `/ready`, and `/api/v1/system/info`.
- Configuration through `pydantic-settings`; no hardcoded credentials.
- PostgreSQL 17 + pgvector, Alembic baseline enabling `vector` and creating
  `app_metadata`.
- Next.js (App Router, TypeScript) landing page reading live API status.
- `docker compose` environment with health checks, dependency ordering, a
  persistent volume, and non-root containers.
- pytest suite that needs no database, no network, and no model provider.
- `Makefile`, `README.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`.

Exit criteria: `docker compose up --build` yields a green status panel; `make test`,
`make lint`, and `make web-lint` pass.

---

## Phase 2 - Patent document ingestion and structural parsing

**Goal:** turn a patent document into a stored, structured, citable representation.

- Upload endpoint under `/api/v1/documents` with size and type limits.
- `DocumentParser` protocol; first implementation for text-based patent documents.
- Structural extraction: bibliographic header, abstract, description sections,
  claim set with numbering and dependency relationships.
- Schema for documents, sections, and claims, with stable source locators
  (page/section/character offsets) so every later answer can cite a location.
- Ingestion status tracking, so a failed parse is observable rather than silent.
- Tests built on small synthetic fixtures committed to the repository.

Exit criteria: a document can be uploaded, parsed, persisted, and its claim
structure retrieved through the API.

Explicit non-goals: OCR of scanned images, multi-language parsing, drawing analysis.

---

## Phase 3 - Indexing and hybrid retrieval

**Goal:** retrieve evidence passages with citations, and be able to say why a
passage was retrieved.

- Chunking strategy aware of patent structure (claims and description segments are
  not chunked identically).
- `EmbeddingProvider` protocol; local embedding model as the first implementation.
- pgvector index for dense search plus PostgreSQL full-text search for lexical
  recall of exact claim terminology.
- Hybrid fusion behind a single `Retriever` protocol, with scores exposed for
  debugging.
- Optional `Reranker` seam; the pipeline must work with it absent.
- Re-index path: embeddings are keyed by provider and dimension, so switching
  models is a re-index rather than an in-place edit.

Exit criteria: a query returns ranked passages, each carrying a resolvable source
locator; retrieval quality is measurable on a fixture corpus.

---

## Phase 4 - Local LLM provider abstraction

**Goal:** make generation a deployment choice, not a code dependency.

- `LLMProvider` protocol for completion and schema-constrained output, selected by
  environment variables.
- Self-hosted inference runtime as the first implementation, consistent with the
  on-premise constraint; no data leaves the deployment.
- Timeouts, retries, and graceful degradation when the provider is unavailable -
  the API must fail clearly rather than hang.
- Readiness reporting extended to include the configured provider.
- A deterministic fake provider for tests, so CI never needs a model.

Exit criteria: generation works against a locally hosted model, and the test suite
still runs with no model present.

---

## Phase 5 - Claim decomposition and evidence comparison

**Goal:** the product's actual analysis, with grounding enforced.

- Claim decomposition into individually addressable elements (preamble,
  transition, limitations), preserving dependency structure.
- Element-level evidence retrieval and side-by-side comparison between a target
  claim and one or more reference documents.
- Per-element output: supporting passages, source locators, and an explicit
  "insufficient evidence" state.
- Grounding validation: any statement without a resolvable citation is rejected
  before it reaches the response.
- UI for claim comparison with citations linking back to source passages.

Exit criteria: a claim can be decomposed and compared against reference documents,
with every rendered assertion traceable to stored evidence.

Standing constraint: output describes textual correspondence only. ClaimTrace does
not conclude infringement, validity, or patentability.

---

## Phase 6 - Evaluation and demonstration

**Goal:** evidence that the system works, and a path a reviewer can follow.

- Offline evaluation harness over committed datasets: retrieval metrics
  (recall@k, MRR) and grounding metrics (citation validity, unsupported-claim rate).
- Regression gate so retrieval or prompt changes cannot silently degrade quality.
- Reproducible demonstration script with synthetic sample documents.
- Performance characterisation: ingestion throughput and query latency on
  commodity on-premise hardware.
- Documented limitations based on measurement rather than intuition.

Exit criteria: metrics are reproducible from a clean checkout with one documented
command.

---

## Out of scope for all six phases

Authentication, authorisation, multi-tenancy, Kubernetes, CI/CD deployment
pipelines, cloud infrastructure, and hosted third-party model APIs. These are
deliberate boundaries for a portfolio project that demonstrates retrieval
engineering, not platform operations.
