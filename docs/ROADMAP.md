# ClaimTrace Roadmap

Six phases, each ending in something runnable and verifiable. Nothing from a later
phase is implemented early: the point of the sequence is that every phase can be
demonstrated on its own.

Current state: **Phases 1, 2A, 2B, 2C, 3A, 4A-1, 4A-2, 5A, and the bounded Phase 5 controlled-pilot analysis flow are complete. Phase 3B and the remaining Phase 6 expansion items are future/unverified.**

Phase 3 was taken before 2C, and split. Claim-level retrieval needed only the
claim graph that 2B already produced, so it could be built and measured
immediately; element decomposition and review were completed later against the
working retrieval and evaluation loop.

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

The ingestion boundary, claim structure, deterministic decomposition, and human
review boundary are independently verifiable steps within the controlled-pilot
scope.

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
read back page by page, with duplicates and rejection paths behaving within the
accepted ingestion contract.

Explicit non-goals honoured: no OCR, no section detection, no scanned/image-only
PDF recovery, no queue.

### Phase 2B - Deterministic claim structural parsing (complete)

**Goal:** turn page text into a claim graph without inventing a new coordinate
system.

Delivered:

- `ClaimParser` protocol with `KoreanRuleBasedClaimParser`
  (`korean-rule-based-claims` 0.1.0). Rules only - no model, no embedding, no
  legal reasoning.
- Claims-region detection and supported Korean claim heading forms.
- Dependency extraction for supported Korean reference forms, with guards so
  technical numbers do not become claim edges.
- Classification into `independent` / `dependent` / `multiple_dependent` /
  `unknown`, with `unknown` used instead of a guess.
- Dependencies persisted as a graph; malformed/self/unresolved dependency cases
  are refused or warned rather than silently invented.
- Claim source stored as ordered page-relative spans, preserving canonical page
  provenance.
- A parse lifecycle separate from document ingestion status.
- Idempotency per parser version, with retry of a failed attempt.
- Claim parsing/read APIs and source-navigation UI.

Exit criteria met: a document's claim set is retrievable with dependencies intact,
and every supported claim resolves exactly to stored page text.

Explicit non-goals honoured: no universal Korean patent parsing correctness, no
OCR, and no legal interpretation.

### Phase 2C - Claim element decomposition and review boundary (complete)

**Goal:** break a claim into individually addressable, source-backed elements and
keep reviewer judgement separate from machine output.

Delivered within the frozen controlled-pilot boundary:

- deterministic source-backed claim-element decomposition;
- element provenance tied back to persisted source spans rather than a separate
  citation coordinate system;
- append-only human review state persisted separately from machine-generated
  analytical output;
- review/navigation surfaces that return the reviewer to the persisted source
  evidence used by the decomposition;
- deterministic regression coverage for the supported synthetic/public-safe
  boundary.

Exit criteria met within the accepted Proof scope: decomposition output is
source-verifiable and reviewer state remains distinct from generated/machine
state.

Explicit non-goals remain: this decomposition is not a legal claim construction
and does not determine infringement, validity, novelty, inventive step,
equivalence, or patentability. Universal parser/decomposition correctness is not
claimed.

---

## Phase 3 - Indexing and hybrid retrieval

Split in two: claim-level retrieval is useful and measurable on its own; broader
description retrieval/reranking remains separate future work.

### Phase 3A - Claim indexing and hybrid retrieval (complete)

**Goal:** retrieve claims with citations, and be able to say why each one was
retrieved.

Delivered:

- `EmbeddingProvider` protocol with a local sentence-transformers implementation
  and a deterministic hash provider used by offline regression.
- A claim indexing lifecycle separate from ingestion and parsing, with a
  retrieval profile recorded per run and idempotency keyed on it.
- Dense retrieval over pgvector and lexical retrieval over PostgreSQL full-text
  plus trigram matching.
- Reciprocal Rank Fusion with per-channel ranks/scores preserved and
  `hybrid` / `dense` / `lexical` modes.
- Claim search/indexing APIs, search UI, and source navigation.
- Reproducible synthetic regression evaluation reporting Recall@k and MRR.

Exit criteria met: a query returns ranked claims carrying resolvable source spans;
retrieval behavior is measurable and regression-tested.

Explicit non-goals honoured: no description retrieval, no reranking, and no
benchmark-quality general patent retrieval claim.

### Phase 3B - Description retrieval and reranking (future / unverified)

**Goal:** widen retrieval past claims, and improve precision at the top.

Potential bounded work:

- patent-structure-aware description chunking;
- optional `Reranker` seam over fused top-k;
- evaluation specific to description retrieval/reranking.

