# ClaimTrace v1.0 Master

> **Authoritative execution contract for ClaimTrace v1.0.** Read this before every batch. `README.md` is external-facing, `docs/ARCHITECTURE.md` explains design, and `docs/ROADMAP.md` records broader possibilities. **This file controls what v1.0 is finishing now.**

**Last execution update:** 2026-08-20  
**Current target:** L4 Controlled Pilot  
**Current active batch:** V1-07 — Final Validation + Wishket Proof  
**Current batch state:** **NEXT — V1-06 Operational Hardening is CLOSED; final current-head validation/evaluation rerun is the first V1-07 acceptance gap before proof packaging**

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

Historical evaluation evidence retained until V1-07 rerun: deterministic grounded citation resolution `1.000`; `qwen2.5:1.5b` citation resolution `1.000`; statement citation coverage `1.000`; forbidden cross-document citations `0`.

Current operational evidence supersedes the older 876-test checkpoint: V1-06 General CI exact-head execution proved **785 database-free PASS + 135 PostgreSQL integration PASS / 0 skipped**, with Ruff and frontend lint/typecheck GREEN.

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
**CLOSED**

Acceptance areas:

- [x] clean clone/start path;
- [x] empty-DB migration path;
- [x] deterministic demo/sample material sufficient for the full supported golden path;
- [x] one repeatable whole-product golden-path procedure;
- [x] general CI backend/integration/lint/frontend gates;
- [x] expected unsupported/failure-state validation.

#### Closed — Issue #20 / PR #21: clean checkout + empty DB

**Actually Executed / Verified**
- final exact head `5030fb023e34b9a58b1c3a2c4d8d3d2ed9d978ea`;
- run `32275712641`, job `96142528344` → **SUCCESS**;
- Alembic `0001 → 0006 (head)` from empty DB;
- `/health` = `ok`; `/ready` = PostgreSQL `ok`;
- expected-head merge `380abc91ad703c3cf3d01e2466dc494d0a2ac6a1`; Issue #20 auto-closed.

#### Closed — Issue #22 / PR #23: deterministic whole-product golden path

**Actually Executed / Verified**
- final exact head `a1490d9154cb871adbe6f84de85e8efd24273ede`;
- final V1-06 run `32277157847` → **SUCCESS**;
- V1-03 regression `32277157837` → **SUCCESS**;
- V1-05 regression `32277157902` → **SUCCESS**;
- empty PostgreSQL + Alembic `0001 → 0006`, deterministic two-document seed, healthy API/Web, full frozen golden path, persisted human review, document-scoped exact source navigation → **PASS**;
- expected-head merge `b7f3326f35d47537a9415845ab26f3b3ce0b024e`; Issue #22 auto-closed.

#### Closed — Issue #24 / PR #25: general repository CI

**Changed**
- `.github/workflows/ci.yml` provides one PR-visible general quality gate for ordinary backend/frontend/shared-config changes;
- backend gate uses exact-head checkout, committed-default Compose validation, API build, live PostgreSQL, database-free + non-skipping integration tiers, Ruff lint/format;
- frontend gate uses exact-head checkout, `npm ci`, ESLint, TypeScript typecheck.

**Actually Executed / Verified**
- exact head `da49dc8bd18b97a731ab2a2d469225c58dd9bef5`;
- General CI run `32278344808` → **SUCCESS**;
- database-free backend **785 PASS / 135 deselected**;
- PostgreSQL integration **135 PASS / 0 skipped / 785 deselected**;
- Ruff `All checks passed`; format `157 files already formatted`;
- frontend `npm ci` + ESLint + TypeScript typecheck → **SUCCESS**;
- no unresolved review threads;
- expected-head merge `664ad95675b51356c42d5f98ec14d80bf6b56ed2`; Issue #24 auto-closed.

#### Closed — Issue #26 / PR #27: final expected unsupported/failure states

**Changed**
- added `.github/workflows/v1-06-failure-states.yml` as a proof-only exact-head gate;
- reused existing HTTP contract tests; **no product code or behavior changed**.

