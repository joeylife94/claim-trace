# ClaimTrace v1.0 Master

> **Authoritative execution contract for ClaimTrace v1.0.** Read this before every batch. `README.md` is external-facing, `docs/ARCHITECTURE.md` explains design, and `docs/ROADMAP.md` records broader possibilities. **This file controls what v1.0 is finishing now.**

**Last execution update:** 2026-08-20  
**Current target:** L4 Controlled Pilot  
**Current active batch:** V1-06 — Operational Hardening  
**Current batch state:** **READY FOR ISSUE SELECTION — V1-05 closed with executed browser proof; select exactly one bounded V1-06 acceptance gap after Issue search**

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
| 14 persisted human review | EXECUTED GREEN | V1-05 closed |
| 15 source verification everywhere | EXECUTED GREEN for current golden path | review UI direct source navigation browser-verified; final whole-product rerun remains V1-06/V1-07 |

**Do not rebuild stages 1–14.**

---

## 3. Execution Plan

### V1-00 — Master Freeze
**CLOSED**

### V1-01 — Golden Path Gap Audit
**CLOSED**

### V1-02 — Claim Comparison Backend
**CLOSED**

Closure evidence: PR #7 exact head `f62b8847ec3bfd6df4ecf1750b6a0e5d90202f6c`; run `32225430081` success; DB-free comparison tests **26 PASS**; PostgreSQL integration **3 PASS / 0 skipped**; Ruff lint/format PASS; merged `db5e39d2118e42527a3794a32173e08535f18cec`.

### V1-03 — Comparison UI + Flow Stitching
**CLOSED**

Closure evidence: PR #10 exact head `1f093cbc6d611ef1aaedbea1ed934ff1f88d860c`; V1-02 regression `32242502338` success; V1-03 run `32242502306` success including browser golden path; merged `6de5a391715ace893189378710f8852b4542dfaa`.

### V1-04 — Claim Element Decomposition
**CLOSED**

Closure evidence:

- PR #11 deterministic element boundary → run `32252992292` success, merge `0bb31d7151df85c43c5e8621acd25c8220b2f87f`;
- PR #12 persistence/idempotency → run `32259126905` success, merge `1cf8cf6a1660cd2a814dc86274179108bed148cf`;
- Issue #13 / PR #14 public decomposition API → exact head `548e28637a2167f0ccfe09b836807a70c6e76c05`, V1-04 run `32260927368` success, parser **6 PASS**, PostgreSQL persistence/API **7 PASS / 0 skipped**, Ruff PASS, merge `875e29529963fb28bd3d5efa44e98bee7848c689`, Issue #13 completed.

### V1-05 — Human Review Boundary
**CLOSED**

Goal achieved: reviewer judgement is persisted separately from machine decomposition and is source-verifiable through the web UI without mutating machine output.

Acceptance:

- [x] review record separate from machine decomposition rows;
- [x] minimum states `accepted` / `needs_correction`;
- [x] exact decomposition run/parser version linkage;
- [x] prior review history survives later decomposition runs;
- [x] review UI exposes exact run, ordered elements, source evidence, and append-only history;
- [x] review controls submit through existing bounded review API without editing machine output;
- [x] direct source navigation resolves reviewed element spans to exact original page/character ranges;
- [x] browser proof covers review submission, persisted history, and source highlight;
- [x] no legal-conclusion fields or semantics.

Persistence/API foundation — Issue #15 / PR #16:

- exact head `b4f3d3bef2817909b81afae5bfede89be127d425`;
- V1-02 `32264262101` success;
- V1-03 `32264262064` success including browser regression;
- V1-04 `32264262002` success;
- V1-05 `32264262027` success;
- focused PostgreSQL review persistence/API **2 PASS / 0 skipped**;
- Ruff lint/format PASS;
- merged `bf8623b0bdeb12c6b037bc538cea597ec0ecc50d`;
- Issue #15 completed.