This phase is not part of the frozen v1.0 accepted capability boundary. No
completion or quality claim is made for description retrieval or reranking.

---

## Phase 4A - Local generation

### Phase 4A-1 - LLM provider boundary (complete)

**Goal:** make generation a deployment choice, not a code dependency.

Delivered:

- provider-neutral LLM protocol and configuration boundary;
- locally hosted/self-hosted provider implementations plus deterministic fake
  provider for CI/offline execution;
- provider-neutral error/timeout handling and schema validation;
- narrow diagnostics and development generation surfaces without chat/history;
- no persistence of prompts/completions as domain data.

Accepted evidence includes historical local-model execution plus deterministic
CI/offline coverage. Current real-local-model quality is not promoted beyond the
explicit evidence recorded in the MASTER.

### Phase 4A-2 - Evidence-grounded generation (complete)

**Goal:** answers that can be checked, not answers that merely sound right.

Delivered:

- grounded generation composed with claim retrieval;
- request-local evidence identifiers resolved server-side to canonical source
  locators;
- strict structured output with no unrestricted free-form citation coordinates;
- server-resolved quotes from persisted source text;
- explicit `insufficient_evidence` behavior;
- deterministic grounding evaluation and hostile-payload refusal coverage;
- source-navigation UI for generated analytical output.

Standing constraint: this phase answers about retrieved text and determines
nothing about infringement, validity, novelty, inventive step, equivalence, or
patentability.

---

## Phase 5A - Claim comparison workspace (complete within controlled-pilot scope)

**Goal:** compare a target claim against a reference document while preserving the
same grounding and source-verification guarantee.

Delivered within the accepted v1.0 Proof boundary:

- target/reference claim comparison under strict reference-document scope;
- evidence-backed textual correspondence with resolvable source locators;
- explicit insufficient/no-supported-correspondence behavior rather than a forced
  conclusion;
- navigation from comparison output back to persisted source text;
- deterministic whole-product and comparison regression coverage on the committed
  synthetic/public-safe corpus.

Exit criteria met for the controlled pilot: comparison surfaces remain grounded
and source-verifiable.

Standing constraint: comparison describes textual correspondence only. It does
not determine infringement, validity, novelty, inventive step, equivalence,
patentability, or any other legal conclusion.

---

## Phase 5 - Claim decomposition and evidence comparison (bounded controlled-pilot flow complete)

**Goal:** combine deterministic decomposition, evidence-backed comparison, and
review/source navigation into the product's analytical workflow.

Delivered within the accepted v1.0 scope:

- deterministic claim decomposition into source-backed elements;
- target/reference evidence comparison under bounded document scope;
- per-element/source-backed analytical output with explicit insufficient-evidence
  behavior where supported evidence is absent;
- grounding/source-resolution validation before analytical output is presented;
- append-only reviewer state separate from machine output;
- UI navigation from generated/reviewed analytical surfaces back to persisted
  source passages.

Exit criteria met within the frozen Proof boundary: claims can be decomposed and
compared against reference evidence with rendered analytical assertions tied to
stored source evidence.

Standing constraint: this workflow remains analytical/review support only.
ClaimTrace does not conclude infringement, validity, novelty, inventive step,
equivalence, or patentability.

---

## Phase 6 - Evaluation and demonstration (core v1.0 proof complete; expansion items remain)

**Goal:** evidence that the system works within its bounded scope, and a path a
reviewer can reproduce.

Accepted v1.0 evidence includes:

- deterministic retrieval regression over the committed synthetic corpus;
- deterministic grounded evaluation and hostile-grounding checks;
- expected failure-state verification;
- clean-start and whole-product golden-path verification;
- committed screenshots, architecture visual, and golden-path WebM;
- one-command deterministic regression verification added post-v1.

Still future/unverified unless separately accepted:

- benchmark-quality general patent retrieval performance;
- broader real-world corpus characterization;
- current real-local-model quality beyond recorded historical evidence;
- generalized performance characterization on arbitrary commodity hardware;
- OCR/scanned-PDF recovery;
- production security/compliance certification.

---

## Out of scope for the accepted v1.0 Proof boundary

Authentication, authorisation/RBAC, multi-tenancy, public-cloud production
readiness, Kubernetes, billing/admin production readiness, OCR/scanned-image PDF
recovery, legal conclusions, benchmark-quality retrieval claims, and production
security/compliance certification remain outside the accepted v1.0 Proof scope.

The roadmap describes implementation direction and historical phase intent;
`CLAIMTRACE_V1_MASTER.md` remains authoritative for the frozen v1.0 capability,
evidence, limitation, and non-claim boundary.
