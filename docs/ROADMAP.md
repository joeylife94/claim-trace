# ClaimTrace Roadmap

Six phases, each ending in something runnable and verifiable. Nothing from a later
phase is implemented early: the point of the sequence is that every phase can be
demonstrated on its own.

Current state: **Phases 1, 2A, 2B, and 3A complete; Phase 4A is next.**

Phase 3 was taken before 2C, and split. Claim-level retrieval needs only the
claim graph that 2B already produces, so it could be built and measured
immediately; element decomposition (2C) is the harder domain-judgement problem
and benefits from having a working retrieval and evaluation loop to test
against.

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

Split in two, because the ingestion boundary is useful and verifiable on its own,
and because structural parsing is where the domain judgement lives.

### Phase 2A - Ingestion boundary and page provenance (complete)

**Goal:** get a patent PDF into the system as stored, citable page text.

Delivered:

- `POST /api/v1/documents` accepting one PDF, with validation by extension,
  declared type, `%PDF-` signature, size (streaming-bounded), and emptiness.
- Content-addressed local storage behind a `FileStorage` protocol; the client's
  filename never determines a path.
- SHA-256 identity with a unique constraint: duplicates return the existing record
  rather than storing a second copy.
- `DocumentParser` protocol with a PyMuPDF implementation for digital PDFs,
  returning ordered page text and parser identity.
- `documents` and `document_pages` tables (revision `0002`), with pages and the
  `completed` status written in one transaction.
- Explicit lifecycle (`uploaded → processing → completed | failed`) with persisted
  error codes, so failures stay traceable.
- `SourceLocator` — `(document_id, page_number, start_char, end_char)` over stored
  page text — defined, validated, and returned with every page.
- Minimal upload + document status + page text UI.
- Structured ingestion logging that never records document text.

Exit criteria met: a synthetic PDF can be uploaded, parsed, persisted, listed, and
read back page by page, with duplicates and every rejection path behaving as
documented.

Explicit non-goals honoured: no OCR, no section detection, no claim parsing, no
chunking, no queue.

### Phase 2B - Deterministic claim structural parsing (complete)

**Goal:** turn page text into a claim graph without inventing a new coordinate
system.

Delivered:

- `ClaimParser` protocol with `KoreanRuleBasedClaimParser`
  (`korean-rule-based-claims` 0.1.0). Rules only - no model, no embedding, no
  legal reasoning.
- Claims-region detection, heading detection across the common Korean forms
  (`청구항 1`, `청구항 제1항`, `[청구항 1]`, `【청구항 1】`, full-width digits) and a
  minimal line-anchored `Claim 1` fallback.
- Dependency extraction for `에 있어서` / `에 따른` / `에 기재된` forms, including
  `또는`, `및`, comma lists, and `내지` ranges, with a required dependency particle
  so technical numbers never become edges.
- Classification into `independent` / `dependent` / `multiple_dependent` /
  `unknown`, with `unknown` used instead of a guess.
- Dependencies persisted as a graph; self-references, unresolved references, and
  backwards ranges are refused with warnings, and cycles are detected.
- Claim source stored as ordered page-relative spans; a page-crossing claim gets
  one span per page, and claim text is defined as those spans joined by `"\n"`.
- A parse lifecycle (`processing → completed | no_claims_found | failed`) that is
  fully separate from document ingestion status.
- Idempotency per parser version, with in-place retry of a failed attempt.
- `POST /claims/parse`, `GET /claims`, `GET /claims/{claim_number}`.
- UI: parse action, claim list with types and dependency lists, source span
  buttons that open and highlight the exact range in the page viewer.
- Migration `0003`, and tests covering the parser rules, persistence, and the API.

Exit criteria met: a document's claim set is retrievable with dependencies intact,
and every claim resolves exactly to text on a page.

Explicit non-goals honoured: no element decomposition, no other languages, no
OCR, no retrieval, no LLM.

### Phase 2C - Claim element decomposition and review boundary (next)

**Goal:** break each claim into individually addressable elements, still
deterministically, and give a reviewer a way to confirm or correct them.

- Element decomposition schema: elements belong to a claim and carry their own
  page-anchored spans, so an element is a sub-span of its claim rather than a new
  coordinate system.
- Deterministic splitting of Korean claim bodies on structural markers
  (`~와/과`, `; `, enumerated limitations, `상기` reference chains), with an explicit
  confidence or warning when a claim resists splitting.
- A review boundary: a reviewer can accept a decomposition or mark it wrong, and
  that judgement is persisted separately from the parser's output so a re-parse
  never silently discards it.
- API and UI for reading and reviewing elements, reusing the existing span viewer.

Exit criteria: a claim can be decomposed into elements whose spans resolve exactly,
and a reviewer's verdict survives a re-parse.

Explicit non-goals: retrieval, embeddings, and any LLM generation - Phase 2C
stops at the deterministic boundary that later phases will build on.

---

## Phase 3 - Indexing and hybrid retrieval

Split in two: claim-level retrieval is useful and measurable on its own, and it
is what the rest of the product needs first.

### Phase 3A - Claim indexing and hybrid retrieval (complete)

**Goal:** retrieve claims with citations, and be able to say why each one was
retrieved.

Delivered:

- `EmbeddingProvider` protocol with a real local sentence-transformers
  implementation (`intfloat/multilingual-e5-small`, 384d, CPU) and a
  deterministic hash provider that downloads nothing and backs the whole test
  suite.
- A claim indexing lifecycle separate from ingestion and parsing, with a
  retrieval profile recorded per run and idempotency keyed on it.
- Migration `0004`: `claim_index_runs`, `claim_search_records`, `pg_trgm`, an
  HNSW cosine index, and GIN indexes for full-text and trigram matching.
- Dense retrieval over pgvector; lexical retrieval over PostgreSQL `simple`
  full-text plus trigram, tuned for Korean compounds and josa attachment.
- Reciprocal Rank Fusion with configurable `k`, per-channel ranks and scores
  preserved, and `hybrid` / `dense` / `lexical` modes.
- `POST /api/v1/search/claims`, indexing endpoints, a `/search` UI, and a
  retrieval index panel on the document page.
- A reproducible evaluation over a synthetic Korean corpus reporting
  Recall@1/3/5 and MRR@10 per mode, including where hybrid loses to a single
  channel.

Exit criteria met: a query returns ranked claims, each carrying spans that
resolve exactly against stored page text; retrieval quality is measurable and
measured.

Explicit non-goals honoured: no reranking, no chunking of descriptions, no LLM.

### Phase 3B - Description retrieval and reranking

**Goal:** widen retrieval past claims, and improve precision at the top.

- Chunking strategy aware of patent structure - description segments are not
  chunked like claims.
- Optional `Reranker` seam over the fused top-k; the pipeline must work with it
  absent.
- A retrieval regression gate wired into CI, using the Phase 3A evaluation.

Exit criteria: description passages are retrievable alongside claims, and a
reranker can be switched on without touching the retrieval or API layers.

---

## Phase 4A - Local LLM provider abstraction (next)

**Goal:** make generation a deployment choice, not a code dependency.

- `LLMProvider` protocol for completion and schema-constrained output, selected by
  environment variables - built the same way `EmbeddingProvider` was in 3A:
  plain Python in and out, no framework types crossing the boundary.
- Two self-hosted implementations, consistent with the on-premise constraint and
  so the protocol is proven by more than one caller: Ollama, and an
  OpenAI-compatible endpoint such as vLLM. No data leaves the deployment.
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