Review UI/source-navigation closure — Issue #17 / PR #18:

- Issue #17 `V1-05: Add human review UI with direct source navigation` → **closed/completed** after merge;
- PR #18 final exact head `9943e0427362d8626cfdc8e3f75a2cc52f4b4977`;
- V1-03 Comparison UI Verification run `32265797797` → **success**, including browser regression;
- V1-05 Human Review Verification run `32265797594` → **success**;
- V1-05 persistence/API job → success;
- frontend npm install + ESLint + TypeScript → success;
- browser review path → **success**: document → `Decompose & review` → exact run page → append accepted review → persisted history visible → exact source link → source highlight;
- Ruff lint + format → success through V1-05 persistence job;
- one pending-submit review-thread finding was repaired and the thread is resolved;
- PR #18 merged with expected-head guard as `2c0471dde083c36a4c3c8ecbf893fa051df0e2b4`;
- `main` re-read at `2c0471dde083c36a4c3c8ecbf893fa051df0e2b4` confirms review UI files are present.

Historical reconciliation note: Issue #19 was created from a stale MASTER snapshot during reconciliation, then immediately closed as `duplicate` after current repository state showed Issue #17 / PR #18 had already completed the same acceptance gap. No implementation was attached to #19.

### V1-06 — Operational Hardening
**READY FOR ISSUE SELECTION**

Goal: prove the supported product is reproducible and operationally repeatable, not merely implemented on prior PR-specific paths.

Planned acceptance areas:

- clean clone/start path;
- empty-DB migration path;
- deterministic demo/sample material sufficient for the full supported golden path;
- one repeatable golden-path procedure;
- general CI backend/integration/lint/frontend gates rather than only phase-specific PR workflows;
- expected unsupported/failure-state validation.

No V1-06 implementation work begins until one exact open Issue is reused or one new bounded Issue is created under the Issue-first lifecycle.

### V1-07 — Final Validation + Wishket Proof
**PLANNED**

Final test/evaluation rerun; README; architecture visual; ≥4 screenshots; demo asset; limitations; release/tag. Human Review remains the final release/proof gate before proof freeze.

---

## 4. Execution Rules

Every batch defines **Goal / Scope / Acceptance / Non-goals** and records **What changed / What was actually executed / What was not verified / Remaining risks / Exact Next Action**.

Current-state order at the start of every run:

**current repository/PR state → current exact head → exact-head required workflows → MASTER reconciliation → action**.

PR lifecycle:

1. inspect current relevant active focused PR and current exact-head pull-request-visible workflows first;
2. RED/CANCELLED/TIMED_OUT/ACTION_REQUIRED/stale IN_PROGRESS → inspect first concrete job/step/log; fix only that executed failure;
3. GREEN + in scope + no unresolved review/security/human-decision blocker → merge with expected-head guard;
4. update this MASTER on `main` with concrete evidence and resulting main SHA;
5. continue to the next smallest step in the earliest unfinished batch.

Issue-first lifecycle for every new implementation gap:

1. search for one exact open implementation Issue representing the current MASTER gap;
2. reuse it only when clearly the same bounded work item;
3. otherwise create exactly one Issue before branch/commit/implementation;
4. Issue requires `Goal`, `Scope`, `Acceptance Criteria`, `Verification`, `Non-goals`, and `Evidence Required`;
5. keep one active implementation Issue at a time; concrete failures discovered inside it stay in the same work item;
6. merge/Issue closure requires executed verification and accepted PR merge, then reconcile this MASTER before selecting another gap.

Any SHA/run ID written here is historical evidence only. **Current repository/PR state always wins.** Missing push status is not evidence; prefer PR-visible exact-head workflow evidence. Agent self-report is not proof.

BLOCKED/HOLD is not a terminal automation state. Technical blockers stay recorded with exact evidence and one exact next action; task freeze/disable is reserved for explicit Human Review / FREEZE / proof-candidate-ready / completion / user-requested stop.

