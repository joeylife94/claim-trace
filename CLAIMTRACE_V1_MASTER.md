# ClaimTrace v1.0 Master

> **Authoritative execution contract for ClaimTrace v1.0.** Read this before every batch. `README.md` is external-facing, `docs/ARCHITECTURE.md` explains design, and `docs/ROADMAP.md` records broader possibilities. **This file controls what v1.0 is finishing now.**

**Last execution update:** 2026-08-19  
**Current target:** L4 Controlled Pilot  
**Current active batch:** V1-05 — Human Review Boundary  
**Current batch state:** **IN PROGRESS — Issue #15 review persistence/API foundation is the single active implementation work item**

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
| 14 persisted human review | IN PROGRESS | Issue #15 persistence/API foundation active |
| 15 source verification everywhere | PARTIAL | comparison/decomposition source-backed; review source navigation pending |

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

Acceptance:

- [x] element domain/schema exists with stable identifiers and ordered elements;
- [x] every persisted element is represented as a sub-span of canonical persisted claim source;
- [x] decomposition run is versioned and idempotent/re-runnable without ambiguous duplication;
- [x] resistant/unsupported claim shapes produce explicit warnings or bounded failure instead of invented structure;
- [x] API exposes decomposition result without legal-conclusion fields;
- [x] focused tests cover ordering, source-span containment, idempotency, resistant-claim behavior, and same-version conflict recovery;
- [x] merged bounded slices had exact-head executable checks GREEN before ordinary merge.

Closure evidence:

- PR #11 deterministic element boundary → V1-04 run `32252992292` **success**, merge `0bb31d7151df85c43c5e8621acd25c8220b2f87f`;
- PR #12 persistence/idempotency → V1-04 run `32259126905` **success**, merge `1cf8cf6a1660cd2a814dc86274179108bed148cf`;
- Issue #13 / PR #14 public decomposition API;
- PR #14 first exact-head execution: parser **6 PASS**, PostgreSQL persistence/API **7 PASS / 0 skipped**, then four Ruff `ANN001` failures only;
- only those executed lint failures were fixed by annotating the SQLAlchemy `Engine` test fixture;
- PR #14 final exact head `548e28637a2167f0ccfe09b836807a70c6e76c05`;
- V1-02 run `32260927179` → **success**;
- V1-03 run `32260927196` → **success**;
- V1-04 run `32260927368` → **success**;
- parser **6 PASS**; PostgreSQL persistence/API **7 PASS / 0 skipped**; Ruff lint/format **PASS**;
- no unresolved review threads;
- PR #14 merged with expected-head guard as `875e29529963fb28bd3d5efa44e98bee7848c689`;
- Issue #13 auto-closed as `completed` after merge.

### V1-05 — Human Review Boundary
**IN PROGRESS**

Goal: persist reviewer judgement separately from machine decomposition and make review source-verifiable without mutating machine output.

Acceptance:

- [ ] review record is separate from `ElementDecompositionRun` / machine element rows;
- [ ] minimum review states are `accepted` and `needs_correction`;
- [ ] review references the exact decomposition run/version it judged;
- [ ] re-running decomposition does not silently delete or rewrite prior review history;
- [ ] review API/UI exposes the reviewed element/source evidence and direct source navigation;
- [ ] focused persistence/API/UI tests prove review-state survival and provenance;
- [ ] no review field represents infringement, validity, novelty, equivalence, inventive step, or patentability.

Active bounded acceptance gap — Issue #15:

- `V1-05: Persist human review state for claim decomposition`;
- created only after Issue #13 closed, PR #14 merged, V1-04 was reconciled/closed, and open-Issue search found no exact V1-05 work item;
- Issue-linked branch `issue-15-v1-05-review-persistence` created from current `main`;
- scope is separate review persistence + bounded create/read API + exact decomposition-run linkage + survival across later parser-version runs + PostgreSQL verification;
- review UI is explicitly excluded from Issue #15 and must remain a later bounded V1-05 work item;
- Issue closure requires executed evidence and merged `Closes #15` PR.

Non-goals for Issue #15:

- no review UI yet;
- no mutation of machine decomposition text/spans;
- no legal decision/conclusion fields;
- no comparison changes;
- no OCR/auth/cloud/Kubernetes/billing/unrelated redesign.

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
2. reuse it only when clearly the same bounded work item;
3. otherwise create exactly one Issue before branch/commit/implementation;
4. Issue requires `Goal`, `Scope`, `Acceptance Criteria`, `Verification`, `Non-goals`, and `Evidence Required`;
5. keep one active implementation Issue at a time; concrete failures discovered inside it stay in the same work item;
6. merge/Issue closure requires executed verification and accepted PR merge, then reconcile this MASTER before selecting another gap.

