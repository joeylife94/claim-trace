# ClaimTrace v1.0 Master

> **Authoritative execution contract for ClaimTrace v1.0.** Read this before every batch. `README.md` is external-facing, `docs/ARCHITECTURE.md` explains design, and `docs/ROADMAP.md` records broader possibilities. **This file controls what v1.0 is finishing now.**

**Last execution update:** 2026-08-19  
**Current target:** L4 Controlled Pilot  
**Current active batch:** V1-04 — Claim Element Decomposition  
**Current batch state:** **IN PROGRESS — deterministic boundary merged; persistence/idempotency slice next**

---

## 1. Goal and Product Boundary

Frozen v1.0 flow:

**ingest → parse → index → retrieve → ask → compare → decompose → review → verify source evidence**

Target: one analyst/reviewer on a trusted workstation or controlled on-premise environment, working with text-based Korean patent PDFs and source-verifiable analytical output.

Explicit non-goals unless deliberately re-scoped:

- OCR / scanned-PDF recovery;
- auth / RBAC / multi-tenancy;
- public cloud / Kubernetes / production deployment pipelines;
- billing / admin / team workspace;
- chat history / memory / streaming / generic tool calling / notifications;
- broad observability or full multilingual support;
- hosted third-party LLM APIs as default path;
- legal advice or determinations of infringement, validity, novelty, equivalence, inventive step, or patentability.

Human Review is the **final release/proof gate**, not a requirement for ordinary bounded intermediate PR merges.

---

## 2. Current State

Existing pre-v1 engine: FastAPI + Next.js, PostgreSQL + pgvector/pg_trgm, PDF persistence/provenance, deterministic Korean claim parsing, dense/lexical/RRF retrieval, exact source links, local/self-hosted LLM boundary, grounded Q&A with server-issued evidence IDs, citation resolution, explicit insufficient evidence, deterministic/real-local-model evaluation tiers, hostile-evidence guards, Docker Compose.

Historical evidence retained until final rerun: 876 backend tests after Phase 4A-2; deterministic grounded citation resolution `1.000`; `qwen2.5:1.5b` citation resolution `1.000`; statement citation coverage `1.000`; forbidden cross-document citations `0`.

Golden-path state:

| Stage | Status | v1 delta |
| --- | --- | --- |
| 1–10 ingest → grounded Q&A | READY | final runtime re-verification only |
| 11 target/reference selection | EXECUTED GREEN | V1-03 closed |
| 12 claim comparison | EXECUTED GREEN | V1-02/V1-03 closed |
| 13 element decomposition | IN PROGRESS | deterministic provenance boundary merged; persistence/API remain |
| 14 persisted human review | MISSING | V1-05 |
| 15 source verification everywhere | PARTIAL | comparison source-linked; element boundary preserves source sub-spans |

**Do not rebuild stages 1–12.**

---

## 3. Execution Plan

### V1-00 — Master Freeze
**CLOSED**

### V1-01 — Golden Path Gap Audit
**CLOSED**

### V1-02 — Claim Comparison Backend
**CLOSED**

Executed closure evidence:

- PR #7 exact head `f62b8847ec3bfd6df4ecf1750b6a0e5d90202f6c`;
- workflow run `32225430081` → **success**;
- database-free comparison tests **26 PASS**;
- PostgreSQL integration **3 PASS / 0 skipped**;
- Ruff lint + format **PASS**;
- Docker API build + PostgreSQL readiness **PASS**;
- merged to `main` as `db5e39d2118e42527a3794a32173e08535f18cec`.

### V1-03 — Comparison UI + Flow Stitching
**CLOSED**

Executed closure evidence:

- PR #8 workspace → run `32228257540` **success**, merged `3a12c6601da8ece8c71ea5233c77100d2229bbb9`;
- PR #9 flow stitching → run `32228493202` **success**, merged `6088fbbfbc4abad2e0983b03e464a74919b8124d`;
- PR #10 final exact head `1f093cbc6d611ef1aaedbea1ed934ff1f88d860c`;
- V1-02 regression run `32242502338` → **success**;
- V1-03 run `32242502306` → **success**;
- browser job completed exact-head checkout, deterministic runtime config, API/Web image build, PostgreSQL migration, deterministic two-document seed, API/Web startup, Chromium install, and browser golden-path execution → **PASS**;
- no unresolved review threads;
- merged with expected-head guard to `main` as `6de5a391715ace893189378710f8852b4542dfaa`.