**Actually Executed**
- exact PR head `431c85ad9d4b0aa8745600300c083b3adf5a8a99`;
- `V1-06 Expected Failure States` run `32278992050`, job `96153015153` → **SUCCESS**;
- focused representative failure-state tier: **5 PASS**;
- exact-head General CI regression run `32278991988` → **SUCCESS**;
- no unresolved review threads;
- expected-head squash merge `1bc636985ba85754a0e99e3743b7ca5794c5d357`;
- Issue #26 auto-closed `completed`.

**Verified**
- non-PDF bytes renamed as PDF are rejected with HTTP `415` / `unsupported_file_type`;
- image-only/no-text-layer PDF is rejected with HTTP `422` / `no_extractable_text`, preserving the explicit **no OCR** boundary;
- no retrieved grounded evidence returns HTTP `200` with `insufficient_evidence=true`, `no_retrieved_evidence`, no generation, and no fabricated statement;
- comparison with no correspondence returns explicit `no_matches`;
- unindexed reference comparison returns distinct explicit `reference_not_indexed`;
- current-head general regression remained GREEN.

**Not Verified / Remaining Risks after V1-06**
- V1-07 final retrieval/grounding evaluation reruns and external proof packaging remain;
- citation resolvability still does not prove semantic entailment;
- dependency audit findings reported by hosted npm install are not silently treated as resolved and remain out of scope absent a concrete V1-07 gate requiring remediation.

### V1-07 — Final Validation + Wishket Proof
**NEXT**

Acceptance areas:

- [ ] final current-head automated validation/evaluation rerun;
- [ ] retrieval evaluation reproduced;
- [ ] grounded deterministic evaluation reproduced;
- [ ] real local model validation rerun or explicitly and visibly marked not rerun;
- [ ] README communicates problem → solution → demo → evidence before deep implementation detail;
- [ ] architecture visual exists and matches current v1 boundaries;
- [ ] at least four useful product screenshots exist;
- [ ] concise golden-path demo asset exists;
- [ ] CI state/evidence is externally visible;
- [ ] proof metrics link to reproducible evidence;
- [ ] known limitations are visible;
- [ ] v1.0 proof release/tag exists;
- [ ] final Human Review / FREEZE decision.

**Exact Next Action**

**Before proof packaging, search current open Issues for one that exactly represents the first V1-07 gap: final current-head automated validation plus retrieval/grounded evaluation rerun. Reuse only an exact active Issue; otherwise create exactly one bounded Issue before branch/implementation. Keep real-local-model validation separate only if execution evidence shows it requires a materially different runtime.**

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
| V1-06 clean checkout + empty DB migration | EXECUTED GREEN / CLOSED | Issue #20 / PR #21, run `32275712641` |
| V1-06 deterministic whole-product reproducibility | EXECUTED GREEN / CLOSED | Issue #22 / PR #23, run `32277157847` |
| V1-06 general CI | EXECUTED GREEN / CLOSED | Issue #24 / PR #25, run `32278344808`, DB-free **785 PASS**, PostgreSQL **135 PASS / 0 skipped**, Ruff + frontend PASS |
| V1-06 final expected failure-state set | EXECUTED GREEN / CLOSED | Issue #26 / PR #27, run `32278992050`, focused **5 PASS**, General CI `32278991988` GREEN |
| V1-06 batch | **CLOSED** | every V1-06 acceptance area has current executed evidence |
| V1-07 final evaluations/proof | NOT VERIFIED | next batch |

---

## 6. Known Risks / Closure Condition

Known limits: citation resolvability ≠ semantic entailment; current real-model evidence uses a small model and synthetic data; OCR intentionally unsupported; Korean parser supports bounded patterns; comparison quality is retrieval quality, **not legal similarity**; human review records local reviewer judgement and does not certify legal correctness.

V1-06 is **CLOSED**. v1.0 closes only when it is **usable, trustable, and showable**: V1-07 validation/evaluations are current and reproducible; proof README/visuals/screenshots/demo/limitations/release tag are complete; and the resulting proof candidate reaches explicit **HUMAN REVIEW / FREEZE** rather than silently declaring itself final.