Any SHA/run ID written here is historical evidence only. **Current repository/PR state always wins.** Missing push status is not evidence; prefer PR-visible exact-head workflow evidence. Agent self-report is not proof.

---

## 5. Current Batch Record — V1-05

### What changed

- Issue #13 / PR #14 completed the last V1-04 acceptance gap and V1-04 is CLOSED;
- Issue #13 closure was explicitly confirmed as `closed/completed` after PR #14 merge;
- open Issue search found no exact V1-05 human-review persistence work item;
- Issue #15 was created before implementation with Goal / Scope / Acceptance Criteria / Verification / Non-goals / Evidence Required;
- branch `issue-15-v1-05-review-persistence` was created from current `main`.

### What was actually executed

- PR #14 exact head `548e28637a2167f0ccfe09b836807a70c6e76c05` executed V1-02 `32260927179` **success**, V1-03 `32260927196` **success**, V1-04 `32260927368` **success**;
- V1-04 run proved parser **6 PASS**, PostgreSQL persistence/API **7 PASS / 0 skipped**, Ruff lint **PASS**, Ruff format **PASS**;
- PR #14 merged with expected-head guard as `875e29529963fb28bd3d5efa44e98bee7848c689`;
- Issue #13 was re-read after merge and confirmed `closed/completed`;
- repository Issue search for V1-05 / human review / review persistence returned no exact active work item before Issue #15 creation.

### What was not verified

- Issue #15 implementation has not yet been committed or executed;
- no V1-05 review persistence/API tests have run yet;
- review UI/source navigation remains intentionally deferred beyond Issue #15;
- final clean-checkout/general-CI/proof rerun remains V1-06/V1-07 work.

### Remaining risks

- V1-05 must preserve prior human review history across later decomposition parser versions;
- the review API must identify the exact machine run judged and must not mutate machine output;
- authentication/identity is out of scope, so v1.0 review provenance is a single-user local reviewer action, not a multi-user identity/audit system;
- Human Review remains the final release/proof gate and must be browser/source-navigation verified before v1.0 proof freeze.

### Exact next action

**ACTIVE ISSUE #15 FIRST. Implement only the smallest review persistence/API foundation on `issue-15-v1-05-review-persistence`: separate review model/table + migration, `accepted` / `needs_correction` states, exact `ElementDecompositionRun` reference, bounded create/read service/API, and PostgreSQL tests proving prior review survives a later parser-version decomposition run while machine rows/source spans remain unchanged. Open one PR with `Closes #15`; do not add UI in this Issue.**

---

## 6. Verification Evidence

| Evidence | State | Note |
| --- | --- | --- |
| Existing stages 1–10 | VERIFIED BY STATIC INSPECTION | V1-01 |
| V1-02 comparison backend | EXECUTED GREEN / CLOSED | PR #7, run `32225430081` |
| V1-02 DB-free tests | 26 PASS | exact PR head |
| V1-02 PostgreSQL | 3 PASS / 0 skipped | exact PR head |
| V1-03 browser golden path | EXECUTED GREEN / CLOSED | PR #10, run `32242502306` |
| V1-04 deterministic element boundary | EXECUTED GREEN / MERGED | PR #11, run `32252992292` |
| V1-04 persistence/idempotency | EXECUTED GREEN / MERGED | PR #12, run `32259126905` |
| V1-04 public decomposition API | EXECUTED GREEN / CLOSED | Issue #13, PR #14, run `32260927368`, merge `875e295...` |
| V1-05 review persistence/API | ACTIVE ISSUE / NOT IMPLEMENTED | Issue #15 |
| V1-05 review UI/source navigation | NOT IMPLEMENTED | later V1-05 work item |

---

## 7. Known Risks / Closure Condition

Known limits: citation resolvability ≠ semantic entailment; current real-model evidence uses a small model and synthetic data; OCR intentionally unsupported; Korean parser supports bounded patterns; comparison quality is retrieval quality, **not legal similarity**; decomposition is a domain-judgement boundary and therefore requires final human review.

v1.0 closes only when it is **usable, trustable, and showable**: full frozen workflow usable; expected failures explicit; source verification present; comparison + decomposition/review usable; clean checkout/migrations reproduced; general CI green; automated tests/evaluations reproducible; proof README/visuals/screenshots/demo/limitations/release tag complete.