### V1-04 — Claim Element Decomposition
**IN PROGRESS**

Goal: decompose a persisted claim into individually reviewable elements/limitations while preserving canonical source provenance and keeping machine output explicitly non-authoritative.

Acceptance:

- [ ] element domain/schema exists with stable identifiers and ordered elements;
- [ ] every element is represented as a sub-span of the canonical persisted claim source;
- [ ] decomposition run is versioned and idempotent/re-runnable without ambiguous duplication;
- [ ] resistant/unsupported claim shapes produce explicit warnings or bounded failure instead of invented structure;
- [ ] API exposes decomposition result without legal-conclusion fields;
- [ ] focused tests cover ordering, source-span containment, idempotency, and resistant-claim behavior;
- [ ] exact-head executable checks are GREEN before ordinary bounded PR merge.

Completed bounded slice — PR #11:

- deterministic `DeterministicElementParser` boundary;
- conservative explicit-semicolon splitting;
- exact page-relative source sub-span mapping, including cross-page claims;
- no-delimiter claim remains one element with explicit `no_structural_delimiter` warning;
- provenance mismatch raises instead of approximating;
- leading/consecutive semicolon empty segments are ignored with `EMPTY_SEGMENT` rather than becoming punctuation-only elements;
- focused tests cover ordering, source containment, cross-page mapping, resistant/no-delimiter behavior, empty segments, and provenance mismatch;
- final exact head `7a2d39a7cdde4d62fec563ddf8d7887f17a8f409`;
- V1-02 regression run `32252992179` → **success**;
- V1-03 regression/browser run `32252992260` → **success**;
- V1-04 Claim Element Verification run `32252992292` → **success**;
- review thread for punctuation-only segments resolved;
- merged with expected-head guard to `main` as `0bb31d7151df85c43c5e8621acd25c8220b2f87f`.

Next bounded slice:

- persistence/schema only for decomposition runs, ordered elements, and exact source spans;
- parser name/version participates in idempotency identity;
- rerunning the same parser version must not duplicate ambiguous element sets;
- a later parser version may coexist without overwriting older provenance;
- focused PostgreSQL tests must prove idempotency, ordering, and source-span containment;
- no public API/UI/human-review state in this slice.

Non-goals:

- no human-review persistence yet (V1-05);
- no claim comparison changes;
- no LLM-based legal interpretation;
- no OCR/auth/cloud/Kubernetes work;
- no unrelated UI redesign.

### V1-05 — Human Review Boundary
**PLANNED**

Review record separate from machine output; `accepted` / `needs_correction`; survives reprocessing; review UI/source navigation; persistence tests.

### V1-06 — Operational Hardening
**PLANNED**

Clean clone/start; empty-DB migration; deterministic demo data; golden-path procedure; general CI backend/integration/lint/frontend gates; failure-state validation.

### V1-07 — Final Validation + Wishket Proof
**PLANNED**

Final test/evaluation; README; architecture visual; ≥4 screenshots; demo asset; limitations; release/tag. **Human Review remains the final release/proof gate.**

---

## 4. Execution Rules

Every batch defines **Goal / Scope / Acceptance / Non-goals** and records **What changed / What was actually executed / What was not verified / Remaining risks / Exact next action**.

PR lifecycle:

1. inspect current active focused PR and current exact-head pull-request-visible workflows first;
2. RED/CANCELLED/TIMED_OUT/ACTION_REQUIRED/stale IN_PROGRESS → inspect first concrete job/step/log; fix only that executed failure;
3. GREEN + in scope + no unresolved review/security/human-decision blocker → merge with expected-head guard;
4. update this MASTER on `main` with concrete evidence and main SHA;
5. continue to the next smallest step in the earliest unfinished batch.

Any SHA/run ID written here is historical evidence only. **Current repository/PR state always wins.** Missing push status is not evidence; prefer PR-visible exact-head workflow evidence. Agent self-report is not proof.

---

## 5. Current Batch Record — V1-04

### What changed

