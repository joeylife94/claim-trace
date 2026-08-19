# ClaimTrace v1.0 Master

> **Authoritative execution contract for ClaimTrace v1.0.** Read this before every batch. `README.md` is external-facing, `docs/ARCHITECTURE.md` explains design, and `docs/ROADMAP.md` records broader possibilities. **This file controls what v1.0 is finishing now.**

**Last execution update:** 2026-08-20  
**Current target:** L4 Controlled Pilot  
**Current active batch:** V1-06 — Operational Hardening  
**Current batch state:** **IN PROGRESS — clean start, empty-DB migration, deterministic whole-product reproducibility, and general CI are executed GREEN; final expected unsupported/failure-state validation remains**

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

Historical evidence retained until final V1-07 rerun: 876 backend tests after Phase 4A-2; deterministic grounded citation resolution `1.000`; `qwen2.5:1.5b` citation resolution `1.000`; statement citation coverage `1.000`; forbidden cross-document citations `0`.

Golden-path state:

| Stage | Status | v1 delta |
| --- | --- | --- |
| 1–10 ingest → grounded Q&A | EXECUTED GREEN in deterministic whole-product run | final V1-07 evaluation rerun remains |
| 11 target/reference selection | EXECUTED GREEN | V1-03 + V1-06 whole-product proof |
| 12 claim comparison | EXECUTED GREEN | V1-02/V1-03 + V1-06 whole-product proof |
| 13 element decomposition | EXECUTED GREEN | V1-04 + V1-06 whole-product proof |
| 14 persisted human review | EXECUTED GREEN | V1-05 + V1-06 whole-product proof |
| 15 source verification everywhere | EXECUTED GREEN for frozen golden path | search, grounded, comparison, review source navigation verified |

**Do not rebuild stages 1–14.**

---

## 3. Execution Plan

### V1-00 — Master Freeze
**CLOSED**

### V1-01 — Golden Path Gap Audit
**CLOSED**

### V1-02 — Claim Comparison Backend
**CLOSED**

PR #7, run `32225430081` success; DB-free comparison **26 PASS**; PostgreSQL **3 PASS / 0 skipped**; Ruff PASS; merge `db5e39d2118e42527a3794a32173e08535f18cec`.

### V1-03 — Comparison UI + Flow Stitching
**CLOSED**

PR #10, run `32242502306` success including browser golden path; merge `6de5a391715ace893189378710f8852b4542dfaa`.

### V1-04 — Claim Element Decomposition
**CLOSED**

PR #11 run `32252992292` success; PR #12 run `32259126905` success; Issue #13 / PR #14 run `32260927368` success, parser **6 PASS**, PostgreSQL persistence/API **7 PASS / 0 skipped**, Ruff PASS; merge `875e29529963fb28bd3d5efa44e98bee7848c689`.

### V1-05 — Human Review Boundary
**CLOSED**

- Issue #15 / PR #16: persistence/API, run `32264262027` success, PostgreSQL **2 PASS / 0 skipped**, Ruff PASS; merge `bf8623b0bdeb12c6b037bc538cea597ec0ecc50d`.
- Issue #17 / PR #18: review UI/source navigation, V1-03 regression `32265797797` + V1-05 `32265797594` success; browser document → decomposition → accepted review → persisted history → exact source highlight; merge `2c0471dde083c36a4c3c8ecbf893fa051df0e2b4`.
- Issue #19 was created from a stale snapshot and immediately closed as duplicate; no implementation attached.

### V1-06 — Operational Hardening
**IN PROGRESS**

Goal: prove the supported product is reproducible and operationally repeatable, not merely implemented on isolated feature PRs.

Acceptance areas:

- [x] clean clone/start path;
- [x] empty-DB migration path;
- [x] deterministic demo/sample material sufficient for the full supported golden path;
- [x] one repeatable whole-product golden-path procedure;
- [x] general CI backend/integration/lint/frontend gates;
- [ ] expected unsupported/failure-state validation.

