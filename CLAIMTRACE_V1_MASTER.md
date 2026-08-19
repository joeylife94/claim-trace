# ClaimTrace v1.0 Master

> **Authoritative execution contract for ClaimTrace v1.0.** Read this before every batch. `README.md` is external-facing, `docs/ARCHITECTURE.md` explains design, and `docs/ROADMAP.md` records broader possibilities. **This file controls what v1.0 is finishing now.**

**Last execution update:** 2026-08-19  
**Current target:** L4 Controlled Pilot  
**Current active batch:** V1-05 — Human Review Boundary  
**Current batch state:** **PLANNED — V1-04 closed; re-evaluate open Issues before starting the first V1-05 work item**

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
| 13 element decomposition | EXECUTED GREEN | V1-04 closed |
| 14 persisted human review | MISSING | V1-05 active batch |
| 15 source verification everywhere | PARTIAL | comparison and decomposition source-backed; review source navigation still pending |

**Do not rebuild stages 1–13.**

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
**CLOSED**

Goal: decompose a persisted claim into individually reviewable elements/limitations while preserving canonical source provenance and keeping machine output explicitly non-authoritative.

Acceptance:

- [x] element domain/schema exists with stable identifiers and ordered elements;
- [x] every persisted element is represented as a sub-span of the canonical persisted claim source;
- [x] decomposition run is versioned and idempotent/re-runnable without ambiguous duplication;
- [x] resistant/unsupported claim shapes produce explicit warnings or bounded failure instead of invented structure;
- [x] API exposes decomposition result without legal-conclusion fields;
- [x] focused tests cover ordering, source-span containment, idempotency, resistant-claim behavior, and same-version conflict recovery;
- [x] merged bounded slices had exact-head executable checks GREEN before ordinary merge.

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
- merged with expected-head guard as `0bb31d7151df85c43c5e8621acd25c8220b2f87f`.

Completed bounded slice — PR #12:

- versioned `ElementDecompositionRun`, ordered `ClaimElement`, and ordered `ClaimElementSpan` persistence;
- DB uniqueness on `(claim_id, parser_name, parser_version)` and Alembic revision `0005`;
- idempotent `ClaimElementService`, parser-version coexistence, and same-version unique-conflict recovery;
- exact-head V1-02 run `32259126922` → **success**;
- exact-head V1-03 run `32259126863` → **success**;
- exact-head V1-04 run `32259126905` → **success**;
- merged with expected-head guard to `main` as `1cf8cf6a1660cd2a814dc86274179108bed148cf`.

Completed bounded slice — Issue #13 / PR #14:

- Issue #13 `V1-04: Expose persisted claim element decomposition API` was created before implementation under the Issue-first lifecycle;
- PR #14 `Expose V1-04 claim element decomposition API` linked with `Closes #13`;
- public persisted POST decomposition endpoint added with stable run/element IDs, parser version, warnings, ordered elements, exact source locators, 201 create / 200 same-version reuse, and explicit missing-document/parse/claim states;
- response contract excludes legal-conclusion fields and labels machine output as review material;
- first exact-head V1-04 run reached parser **6 PASS** and PostgreSQL persistence/API **7 PASS / 0 skipped**, then failed only Ruff `ANN001` on four untyped test fixture arguments;
- only that executed lint failure was corrected by annotating the SQLAlchemy `Engine` fixture;
- final exact head `548e28637a2167f0ccfe09b836807a70c6e76c05`;
- V1-02 regression run `32260927179` → **success**;
- V1-03 regression/browser run `32260927196` → **success**;
- V1-04 run `32260927368` → **success**;
- focused element parser **6 PASS**;
- PostgreSQL element persistence + API integration **7 PASS / 0 skipped**;
- Ruff lint **PASS**;
- Ruff format **PASS** (`151 files already formatted`);
- no unresolved review threads;
- merged with expected-head guard to `main` as `875e29529963fb28bd3d5efa44e98bee7848c689`;
- Issue #13 is expected to auto-close through the merged `Closes #13` PR and must be confirmed before starting a new Issue.

V1-04 non-goals remained frozen: no human-review persistence/UI, no comparison rebuild, no LLM legal interpretation, no OCR/auth/cloud/Kubernetes work, no unrelated UI redesign.

### V1-05 — Human Review Boundary
**PLANNED / EARLIEST UNFINISHED BATCH**

Goal: persist reviewer judgement separately from machine decomposition and make review source-verifiable without mutating machine output.

Minimum acceptance boundary:

- review record is separate from `ElementDecompositionRun` / machine element rows;
- minimum review states are `accepted` and `needs_correction`;
- review references the exact decomposition run/version it judged;
- re-running decomposition does not silently delete or rewrite prior review history;
- review API/UI exposes the reviewed element/source evidence and direct source navigation;
- focused persistence/API/UI tests prove review-state survival and provenance;
- no review field represents infringement, validity, novelty, equivalence, inventive step, or patentability.

Implementation must be decomposed into bounded Issue-first work items; do not create parallel acceptance gaps.

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

Issue-first lifecycle for every new implementation gap:

1. search for one exact open implementation Issue representing the current MASTER gap;
2. reuse it only when it is clearly the same bounded work item;
3. otherwise create exactly one Issue before branch/commit/implementation;
4. Issue requires `Goal`, `Scope`, `Acceptance Criteria`, `Verification`, `Non-goals`, and `Evidence Required`;
5. keep one active implementation Issue at a time; concrete failures discovered inside it stay in the same work item;
6. merge/Issue closure requires executed verification and accepted PR merge, then reconcile this MASTER before selecting another gap.

Any SHA/run ID written here is historical evidence only. **Current repository/PR state always wins.** Missing push status is not evidence; prefer PR-visible exact-head workflow evidence. Agent self-report is not proof.

---

## 5. Current Batch Record — V1-05

### What changed

- V1-04 public decomposition API acceptance was completed through Issue #13 / PR #14 and merged;
- V1-04 is now closed because all frozen V1-04 acceptance criteria have executed evidence;
- current batch advanced to V1-05 Human Review Boundary only after V1-04 merge and MASTER reconciliation.

### What was actually executed

- PR #14 initial exact-head execution proved parser **6 PASS** and PostgreSQL persistence/API **7 PASS / 0 skipped**, then exposed four Ruff `ANN001` findings;
- only those four type-annotation findings were fixed;
- PR #14 final exact head `548e28637a2167f0ccfe09b836807a70c6e76c05` executed V1-02 `32260927179` **success**, V1-03 `32260927196` **success**, and V1-04 `32260927368` **success**;
- final V1-04 run proved parser **6 PASS**, PostgreSQL persistence/API **7 PASS / 0 skipped**, Ruff lint **PASS**, and Ruff format **PASS**;
- PR #14 had no unresolved review threads and merged with expected-head guard as `875e29529963fb28bd3d5efa44e98bee7848c689`.

### What was not verified

- Issue #13 auto-close has not yet been re-read after merge in this MASTER reconciliation step;
- no V1-05 human-review persistence, API, or UI has been implemented or verified yet;
- decomposition output remains machine-produced and non-authoritative until V1-05 closes;
- final clean-checkout/general-CI/proof rerun remains V1-06/V1-07 work.

### Remaining risks

- decomposition source containment is enforced by deterministic parser/service behavior plus executed assertions, not a cross-table SQL CHECK constraint;
- same-version conflict recovery is tested deterministically but is not a high-load concurrency stress test;
- pre-existing retrieval custom-index Alembic autogenerate drift remains outside V1-04 and will need explicit treatment if V1-06 chooses repository-wide Alembic drift checking;
- V1-05 must preserve human review history across reprocessing and must not mutate machine decomposition output.

### Exact next action

**Confirm Issue #13 closed through merged PR #14. Then search open Issues for an exact V1-05 human-review persistence work item. If none exists, create exactly one bounded Issue before any implementation. The first V1-05 work item should be the smallest persistence/API foundation that stores review state separately from machine decomposition, references an exact decomposition run, and proves review survival across decomposition re-runs. Do not add UI until that persistence/API acceptance surface is merged and reconciled.**

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
| V1-04 persistence/idempotency | EXECUTED GREEN / MERGED | PR #12, run `32259126905` |
| V1-04 public decomposition API | EXECUTED GREEN / MERGED / CLOSED | Issue #13, PR #14, runs `32260927179` / `32260927196` / `32260927368`, merge `875e295...` |
| Persisted human review | NOT IMPLEMENTED | V1-05 |

---

## 7. Known Risks / Closure Condition

Known limits: citation resolvability ≠ semantic entailment; current real-model evidence uses a small model and synthetic data; OCR intentionally unsupported; Korean parser supports bounded patterns; comparison quality is retrieval quality, **not legal similarity**; decomposition is a domain-judgement boundary and therefore requires final human review.

v1.0 closes only when it is **usable, trustable, and showable**: full frozen workflow usable; expected failures explicit; source verification present; comparison + decomposition/review usable; clean checkout/migrations reproduced; general CI green; automated tests/evaluations reproducible; proof README/visuals/screenshots/demo/limitations/release tag complete.
