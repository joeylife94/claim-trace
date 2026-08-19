# ClaimTrace v1.0 Master

> **Authoritative execution contract for ClaimTrace v1.0.** Read this before every batch. `README.md` is external-facing, `docs/ARCHITECTURE.md` explains design, and `docs/ROADMAP.md` records broader possibilities. **This file controls what v1.0 is finishing now.**

**Last execution update:** 2026-08-20  
**Current target:** L4 Controlled Pilot  
**Current active batch:** V1-06 — Operational Hardening  
**Current batch state:** **IN PROGRESS — Issue #20 / PR #21 clean-checkout + empty-DB migration verification; exact-head run `32270376815` currently in progress**

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

Existing engine: FastAPI + Next.js, PostgreSQL + pgvector/pg_trgm, PDF persistence/provenance, deterministic Korean claim parsing, dense/lexical/RRF retrieval, exact source links, local/self-hosted LLM boundary, grounded Q&A with server-issued evidence IDs, citation resolution, explicit insufficient evidence, deterministic/real-local-model evaluation tiers, hostile-evidence guards, Docker Compose.

Historical evidence retained until final rerun: 876 backend tests after Phase 4A-2; deterministic grounded citation resolution `1.000`; `qwen2.5:1.5b` citation resolution `1.000`; statement citation coverage `1.000`; forbidden cross-document citations `0`.

Golden-path state:

| Stage | Status | v1 delta |
| --- | --- | --- |
| 1–10 ingest → grounded Q&A | READY | final runtime re-verification only |
| 11 target/reference selection | EXECUTED GREEN | V1-03 closed |
| 12 claim comparison | EXECUTED GREEN | V1-02/V1-03 closed |
| 13 element decomposition | EXECUTED GREEN | V1-04 closed |
| 14 persisted human review | EXECUTED GREEN | V1-05 closed |
| 15 source verification everywhere | EXECUTED GREEN for current golden path | review source navigation browser-verified; whole-product operational/proof rerun remains V1-06/V1-07 |

**Do not rebuild stages 1–14.**

---

## 3. Execution Plan

### V1-00 — Master Freeze
**CLOSED**

### V1-01 — Golden Path Gap Audit
**CLOSED**

### V1-02 — Claim Comparison Backend
**CLOSED**

Closure evidence: PR #7, run `32225430081` success; DB-free comparison **26 PASS**; PostgreSQL **3 PASS / 0 skipped**; Ruff PASS; merge `db5e39d2118e42527a3794a32173e08535f18cec`.

### V1-03 — Comparison UI + Flow Stitching
**CLOSED**

Closure evidence: PR #10, run `32242502306` success including browser golden path; merge `6de5a391715ace893189378710f8852b4542dfaa`.

### V1-04 — Claim Element Decomposition
**CLOSED**

Closure evidence: PR #11 run `32252992292` success; PR #12 run `32259126905` success; Issue #13 / PR #14 run `32260927368` success, parser **6 PASS**, PostgreSQL persistence/API **7 PASS / 0 skipped**, Ruff PASS; merge `875e29529963fb28bd3d5efa44e98bee7848c689`.

### V1-05 — Human Review Boundary
**CLOSED**

Persistence/API — Issue #15 / PR #16:

- exact head `b4f3d3bef2817909b81afae5bfede89be127d425`;
- V1-05 run `32264262027` success;
- PostgreSQL review persistence/API **2 PASS / 0 skipped**;
- Ruff PASS;
- merge `bf8623b0bdeb12c6b037bc538cea597ec0ecc50d`;
- Issue #15 completed.

Review UI/source navigation — Issue #17 / PR #18:

- final exact head `9943e0427362d8626cfdc8e3f75a2cc52f4b4977`;
- V1-03 regression run `32265797797` success;
- V1-05 run `32265797594` success;
- frontend ESLint + TypeScript success;
- browser path success: document → `Decompose & review` → exact run → append accepted review → persisted history → exact source link → source highlight;
- review controls are pending-aware after executed review feedback; thread resolved;
- merge `2c0471dde083c36a4c3c8ecbf893fa051df0e2b4`;
- Issue #17 completed.

Reconciliation note: Issue #19 was accidentally created from a stale MASTER snapshot, then immediately closed as `duplicate` after current state showed #17/#18 had already completed the same gap. No implementation attached.

### V1-06 — Operational Hardening
**IN PROGRESS**

Goal: prove the supported product is reproducible and operationally repeatable, not merely implemented on prior PR-specific paths.

Acceptance areas:

- clean clone/start path;
- empty-DB migration path;
- deterministic demo/sample material sufficient for the full supported golden path;
- one repeatable golden-path procedure;
- general CI backend/integration/lint/frontend gates;
- expected unsupported/failure-state validation.

Current bounded work item — Issue #20 / PR #21:

**Goal:** prove clean checkout + empty PostgreSQL migration + API readiness without developer-local state.

**Changed:**