#### Closed — Issue #20 / PR #21: clean checkout + empty DB

**Changed**
- isolated Compose verifier `scripts/verify-v1-06-clean-start.sh`;
- PR-visible `.github/workflows/v1-06-clean-start.yml`;
- safe `.env` initialization, empty isolated PostgreSQL state, full migration chain, API health/readiness.

**Actually Executed / Verified**
- final exact head `5030fb023e34b9a58b1c3a2c4d8d3d2ed9d978ea`;
- run `32275712641`, job `96142528344` → **SUCCESS**;
- Alembic `0001 → 0006 (head)` from empty DB;
- `/health` = `ok`; `/ready` = PostgreSQL `ok`;
- merge `380abc91ad703c3cf3d01e2466dc494d0a2ac6a1`; Issue #20 auto-closed.

#### Closed — Issue #22 / PR #23: deterministic whole-product golden path

**Changed**
- `scripts/verify-v1-06-golden-path.sh` using committed synthetic corpus + real ingest/parse/index seed path;
- `apps/web/e2e/v1-06-golden-path.mjs` covering Search → Grounded → Compare → Decompose/Review → exact source highlight;
- `.github/workflows/v1-06-golden-path.yml` exact-head browser + frontend gate.

**Actually Executed / Verified**
- final exact head `a1490d9154cb871adbe6f84de85e8efd24273ede`;
- final V1-06 run `32277157847` → **SUCCESS**;
- V1-03 regression `32277157837` → **SUCCESS**;
- V1-05 regression `32277157902` → **SUCCESS**;
- empty PostgreSQL + Alembic `0001 → 0006`, deterministic two-document seed, healthy API/Web, full frozen golden path, persisted human review, document-scoped exact source navigation → **PASS**;
- merge `b7f3326f35d47537a9415845ab26f3b3ce0b024e`; Issue #22 auto-closed.

#### Closed — Issue #24 / PR #25: general repository CI

**Changed**
- added `.github/workflows/ci.yml` as one PR-visible general quality gate for ordinary backend/frontend/shared-config changes;
- backend gate performs exact-head checkout, committed-default Compose validation, API test-image build, live PostgreSQL readiness, database-free tests, non-skipping integration tier, Ruff lint, and Ruff format check;
- frontend gate performs exact-head checkout, Node 22 `npm ci`, ESLint, and TypeScript typecheck;
- backend/frontend/shared config and workflow paths trigger the general gate.

**Actually Executed**
- exact PR head `da49dc8bd18b97a731ab2a2d469225c58dd9bef5`;
- PR-visible General CI run `32278344808` → **SUCCESS**;
- backend job `96150941645` → **SUCCESS**;
- database-free backend tier: **785 PASS / 135 deselected**;
- PostgreSQL integration tier: **135 PASS / 0 skipped / 785 deselected**;
- Ruff lint: **All checks passed**;
- Ruff format: **157 files already formatted**;
- frontend job `96150941220` → **SUCCESS**, including `npm ci`, ESLint, and TypeScript typecheck;
- no unresolved review threads;
- expected-head squash merge `664ad95675b51356c42d5f98ec14d80bf6b56ed2`;
- Issue #24 auto-closed `completed`.

**Verified**
- general PR changes now receive a current exact-head repository quality gate;
- PostgreSQL integration coverage executes against a live DB and cannot succeed through the integration-skip fallback;
- backend database-free tests + integration tests + Ruff and frontend lint/typecheck all executed GREEN on the implementation PR.

**Not Verified / Remaining Risks**
- the final V1-06 set of deliberately unsupported/expected failure states under a clean current-head run remains unverified;
- V1-07 final retrieval/grounding evaluation reruns and proof packaging remain;
- GitHub-hosted npm install output has reported dependency audit findings historically; dependency remediation remains out of scope unless a required V1-06/V1-07 gate concretely requires it.

