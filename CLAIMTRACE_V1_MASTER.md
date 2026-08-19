# ClaimTrace v1.0 Master

> **Authoritative execution contract for ClaimTrace v1.0.** Read this before every batch. `README.md` is external-facing, `docs/ARCHITECTURE.md` explains design, and `docs/ROADMAP.md` records broader possibilities. **This file controls what v1.0 is finishing now.**

**Last execution update:** 2026-08-19  
**Current target:** L4 Controlled Pilot  
**Current active batch:** V1-04 — Claim Element Decomposition  
**Current batch state:** **IN PROGRESS — PR #12 persistence/idempotency exact-head verification pending**

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
| 13 element decomposition | IN PROGRESS | deterministic boundary merged; persistence/idempotency in PR #12 |
| 14 persisted human review | MISSING | V1-05 |
| 15 source verification everywhere | PARTIAL | comparison source-linked; decomposition persistence is source-span based |

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
- browser golden path → **PASS**;
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
- exact page-relative source sub-span mapping including cross-page claims;
- explicit resistant/no-delimiter and empty-segment warnings;
- provenance mismatch rejection;
- final exact head `7a2d39a7cdde4d62fec563ddf8d7887f17a8f409`;
- V1-02 run `32252992179` → **success**;
- V1-03 run `32252992260` → **success**;
- V1-04 run `32252992292` → **success**;
- review thread resolved;
- merged with expected-head guard as `0bb31d7151df85c43c5e8621acd25c8220b2f87f`.

Current bounded slice — PR #12:

- branch `v1-04-element-persistence`;
- versioned `ElementDecompositionRun`, ordered `ClaimElement`, and ordered `ClaimElementSpan` persistence;
- DB uniqueness on `(claim_id, parser_name, parser_version)`;
- Alembic revision `0005`;
- idempotent `ClaimElementService` returning the existing same-version run;
- future parser version can coexist without overwriting prior provenance;
- focused PostgreSQL tests prove same-version idempotency, ordered elements, exact source resolution, and version coexistence;
- public API/UI/human-review state remain out of scope for this slice.

First PR #12 exact-head execution (`9d3b163e968e934f7a6896805b002b52a5c09d1f`):

- API image build → **PASS**;
- focused parser tests → **6 PASS**;
- PostgreSQL readiness → **PASS**;
- persistence integration → **2 PASS / 0 skipped**;
- Ruff lint → **FAIL**, nine concrete style/type-annotation findings only;
- Ruff format was skipped because lint failed.

The nine executed Ruff findings were fixed only: import formatting, one migration line wrap, one unused import, two missing `Settings` annotations, and three overlong test expressions. Current PR #12 exact head is `516e5d4ae37c1b0f725ee7e53af0aaf3231a137c`; new exact-head workflows are pending.

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

- diagnosed and fixed PR #11 exact-head format failure and a concrete parser review bug, then merged PR #11 after all required current-head checks were GREEN;
- created PR #12 from current `main` for persistence/idempotency only;
- added decomposition-run, ordered element, and ordered source-span persistence models;
- added Alembic revision `0005`;
- added an idempotent persistence service keyed by claim/parser name/version;
- added focused PostgreSQL integration tests;
- extended V1-04 verification to require PostgreSQL persistence tests with no skips;
- inspected the first PR #12 failure and fixed only its nine Ruff findings.

### What was actually executed

- PR #11 final current-head V1-02/V1-03/V1-04 workflows all **success** and expected-head merge succeeded as `0bb31d7151df85c43c5e8621acd25c8220b2f87f`;
- existing `ClaimParseResult`, `ClaimIndexRun`, migrations, session factory, and PostgreSQL fixture patterns inspected before persistence implementation;
- PR #12 first exact-head V1-04 run `32253941336` executed real checkout, Compose validation, API build, parser tests, PostgreSQL, migration-from-empty through integration fixture, persistence tests, and Ruff;
- parser tests **6 PASS**;
- persistence integration tests **2 PASS / 0 skipped**;
- first run failed only at Ruff lint with nine enumerated findings;
- those nine findings were fixed on PR #12; current exact head `516e5d4ae37c1b0f725ee7e53af0aaf3231a137c` has new workflows queued;
- PR #12 review threads checked: none at PR creation.

### What was not verified

- current exact-head PR #12 Ruff lint/format have not yet produced GREEN evidence;
- V1-02/V1-03 regressions on current PR #12 exact head are still pending;
- public decomposition API/UI are not implemented;
- human review remains intentionally unimplemented until V1-05.

### Remaining risks

- current exact-head formatting may still require `ruff format` output even after lint findings were fixed;
- persistence source containment is currently guaranteed by parser/service behavior and executed integration assertions, not a cross-table SQL CHECK constraint;
- concurrent same-version requests are DB-unique but have not yet been stress-tested for graceful conflict handling;
- human review must remain separate from machine decomposition in V1-05.

### Exact next action

**Fetch PR #12 CURRENT exact head and CURRENT exact-head PR-visible V1-02/V1-03/V1-04 workflows. If any required check is RED, inspect the first concrete failing step/log and fix only that executed failure. If all are GREEN, inspect current changed-file/review scope and merge PR #12 with expected-head guard. Then update this MASTER with merge evidence and proceed to the smallest public decomposition API slice; do not add UI or human review before the API slice is GREEN and merged.**

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
| V1-04 deterministic element boundary | EXECUTED GREEN / MERGED | PR #11, run `32252992292` |
| V1-04 persistence first execution | FUNCTIONAL TESTS GREEN / LINT RED | PR #12 run `32253941336`: parser 6 PASS, PostgreSQL persistence 2 PASS, Ruff 9 findings |
| V1-04 persistence current exact head | PENDING | PR #12 head `516e5d4ae37c1b0f725ee7e53af0aaf3231a137c` |
| Persisted human review | NOT IMPLEMENTED | V1-05 |

---

## 7. Known Risks / Closure Condition

Known limits: citation resolvability ≠ semantic entailment; current real-model evidence uses a small model and synthetic data; OCR intentionally unsupported; Korean parser supports bounded patterns; comparison quality is retrieval quality, **not legal similarity**; decomposition is a domain-judgement boundary and therefore requires final human review.

v1.0 closes only when it is **usable, trustable, and showable**: full frozen workflow usable; expected failures explicit; source verification present; comparison + decomposition/review usable; clean checkout/migrations reproduced; general CI green; automated tests/evaluations reproducible; proof README/visuals/screenshots/demo/limitations/release tag complete.
