# ClaimTrace v1.0 Master

> **Authoritative execution contract for ClaimTrace v1.0.** Read this before every batch. `README.md` is external-facing, `docs/ARCHITECTURE.md` explains design, and `docs/ROADMAP.md` records broader possibilities. **This file controls what v1.0 is finishing now.**

**Last execution update:** 2026-08-19  
**Current target:** L4 Controlled Pilot  
**Current active batch:** V1-04 — Claim Element Decomposition  
**Current batch state:** **IN PROGRESS — persistence/idempotency slice merged; public decomposition API is the next acceptance gap**

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
| 13 element decomposition | IN PROGRESS | deterministic boundary + persistence/idempotency merged; public API remains |
| 14 persisted human review | MISSING | V1-05 |
| 15 source verification everywhere | PARTIAL | comparison source-linked; decomposition source spans persisted; public element API still pending |

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

- [x] element domain/schema exists with stable identifiers and ordered elements;
- [x] every persisted element is represented as a sub-span of the canonical persisted claim source;
- [x] decomposition run is versioned and idempotent/re-runnable without ambiguous duplication;
- [x] resistant/unsupported claim shapes produce explicit warnings or bounded failure instead of invented structure;
- [ ] API exposes decomposition result without legal-conclusion fields;
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
- review thread resolved;
- merged with expected-head guard as `0bb31d7151df85c43c5e8621acd25c8220b2f87f`.

Completed bounded slice — PR #12:

- branch `v1-04-element-persistence`;
- versioned `ElementDecompositionRun`, ordered `ClaimElement`, and ordered `ClaimElementSpan` persistence;
- DB uniqueness on `(claim_id, parser_name, parser_version)`;
- Alembic revision `0005`;
- idempotent `ClaimElementService` returning the existing same-version run;
- graceful same-version unique-conflict recovery via rollback + winning-run re-query;
- future parser version can coexist without overwriting prior provenance;
- Alembic environment explicitly registers `element_models` before reading `Base.metadata`;
- focused PostgreSQL tests prove same-version idempotency, ordered elements, exact source resolution, version coexistence, conflict recovery, and metadata registration path;
- public API/UI/human-review state remained out of scope for this slice;
- first execution exposed only formatting issues, then two P2 review findings were fixed in-scope;
- an over-broad Alembic `command.check` test was replaced after executed evidence showed unrelated pre-existing retrieval custom indexes would create false-positive drift;
- final exact head `c6a6bee05e54bed647f82c436d427149f2c30f4f`;
- V1-02 regression run `32259126922` → **success**;
- V1-03 regression/browser run `32259126863` → **success**;
- V1-04 run `32259126905` → **success**;
- all PR #12 review threads resolved;
- merged with expected-head guard to `main` as `1cf8cf6a1660cd2a814dc86274179108bed148cf`.

Next bounded acceptance gap: public decomposition API only. Issue-first lifecycle applies before any new implementation because the grandfathered PRs are now resolved.

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

Issue-first lifecycle for every new implementation gap after the grandfathered PRs:

1. search for one exact open implementation Issue representing the current MASTER gap;
2. reuse it only when it is clearly the same bounded work item;
3. otherwise create exactly one Issue before branch/commit/implementation;
4. Issue requires `Goal`, `Scope`, `Acceptance Criteria`, `Verification`, `Non-goals`, and `Evidence Required`;
5. keep one active implementation Issue at a time; concrete failures discovered inside it stay in the same work item;
6. merge/Issue closure requires executed verification and accepted PR merge, then reconcile this MASTER before selecting another gap.

Any SHA/run ID written here is historical evidence only. **Current repository/PR state always wins.** Missing push status is not evidence; prefer PR-visible exact-head workflow evidence. Agent self-report is not proof.

---

## 5. Current Batch Record — V1-04

### What changed