**Exact Next Action**

**Re-evaluate V1-06 closure, then search current open Issues for one that exactly represents the sole remaining V1-06 gap: a bounded clean current-head verification set for expected unsupported/failure states. Reuse only an exact active Issue; otherwise create exactly one Issue before implementation. Do not expand into OCR/auth/security/dependency campaigns or V1-07 proof work.**

### V1-07 — Final Validation + Wishket Proof
**PLANNED**

Final test/evaluation rerun; README; architecture visual; ≥4 screenshots; demo asset; limitations; release/tag. Human Review remains the final release/proof gate before proof freeze.

---

## 4. Execution Rules

Every batch records **Goal / Scope / Acceptance / Non-goals / What changed / What was actually executed / Verified / Not Verified / Remaining risks / Exact Next Action**.

Start every run in this order:

**current repository/PR state → current exact head → exact-head required workflows → MASTER reconciliation → action**.

Active PR first. For new gaps: exact active Issue first, otherwise exactly one bounded Issue before branch/commit/implementation. Keep one active implementation Issue at a time. Do not create Issues for concrete CI/review fixes inside the active work item.

PR lifecycle: current exact-head RED/CANCELLED/TIMED_OUT/ACTION_REQUIRED/stale IN_PROGRESS → fix only the first concrete executed failure. GREEN + in scope + no unresolved blocker → merge with expected-head guard, confirm intended Issue closure, reconcile MASTER on `main`, then re-evaluate closure before selecting another Issue.

Any SHA/run ID here is historical evidence only; **current repository/PR state always wins**. Missing push status is not evidence. Agent self-report is not proof. BLOCKED/HOLD is not terminal; technical blockers stay recorded while the scheduled task remains enabled. Freeze/disable only at explicit Human Review / FREEZE / proof-candidate-ready / completion / user-requested stop.

---

## 5. Verification Evidence

| Evidence | State | Note |
| --- | --- | --- |
| V1-02 comparison backend | EXECUTED GREEN / CLOSED | PR #7, run `32225430081` |
| V1-03 browser golden path | EXECUTED GREEN / CLOSED | PR #10, run `32242502306` |
| V1-04 decomposition | EXECUTED GREEN / CLOSED | PR #11/#12/#14 |
| V1-05 review persistence/API + UI/source | EXECUTED GREEN / CLOSED | Issues #15/#17, PRs #16/#18 |
| V1-06 clean checkout + empty DB migration | EXECUTED GREEN / CLOSED | Issue #20 / PR #21, run `32275712641`, merge `380abc91...` |
| V1-06 deterministic whole-product reproducibility | EXECUTED GREEN / CLOSED | Issue #22 / PR #23, run `32277157847`, merge `b7f3326f...` |
| V1-06 general CI | EXECUTED GREEN / CLOSED | Issue #24 / PR #25, run `32278344808`, DB-free **785 PASS**, PostgreSQL **135 PASS / 0 skipped**, Ruff + frontend gates PASS, merge `664ad956...` |
| V1-06 final expected failure-state set | NOT VERIFIED | sole remaining V1-06 acceptance gap |

---

## 6. Known Risks / Closure Condition

Known limits: citation resolvability ≠ semantic entailment; current real-model evidence uses a small model and synthetic data; OCR intentionally unsupported; Korean parser supports bounded patterns; comparison quality is retrieval quality, **not legal similarity**; human review records local reviewer judgement and does not certify legal correctness.

V1-06 closes when the final expected unsupported/failure-state verification is executed GREEN and reconciled. v1.0 closes only when it is **usable, trustable, and showable**: full frozen workflow usable; expected failures explicit; source verification present; comparison + decomposition/review usable; clean checkout/migrations reproduced; general CI green; automated tests/evaluations reproducible; proof README/visuals/screenshots/demo/limitations/release tag complete.
