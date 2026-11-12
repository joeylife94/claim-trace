# ClaimTrace Roadmap

Six phases, each ending in something runnable and verifiable. Nothing from a later
phase is implemented early: the point of the sequence is that every phase can be
demonstrated on its own.

Current state (updated 2026-11-11): **Phases 1, 2A, 2B, 2C, 3A, 4A-1, 4A-2, and 5A complete within the accepted controlled-pilot boundary. Phase 3B and Phase 6 are partially delivered; each phase section below says what exists and what does not.** Work after the v1.0 freeze is summarised in [Post-v1 progression](#post-v1-progression). No milestone is active, and the next destination needs a human decision (see [Candidate next destinations](#candidate-next-destinations-not-selected)).

The phase sections below are the plan and delivery record as written; where later work
makes a sentence read as contradicted, a dated note under it says so rather than
rewriting it.

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

  > Note (2026-11-11): since the v1.0 freeze an operator can retry a `failed`
  > document from its persisted original (`POST /api/v1/documents/{id}/retry`), which
  > moves it `failed → processing` and on to `completed` or `failed` again. Retry is
  > explicit and operator-driven; there is still no queue or background worker.
- `SourceLocator` — `(document_id, page_number, start_char, end_char)` over stored
  page text — defined, validated, and returned with every page.
- Minimal upload + document status + page text UI.
- Structured ingestion logging that never records document text.

Exit criteria met: a synthetic PDF can be uploaded, parsed, persisted, listed, and
read back page by page, with duplicates and every rejection path behaving as
documented.

Explicit non-goals honoured: no OCR, no section detection, no claim parsing, no
chunking, no queue.

> Note (2026-11-11): true when this phase closed. Description section detection and
> segmentation were added later as a separate derived layer (see Phase 3B), not in
> ingestion. There is still no OCR and no queue; since the later PDF text-layer
> classification, a PDF in which any page has no extractable text is rejected rather
> than ingested partially.

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

### Phase 2C - Claim element decomposition and review boundary (complete)

**Goal:** break each claim into individually addressable elements, still
deterministically, and give a reviewer a way to confirm or correct them.

Delivered within the accepted controlled-pilot boundary:

- Element decomposition schema: elements belong to a claim and carry their own
  page-anchored spans, so an element is a sub-span of its claim rather than a new
  coordinate system.
- Deterministic source-backed decomposition of supported claim structures.
- A review boundary in which reviewer judgement is persisted separately from
  machine output and remains append-only.
- API/UI review surfaces reusing persisted source navigation so generated and
  reviewed analytical output can be checked against stored source text.

Exit criteria met within the frozen v1.0 Proof boundary: supported claims can be
decomposed into source-backed elements and reviewer state remains separate from
machine output.

Explicit non-goals remain: no legal claim construction or determination of
infringement, validity, novelty, inventive step, equivalence, or patentability;
universal Korean patent decomposition correctness is not claimed.

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

  > Note (2026-11-11): after the freeze, lexical retrieval gained a bounded
  > term-level trigram eligibility fallback for multi-word queries (a
  > `word_similarity` threshold of 0.60 per term; it admits candidates and adds no
  > second ranking score). See `retrieval/lexical.py`.
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

> Note (2026-11-11): true when this phase closed. Description segmentation and
> retrieval were added afterwards under Phase 3B; there is still no reranker.

### Phase 3B - Description retrieval and reranking (partially delivered)

**Goal:** widen retrieval past claims, and improve precision at the top.

- Chunking strategy aware of patent structure - description segments are not
  chunked like claims.
- Optional `Reranker` seam over the fused top-k; the pipeline must work with it
  absent.
- A retrieval regression gate wired into CI, using the Phase 3A evaluation.

Exit criteria: description passages are retrievable alongside claims, and a
reranker can be switched on without touching the retrieval or API layers.

This phase was not part of the accepted v1.0 capability boundary. Status as of
2026-11-11, by item:

- **Description retrieval: exists (post-v1, destination D4).** A structure-aware
  segmenter derives description segments from persisted page text, and they are
  indexed and searched through separate endpoints (migration `0007`;
  `POST /api/v1/documents/{id}/descriptions/derive`, `.../descriptions/index`,
  `POST /api/v1/search/descriptions`). It is not merged into claim search: a
  description search returns description evidence only. It has no dedicated UI. See
  [D4_DESCRIPTION_AWARE_EVIDENCE.md](D4_DESCRIPTION_AWARE_EVIDENCE.md).
- **Retrieval regression gate in CI: exists.** The `Progression Deterministic
  Regression` workflow runs `make verify-deterministic-regression`, which pins a
  fake-provider baseline (see Phase 6).
- **`Reranker` seam: not built.** Nothing in `apps/api/src` implements reranking.
- The exit criterion "retrievable alongside claims" is therefore not met as
  written: claims and descriptions are retrieved through separate endpoints.

---

## Phase 4A - Local generation

### Phase 4A-1 - LLM provider boundary (complete)

**Goal:** make generation a deployment choice, not a code dependency.

- `LLMProvider` protocol for plain and schema-constrained output, selected by
  environment variables - built the same way `EmbeddingProvider` was in 3A:
  plain Python in and out, no framework types crossing the boundary. A test
  asserts the package imports no web framework or ORM.
- Two self-hosted implementations, consistent with the on-premise constraint and
  so the protocol is proven by more than one caller: Ollama, and an
  OpenAI-compatible endpoint such as vLLM. No data leaves the deployment, and the
  hosted OpenAI service is deliberately not a supported target.
- A provider-neutral error taxonomy, a conservative retry policy (only failures
  that never reached the server are replayed), and three-level timeout control
  with correct cancellation propagation.
- Structured JSON output with strict extraction and schema validation that runs
  *even when* the server enforced the schema - which Phase 4A-1 validation proved
  necessary: constrained decoding guarantees types, not value ranges.
- A deterministic fake provider, the default, so CI and offline work never need a
  model and the whole application runs with nothing downloaded.
- Narrow diagnostics: `GET /api/v1/llm/status`, two development-only generation
  endpoints, and a `/llm` page. No chat, no history, no streaming.
- No database migration: prompts, completions, and provider health are runtime
  infrastructure, not domain data.

Exit criteria met: generation works against a locally hosted model
(`qwen2.5:1.5b`, warm 0.18-0.38 s, structured 0.61-0.94 s), and the 621-test suite
(the count when this phase closed)
runs with no model present. vLLM is contract-tested against a mocked transport;
no real vLLM server was run. See
[docs/ARCHITECTURE.md](ARCHITECTURE.md) section 10.

### Phase 4A-2 - Evidence-grounded generation (complete)

**Goal:** answers that can be checked, not answers that sound right.

Delivered:

- `GroundedGenerationService` composes the existing `ClaimSearchService` and
  `LLMGenerationService`. Neither changed - 4A-1 left the generation service with
  no session and no retrieval collaborator precisely so this would be an addition.
- A request-local **evidence catalog** issues opaque identifiers (`EV-001`, …).
  The model is shown claim text and may answer only with those identifiers; it
  never sees and never produces a document id, a page number, or an offset.
  Fabricating a citation is not unlikely, it is unrepresentable - the output
  schema has nowhere to put a locator, and an unissued identifier resolves to
  nothing.
- Structured output against a strict schema with **no free-form answer field**.
  The answer text is composed by the server from statements that passed citation
  validation.
- Every citation resolves to a canonical `(document_id, page_number, start_char,
  end_char)` span, and each quote is read out of `document_pages.text` at those
  offsets by the server rather than reproduced by the model. **No second citation
  coordinate system was introduced.**
- Context budget admits whole claims only. A claim that will not fit is dropped
  and counted, never truncated - a half-included claim would still be citable.
- One bounded repair attempt for a grounding-rule violation, reusing the same
  evidence and adding only server-owned corrective text.
- `insufficient_evidence` is a normal 200 outcome, with a fixed server-owned
  limitation sentence. Zero retrieved candidates bypass the provider entirely.
- `POST /api/v1/grounded/answers` and a `/grounded` workspace. Not a chat: no
  history, no memory, no prompt or model controls.
- **No migration.** The output is request-scoped; the schema is unchanged at
  revision 0004.

  > Note (2026-11-11): `POST /api/v1/grounded/answers` is still stateless and still
  > writes nothing. Separately, the later persistent Case workspace (migrations
  > `0008` and `0009`) can store a grounded result under an analyst Case through
  > `POST /api/v1/cases/{case_id}/grounded-results` and reopen it later. Those Case
  > endpoints are API-only (no UI), and grounded answers remain claim-only. The
  > "no history, no memory" and "revision 0004" statements describe the original
  > phase and `/grounded` itself; the Alembic head is now `0009`.

Verified (as recorded when this phase closed): 876 backend tests; a deterministic evaluation tier (16 cases, 23 newly
authored synthetic Korean claims across 3 documents) with citation resolution
1.00 and 6/6 hostile payloads refused; and a real `qwen2.5:1.5b` tier with
structured-output success 1.00, citation resolution 1.00, and zero scope leaks -
alongside honest weaknesses in that small model's judgement. See
[docs/ARCHITECTURE.md](ARCHITECTURE.md) section 11 and
`apps/api/evals/results/grounded/`.

Standing constraint held: this phase answers *about* retrieved text and
determines nothing about infringement, validity, novelty, inventive step, or
patentability.

---

## Phase 5A - Claim comparison workspace (complete within controlled-pilot scope)

**Goal:** two documents, claim to claim, with the same grounding guarantee.

Delivered within the accepted v1.0 Proof boundary:

- Select target/reference documents and compare claims under strict reference
  document scope.
- Retrieve correspondences through the existing claim retrieval pipeline
  (`ClaimSearchService`), so every returned claim carries its canonical
  page-relative source spans and resolves back to stored text.
- Preserve explicit insufficient/no-supported-correspondence behavior rather than
  forcing a match.
- Navigate comparison/review surfaces back to persisted source text.
- Keep append-only human review separate from machine output.

Exit criteria met within the accepted Proof boundary: target/reference claim
comparison is source-verifiable and reviewable on the deterministic controlled
pilot flow.

> Correction (2026-11-11): an earlier version of this section, and the architecture
> document, described comparison as reusing "the grounded evidence/citation
> contract". As built (`services/claim_comparison.py`), comparison is
> retrieval-only: the target claim's stored text is the query, retrieval is forced to
> the one reference document, and the ranked stored claims are returned with their
> spans. `claim_comparison.py` does not import or call `GroundedGenerationService`
> or an LLM provider.

Standing constraint: output describes textual correspondence only. ClaimTrace
does not determine infringement, validity, novelty, inventive step, equivalence,
patentability, or any other legal conclusion.

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

Status as of 2026-11-11: **partially delivered.**

Exists:

- the retrieval and grounded evaluation harnesses under `apps/api/evals/`
  (`python -m evals.run`, `python -m evals.grounded_run`), with committed synthetic
  datasets and committed result files;
- a CI regression gate: `make verify-deterministic-regression` re-runs both
  evaluations with the fake embedding provider and asserts a pinned baseline, run on
  pull requests by the `Progression Deterministic Regression` workflow;
- demonstration and verification scripts over the synthetic seed documents
  (`scripts/verify-v1-06-golden-path.sh`, `scripts/capture-v1-07-proof.sh`,
  `scripts/verify-controlled-pilot-handoff.sh`);
- limitations recorded in `CLAIMTRACE_V1_MASTER.md` (Sections 6 and 7).

Does not exist:

- an ingestion-throughput performance characterisation. The retrieval evaluation
  reports query latency; no ingestion-throughput measurement is committed.

Caveat: the committed result files in `apps/api/evals/results/` were generated on
2026-07-26 with the `intfloat/multilingual-e5-small` profile, before the later
lexical fallback change. Current real-embedding numbers were not re-measured. The
enforced gate pins fake-provider numbers instead; see
[apps/api/evals/README.md](../apps/api/evals/README.md).

---

## Post-v1 progression

After the `v1.0-proof` freeze, work continued as numbered milestones (P1-P14) toward
numbered destinations (D1-D6). The authoritative record of each, with its evidence
and non-claims, is `CLAIMTRACE_V1_MASTER.md` (milestones P1-P13 in Section 10, P14 with
D2 in Section 11, destinations in Sections 11-15, current state in Section 16). This table is only a map.

| Milestone | What it added | Outcome |
| --- | --- | --- |
| P1 | `make verify-deterministic-regression` and a PR workflow for it | Accepted and merged |
| P2, P3, P4, P13 | Ingestion and claim-graph persistence failures that previously could strand a record are terminalized as `failed` with client-safe error codes | Accepted and merged |
| P5, P6, P7 | Documentation reconciliation: ingestion failure table, roadmap phase statuses, removal of a duplicate Phase 5 section | Accepted and merged |
| P8, P9, P10 | Operator retry of a failed ingestion from the persisted original: API, Documents UI form, and a real web/API/PostgreSQL verifier | Accepted and merged |
| P11, P12 | Evidence recovery for the known `g01` question, and a bounded Korean term-level lexical fallback with negative regression coverage | Accepted and merged |
| P14 | One-command controlled-pilot handoff verifier (`scripts/verify-controlled-pilot-handoff.sh`) | Accepted and merged |

| Destination | Scope | Outcome |
| --- | --- | --- |
| D1 | Controlled pilot for one analyst/reviewer on a trusted workstation | Reached |
| D2 | Delivery-ready controlled-pilot handoff (P14) | Reached |
| D3 | Real-document controlled pilot: manifest-driven verifier over two hash-pinned public Korean patent PDFs, downloaded at run time and not committed | Reached |
| D4 | Description-aware evidence retrieval: derive, index and search description segments (API only; migration `0007`) | Reached |
| D5 | Persistent analyst Cases and persisted, reopenable Case-grounded results (API only; migrations `0008`, `0009`) | Reached |
| D6 | Mixed-PDF input: text-layer classification that fails closed (D6-01) | Closed at the fail-closed boundary by Human Review on 2026-11-11; OCR deferred, no D6-02 |

No milestone is active. The Alembic head is `0009`.

---

## Candidate next destinations (not selected)

These are candidates only, listed without order and without commitment. None is
planned, scheduled, or started. Each would need its own Human Review decision and a
bounded acceptance contract before any work begins. The list mirrors Section 16 of
`CLAIMTRACE_V1_MASTER.md`, which is authoritative.

- OCR / scanned-input recovery, behind the OCR Gate recorded in the MASTER (Section 15);
- a web surface for Cases and description retrieval;
- description evidence in grounded analysis, with or without reranking;
- real-local-model quality re-measurement and refreshed evaluation artifacts;
- relaxing the conservative mixed-PDF rejection for text-native PDFs with blank or drawing-only pages;
- deployment hardening for a shared-network host, starting from Issue #65.

---

## Out of scope for all six phases

Authentication, authorisation, multi-tenancy, Kubernetes, CI/CD deployment
pipelines, cloud infrastructure, and hosted third-party model APIs. These are
deliberate boundaries for a portfolio project that demonstrates retrieval
engineering, not platform operations.

Authentication, RBAC, multi-tenancy, public cloud, Kubernetes, private or customer
corpora, and any legal-conclusion capability remain out of scope unless a human
explicitly brings them in.

The authoritative frozen v1.0 capability, evidence, limitations, and non-claims
remain defined by `CLAIMTRACE_V1_MASTER.md`, which also carries the post-v1 ledger
and the current state (Section 16); this roadmap must not be read as a legal or
production-readiness claim.