- PR #11 deterministic element boundary was verified and merged;
- PR #12 added versioned decomposition-run, ordered element, and ordered source-span persistence plus Alembic revision `0005`;
- PR #12 added same-version idempotency and parser-version coexistence;
- executed review identified missing Alembic model registration and concurrent same-version conflict handling; both were fixed in PR #12;
- Alembic environment now registers element models before `Base.metadata` is consumed;
- duplicate same-version commit conflicts now rollback and return the winning run with `created=False`;
- integration coverage now exercises the conflict recovery path and keeps metadata registration guarded without expanding into unrelated legacy index drift;
- PR #12 exact-head verification was brought GREEN and the PR merged.

### What was actually executed

- PR #11 final current-head V1-02/V1-03/V1-04 workflows all **success** and expected-head merge succeeded as `0bb31d7151df85c43c5e8621acd25c8220b2f87f`;
- PR #12 first V1-04 execution built the API image, ran parser **6 PASS**, PostgreSQL persistence **2 PASS / 0 skipped**, then exposed nine Ruff findings;
- after formatting correction, executed review produced two P2 findings: Alembic metadata registration and concurrent idempotency conflict recovery;
- both review findings were fixed and both review threads resolved;
- current-head V1-04 run `32258885843` exposed one concrete test-design failure: global Alembic `command.check` detected three unrelated pre-existing custom retrieval indexes, not an element-schema mismatch;
- that over-broad test was narrowed to assert the exact element-model registration path and required element tables only;
- final PR #12 exact head `c6a6bee05e54bed647f82c436d427149f2c30f4f` executed V1-02 `32259126922` **success**, V1-03 `32259126863` **success**, and V1-04 `32259126905` **success**;
- PR #12 merged with expected-head guard as `1cf8cf6a1660cd2a814dc86274179108bed148cf`.

### What was not verified

- public decomposition API is not implemented or verified;
- decomposition UI is not implemented;
- human review remains intentionally unimplemented until V1-05;
- the three pre-existing retrieval custom-index autogenerate diffs are outside this V1-04 slice and were not altered.

### Remaining risks

- persistence source containment is enforced by deterministic parser/service behavior plus integration assertions, not a cross-table SQL CHECK constraint;
- the conflict-recovery test deterministically exercises the unique-conflict recovery path but is not a high-load concurrency stress test;
- existing retrieval custom indexes are intentionally outside this slice and mean repository-wide Alembic `command.check` is not currently a clean generic gate;
- public API response contracts must preserve element/source provenance and exclude legal-conclusion fields;
- human review must remain separate from machine decomposition in V1-05.

### Exact next action

**Issue-first: search open Issues for an exact V1-04 public decomposition API work item. If none exists, create exactly one bounded Issue before any new branch/commit/implementation. The Issue must cover only a public decomposition API that exposes persisted machine decomposition with source spans, explicit warnings/errors, idempotent behavior, no legal-conclusion fields, focused API/PostgreSQL tests, and exact-head V1-02/V1-03/V1-04 verification. Do not add UI or human review in that work item.**

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
| V1-04 persistence/idempotency | EXECUTED GREEN / MERGED | PR #12 head `c6a6bee...`, runs `32259126922` / `32259126863` / `32259126905`, merge `1cf8cf6...` |
| V1-04 public decomposition API | NOT IMPLEMENTED | next Issue-first work item |
| Persisted human review | NOT IMPLEMENTED | V1-05 |

---

## 7. Known Risks / Closure Condition

Known limits: citation resolvability ≠ semantic entailment; current real-model evidence uses a small model and synthetic data; OCR intentionally unsupported; Korean parser supports bounded patterns; comparison quality is retrieval quality, **not legal similarity**; decomposition is a domain-judgement boundary and therefore requires final human review.

v1.0 closes only when it is **usable, trustable, and showable**: full frozen workflow usable; expected failures explicit; source verification present; comparison + decomposition/review usable; clean checkout/migrations reproduced; general CI green; automated tests/evaluations reproducible; proof README/visuals/screenshots/demo/limitations/release tag complete.