- inspected PR #11 current exact-head RED runs instead of relying on historical handoff;
- proved both V1-04 and V1-02 failures converged on the same PR-introduced Ruff-format mismatch after their functional tests passed;
- formatted the focused element test;
- inspected the remaining unresolved review thread and fixed the concrete leading/consecutive-semicolon bug;
- added focused regression coverage proving empty semicolon segments warn without creating punctuation-only elements;
- resolved the review thread;
- merged PR #11 after all current-head required workflows became GREEN;
- reconciled V1-04 to the next persistence/idempotency slice.

### What was actually executed

- PR #11 current head/workflows fetched before action;
- failed V1-04 job/log inspected: element tests **4 PASS**, Ruff lint **PASS**, Ruff format **FAIL** on one new test file;
- failed V1-02 job/log inspected: comparison tests **26 PASS**, PostgreSQL **3 PASS**, Ruff lint **PASS**, same Ruff format failure;
- after formatting, exact-head V1-02 run `32252680254` → **success**;
- after formatting, exact-head V1-03 run `32252680249` → **success**;
- after formatting, exact-head V1-04 run `32252680278` → **success**;
- current review threads fetched; one parser correctness blocker found and fixed;
- final exact-head `7a2d39a7cdde4d62fec563ddf8d7887f17a8f409` workflows: V1-02 `32252992179` **success**, V1-03 `32252992260` **success**, V1-04 `32252992292` **success**;
- PR changed-file scope checked: only V1-04 workflow, parser boundary, and focused parser tests;
- review thread rechecked resolved/outdated;
- expected-head guarded merge → **success**, main merge SHA `0bb31d7151df85c43c5e8621acd25c8220b2f87f`;
- existing `ClaimParseResult` and `ClaimIndexRun` idempotency patterns inspected to constrain the persistence design.

### What was not verified

- decomposition persistence/schema does not exist yet;
- idempotent persisted decomposition runs have not yet been executed against PostgreSQL;
- decomposition API/UI are not implemented;
- human review remains intentionally unimplemented until V1-05.

### Remaining risks

- semicolon-only decomposition is deliberately conservative and may under-segment claims without explicit delimiters; this is surfaced as a warning rather than silently inferred;
- the persistence identity must bind a claim to parser name/version without allowing duplicate same-version element sets;
- element source spans must remain canonical claim-contained page-relative spans after persistence;
- human review must remain separate from machine decomposition in V1-05.

### Exact next action

**Create the smallest V1-04 persistence/idempotency slice from current `main`: add versioned decomposition-run/element/source-span persistence plus migration and focused PostgreSQL tests. Prove same-version rerun idempotency, ordering, and source containment. Do not add public API, UI, or human-review state until that slice is exact-head GREEN and merged.**

---

## 6. Verification Evidence

| Evidence | State | Note |
| --- | --- | --- |
| Existing stages 1–10 | VERIFIED BY STATIC INSPECTION | V1-01 |
| V1-02 comparison backend | EXECUTED GREEN / CLOSED | PR #7, run `32225430081` |
| V1-02 DB-free tests | 26 PASS | exact PR head |
| V1-02 PostgreSQL | 3 PASS / 0 skipped | exact PR head |
| V1-03 workspace slice | EXECUTED GREEN / MERGED | PR #8 |
| V1-03 contextual links | EXECUTED GREEN / MERGED | PR #9 |
| V1-03 browser golden path | EXECUTED GREEN / CLOSED | PR #10, run `32242502306` |
| V1-03 regression | EXECUTED GREEN | PR #10, run `32242502338` |
| V1-04 deterministic element boundary | EXECUTED GREEN / MERGED | PR #11, run `32252992292`, merge `0bb31d7151df85c43c5e8621acd25c8220b2f87f` |
| V1-04 persistence/idempotency | NOT IMPLEMENTED | next bounded slice |
| Persisted human review | NOT IMPLEMENTED | V1-05 |

---

## 7. Known Risks / Closure Condition

Known limits: citation resolvability ≠ semantic entailment; current real-model evidence uses a small model and synthetic data; OCR intentionally unsupported; Korean parser supports bounded patterns; comparison quality is retrieval quality, **not legal similarity**; decomposition is a domain-judgement boundary and therefore requires final human review.

v1.0 closes only when it is **usable, trustable, and showable**: full frozen workflow usable; expected failures explicit; source verification present; comparison + decomposition/review usable; clean checkout/migrations reproduced; general CI green; automated tests/evaluations reproducible; proof README/visuals/screenshots/demo/limitations/release tag complete.