- Issue #20 created before implementation under Issue-first lifecycle;
- branch `issue-20-v1-06-clean-start` created from current `main`;
- `scripts/verify-v1-06-clean-start.sh` added;
- verifier uses isolated Compose project `claimtrace-v1-06-clean-start`, runs existing safe `make init`, removes only isolated volumes, builds API, starts PostgreSQL, requires `pg_isready`, applies `alembic upgrade head`, starts API, and requires `/health` + `/ready` with PostgreSQL ready;
- `.github/workflows/v1-06-clean-start.yml` added as bounded PR-visible exact-head verification;
- PR #21 opened with `Closes #20`.

**Actually Executed:**

- current repository/MASTER reconciliation before Issue selection;
- open-Issue search returned no exact V1-06 work item;
- shell syntax check on the verifier shape via `sh -n` → PASS;
- PR #21 current exact head `ffc8a559d5ac0dbe77f6c72a08343a370890020d`;
- PR-visible run `32270376815` is currently `in_progress`;
- PR #21 review-thread lookup currently shows no threads.

**Verified:**

- scope is limited to the first V1-06 clean-start/empty-DB acceptance gap;
- verifier uses an isolated Compose project and does not target the ordinary developer project's volumes.

**Not Verified:**

- Docker build/start on the exact PR head;
- actual empty-DB full Alembic migration;
- API `/health` and `/ready` against that migrated database;
- all three remain pending until run `32270376815` completes successfully.

**Remaining Risks:**

- the runner may expose a concrete Docker/startup/config assumption that requires a small evidence-driven repair;
- this work item intentionally does not cover full demo data, whole-product browser procedure, general CI consolidation, or V1-07 proof packaging.

**Exact Next Action:**

**Re-read PR #21 current exact head and run `32270376815`. If RED/CANCELLED/TIMED_OUT/ACTION_REQUIRED, inspect the first concrete failing job/step and repair only that failure inside Issue #20. If GREEN, confirm scope/review state, merge with expected-head guard, confirm Issue #20 closes, then reconcile this MASTER on resulting `main` before selecting the next V1-06 Issue.**

### V1-07 — Final Validation + Wishket Proof
**PLANNED**

Final test/evaluation rerun; README; architecture visual; ≥4 screenshots; demo asset; limitations; release/tag. Human Review remains the final release/proof gate before proof freeze.

---

## 4. Execution Rules

Every batch records **Goal / Scope / Acceptance / Non-goals / What changed / What was actually executed / Verified / Not Verified / Remaining risks / Exact Next Action**.

Start every run in this order:

**current repository/PR state → current exact head → exact-head required workflows → MASTER reconciliation → action**.

Active PR first. Existing pre-Issue-first PRs are grandfathered; do not create retroactive Issues for them. For new gaps: exact active Issue first, otherwise exactly one bounded Issue before branch/commit/implementation. Keep one active implementation Issue at a time.

PR lifecycle: current exact-head RED/CANCELLED/TIMED_OUT/ACTION_REQUIRED/stale IN_PROGRESS → fix only the first concrete executed failure. GREEN + in scope + no unresolved blocker → merge with expected-head guard, confirm intended Issue closure, reconcile MASTER on `main`, then re-evaluate closure before selecting another Issue.

Any SHA/run ID here is historical evidence only; **current repository/PR state always wins**. Missing push status is not evidence. Agent self-report is not proof. BLOCKED/HOLD is not terminal; technical blockers stay recorded while the scheduled task remains enabled. Freeze/disable only at explicit Human Review / FREEZE / proof-candidate-ready / completion / user-requested stop.

---

## 5. Verification Evidence

| Evidence | State | Note |
| --- | --- | --- |
| V1-02 comparison backend | EXECUTED GREEN / CLOSED | PR #7, run `32225430081` |
| V1-03 browser golden path | EXECUTED GREEN / CLOSED | PR #10, run `32242502306` |
| V1-04 decomposition | EXECUTED GREEN / CLOSED | PR #11/#12/#14 |
| V1-05 review persistence/API | EXECUTED GREEN / CLOSED | Issue #15 / PR #16 |
| V1-05 review UI/source navigation | EXECUTED GREEN / CLOSED | Issue #17 / PR #18, run `32265797594` |
| V1-06 clean checkout + empty DB migration | IN PROGRESS | Issue #20 / PR #21, run `32270376815` |
| V1-06 full whole-product reproducibility | NOT VERIFIED | later bounded work |

---

## 6. Known Risks / Closure Condition

Known limits: citation resolvability ≠ semantic entailment; current real-model evidence uses a small model and synthetic data; OCR intentionally unsupported; Korean parser supports bounded patterns; comparison quality is retrieval quality, **not legal similarity**; human review records local reviewer judgement and does not certify legal correctness.

v1.0 closes only when it is **usable, trustable, and showable**: full frozen workflow usable; expected failures explicit; source verification present; comparison + decomposition/review usable; clean checkout/migrations reproduced; general CI green; automated tests/evaluations reproducible; proof README/visuals/screenshots/demo/limitations/release tag complete.