---

## 5. Current Batch Record — V1-06

### What changed

- no V1-06 product/runtime implementation has started;
- V1-05 was reconciled from stale MASTER state to actual merged Issue #17 / PR #18 state;
- duplicate reconciliation Issue #19 was closed as `duplicate` with no implementation attached;
- earliest unfinished batch is now V1-06.

### What was actually executed

Current-state reconciliation:

- fetched `main` and confirmed current SHA `2c0471dde083c36a4c3c8ecbf893fa051df0e2b4` before this MASTER update;
- re-read Issue #17 → `closed/completed`;
- re-read PR #18 → merged, final head `9943e0427362d8626cfdc8e3f75a2cc52f4b4977`, merge commit `2c0471dde083c36a4c3c8ecbf893fa051df0e2b4`;
- exact-head PR-visible workflow lookup: V1-05 run `32265797594` success and V1-03 run `32265797797` success;
- PR #18 review threads re-read: one thread, resolved;
- review UI source file fetched directly from `main` and confirmed present.

### What was not verified

- clean clone from a new checkout has not yet been executed as a V1-06 acceptance surface;
- empty-database migration has not yet been rerun as a general V1-06 gate;
- a single full-product golden path from clean state has not yet been executed under one general reproducible procedure;
- general CI consolidation and final proof/evaluation work remain unverified.

### Remaining risks

- current phase-specific workflows prove bounded slices, but do not yet prove one clean-checkout whole-product operating path;
- historical test/evaluation evidence must be refreshed before release proof freeze;
- open draft PR #6 is older proof/runtime work and is not currently authorized to override V1-06 Issue-first selection unless a future MASTER-approved gap explicitly matches it.

### Exact Next Action

**Search open GitHub Issues for one exact V1-06 Operational Hardening acceptance gap. Reuse only if it exactly matches one bounded remaining gap. If none exists, create exactly one bounded V1-06 Issue with Goal / Scope / Acceptance Criteria / Verification / Non-goals / Evidence Required before any implementation. Do not start V1-07 until V1-06 acceptance is actually executed and closed.**

---

## 6. Verification Evidence

| Evidence | State | Note |
| --- | --- | --- |
| Existing stages 1–10 | VERIFIED BY STATIC INSPECTION | V1-01 |
| V1-02 comparison backend | EXECUTED GREEN / CLOSED | PR #7, run `32225430081` |
| V1-03 browser golden path | EXECUTED GREEN / CLOSED | PR #10, run `32242502306` |
| V1-04 deterministic element boundary | EXECUTED GREEN / CLOSED | PR #11, run `32252992292` |
| V1-04 persistence/idempotency | EXECUTED GREEN / CLOSED | PR #12, run `32259126905` |
| V1-04 public decomposition API | EXECUTED GREEN / CLOSED | Issue #13, PR #14, run `32260927368` |
| V1-05 review persistence/API | EXECUTED GREEN / CLOSED | Issue #15, PR #16, run `32264262027` |
| V1-05 review UI/source navigation | EXECUTED GREEN / CLOSED | Issue #17, PR #18, run `32265797594`, browser path PASS |
| V1-06 clean whole-product reproducibility | NOT VERIFIED | next batch |

---

## 7. Known Risks / Closure Condition

Known limits: citation resolvability ≠ semantic entailment; current real-model evidence uses a small model and synthetic data; OCR intentionally unsupported; Korean parser supports bounded patterns; comparison quality is retrieval quality, **not legal similarity**; human review records local reviewer judgement and does not certify legal correctness.

v1.0 closes only when it is **usable, trustable, and showable**: full frozen workflow usable; expected failures explicit; source verification present; comparison + decomposition/review usable; clean checkout/migrations reproduced; general CI green; automated tests/evaluations reproducible; proof README/visuals/screenshots/demo/limitations/release tag complete.
